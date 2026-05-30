#!/usr/bin/env python3
"""Vault proposals via Discord reactions (Hermes-friendly, no WebSocket).

Uses Hermes' Discord bot token via REST API only — no gateway connection,
so it can run in parallel with Hermes without WebSocket conflicts.

Workflow (every subcommand is idempotent):

  post     Read pending proposals → post any not-yet-posted ones to #botland
           as a plain message with a code-blocked card, then add the reaction
           options ✅ Approve, ❌ Reject, ⏭ Skip. Records the resulting
           message_id in data/automation/proposal_message_index.jsonl so we
           don't double-post on re-run.

  poll     Walk the message index → for each unresolved card, hit the
           Discord API for that message's reactions. First non-bot
           reaction wins; record it to
           data/automation/proposal_decisions.jsonl + mark the index entry
           resolved. Also edits the original message to append the resolution
           line so the channel shows the outcome.

  apply    Read decisions.jsonl, dispatch each approve to the matching
           applier (article-edit / dedup / media), write to vault, mark
           consumed in data/automation/proposal_decisions_consumed.jsonl.

  status   Counts: proposals available / posted / decided / consumed /
           pending.

Why this shape:
  - Discord's "one gateway WebSocket per token" rule means we can't run a
    second bot on Hermes' token. But the REST API is unlimited and we
    can post messages + add reactions + read reactions via HTTP only.
  - Reactions instead of buttons because external code can't post message
    components without owning a gateway connection.
  - Polling (instead of receiving reaction events) keeps this script free
    of any WebSocket dependency. Hermes cron runs `poll` every N minutes.

Token lookup order:
  1. $DISCORD_BOT_TOKEN
  2. line `DISCORD_BOT_TOKEN=...` in /home/kyle/.hermes/.env
  3. line `DISCORD_TOKEN=...` in /home/kyle/.hermes/.env

Channel/guild are baked in via constants below (can be overridden by env).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import vault_automation as va  # noqa: E402

ROOT = va.ROOT
VAULT = va.VAULT
PROPOSALS_DIR = va.AUTOMATION_DIR / "proposals"
INDEX_PATH = va.AUTOMATION_DIR / "proposal_message_index.jsonl"
DECISIONS = va.AUTOMATION_DIR / "proposal_decisions.jsonl"
CONSUMED = va.AUTOMATION_DIR / "proposal_decisions_consumed.jsonl"

DEFAULT_CHANNEL_ID = "1474990458844348630"     # #botland in DFRPG Arden Vul guild
DEFAULT_GUILD_ID   = "1474287012482646088"
HERMES_ENV         = Path("/home/kyle/.hermes/.env")
DISCORD_API_BASE   = "https://discord.com/api/v10"

# Reaction emoji used for the three decisions.
REACTION_APPROVE = "✅"
REACTION_REJECT  = "❌"
REACTION_SKIP    = "⏭"
REACTION_TO_DECISION = {
    REACTION_APPROVE: "approve",
    REACTION_REJECT:  "reject",
    REACTION_SKIP:    "skip",
}


# ---------- token + HTTP ----------

def load_token() -> str:
    import os
    if os.environ.get("DISCORD_BOT_TOKEN"):
        return os.environ["DISCORD_BOT_TOKEN"]
    if HERMES_ENV.exists():
        for line in HERMES_ENV.read_text().splitlines():
            for key in ("DISCORD_BOT_TOKEN", "DISCORD_TOKEN"):
                m = re.match(rf"\s*{key}\s*=\s*(.+?)\s*$", line)
                if m:
                    v = m.group(1).strip().strip('"').strip("'")
                    if v:
                        return v
    raise SystemExit("DISCORD_BOT_TOKEN not found (env or ~/.hermes/.env)")


def discord_request(method: str, path: str, token: str, body: dict | None = None,
                    retries: int = 3) -> dict | list | None:
    url = DISCORD_API_BASE + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "ArdenVulVaultProposals (rest-only, +local)",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    last_err: Exception | None = None
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
                if r.status == 204 or not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Rate limit: respect retry-after
            if e.code == 429:
                try:
                    payload = json.loads(e.read().decode("utf-8"))
                    delay = float(payload.get("retry_after", 1.0))
                except Exception:
                    delay = 1.0
                time.sleep(delay + 0.2)
                continue
            if e.code in (502, 503, 504):
                time.sleep(1.0 * (attempt + 1))
                last_err = e
                continue
            # Bubble up — caller decides how to log.
            try:
                msg = e.read().decode("utf-8")
            except Exception:
                msg = ""
            raise RuntimeError(f"Discord API {method} {path} → HTTP {e.code}: {msg[:300]}") from e
        except urllib.error.URLError as e:
            last_err = e
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Discord API {method} {path} failed after {retries} retries: {last_err}")


# ---------- proposal loading ----------

def load_article_edit_proposals() -> list[dict]:
    p = PROPOSALS_DIR / "article_edit_proposals.json"
    return json.loads(p.read_text()) if p.exists() else []


def load_media_ingestion_proposals() -> list[dict]:
    p = PROPOSALS_DIR / "media_ingestion_proposals.json"
    if not p.exists():
        return []
    return [pr for pr in json.loads(p.read_text()) if pr.get("include")]


def _media_pid(pr: dict) -> str:
    key = pr.get("local_path") or pr.get("absolute_path") or ""
    return "media-" + hashlib.sha1(key.encode()).hexdigest()[:12]


def proposal_kind(p: dict) -> str:
    if p.get("addition_type") in {"append_bullet_to_section", "add_alias", "extend_summary"}:
        return "article_edit"
    if p.get("vault_attachment_path"):
        return "media"
    return "unknown"


def all_proposals_indexed() -> dict[str, tuple[str, dict]]:
    out: dict[str, tuple[str, dict]] = {}
    for p in load_article_edit_proposals():
        pid = p.get("proposal_id")
        if pid:
            out[pid] = ("article_edit", p)
    for p in load_media_ingestion_proposals():
        pid = _media_pid(p)
        out[pid] = ("media", dict(p, proposal_id=pid))
    return out


# ---------- state files ----------

def load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    with p.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def append_jsonl(p: Path, rec: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def index_load() -> dict[str, dict]:
    """proposal_id → latest index record."""
    out: dict[str, dict] = {}
    for rec in load_jsonl(INDEX_PATH):
        pid = rec.get("proposal_id")
        if pid:
            out[pid] = rec
    return out


def decisions_load() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for rec in load_jsonl(DECISIONS):
        pid = rec.get("proposal_id")
        if pid:
            out[pid] = rec
    return out


def consumed_load() -> set[str]:
    return {r["proposal_id"] for r in load_jsonl(CONSUMED) if r.get("proposal_id")}


# ---------- post (card creation) ----------

def _section_excerpt(article_path: str, section: str, max_chars: int = 300) -> str:
    """Return the current content of a section in a vault page, or empty string."""
    if not article_path or not section:
        return ""
    path = ROOT / article_path
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"(?m)^## {re.escape(section)}\s*$", text)
    if not m:
        return "(section not yet present)"
    start = m.end()
    next_h2 = re.search(r"(?m)^## ", text[start:])
    end = (start + next_h2.start()) if next_h2 else len(text)
    content = text[start:end].strip()
    return _clip(content, max_chars) if content else "(empty)"


def render_card_text(p: dict) -> str:
    """One Discord message body. Markdown allowed; under 2000 chars."""
    kind = p.get("kind") or p.get("article_kind") or "Proposal"
    pid = p.get("proposal_id") or p.get("id") or "?"
    target = p.get("article_path") or p.get("target_page") or ""
    section = p.get("target_section") or p.get("section") or ""
    is_media = bool(p.get("vault_attachment_path") or p.get("absolute_path"))

    lines = []

    if is_media:
        title = p.get("entity") or p.get("filename") or "?"
        lines.append(f"**[{kind}] {title}** — `{pid}`")
        from_parts = [f"#{p['channel']}" if p.get("channel") else None,
                      p.get("author") or None,
                      (p.get("timestamp") or "")[:10] or None]
        from_str = " · ".join(x for x in from_parts if x)
        if from_str:
            lines.append(f"**From:** {from_str}")
        if target:
            lines.append(f"**Target:** `{target}`" + (f" → §`{section}`" if section else ""))
        caption = (p.get("caption") or "").strip()
        if caption:
            lines.append(f"**Caption:** {_clip(caption, 200)}")
        reason = (p.get("vision_reason") or p.get("reason") or "").strip()
        if reason and reason != caption:
            lines.append(f"**Reason:** {_clip(reason, 200)}")
        ctx = (p.get("discord_context") or "").strip()
        if ctx:
            # Keep only lines around the target message marker, max 5 lines
            ctx_lines = ctx.splitlines()
            target_idx = next((i for i, l in enumerate(ctx_lines) if "◀ THIS MESSAGE" in l), None)
            if target_idx is not None:
                lo = max(0, target_idx - 2)
                hi = min(len(ctx_lines), target_idx + 2)
                ctx_lines = ctx_lines[lo:hi]
            ctx_trimmed = "\n".join(f"> {l}" for l in ctx_lines[:5])
            lines.append(f"**Context:**\n{_clip(ctx_trimmed, 500)}")
    else:
        title = p.get("article_title") or p.get("title") or p.get("filename") or "Proposal"
        addition_type = p.get("addition_type") or ""
        lines.append(f"**[{kind}] {title}** — `{pid}`")
        if target:
            lines.append(f"**Target:** `{target}`" + (f" → §`{section}`" if section else ""))
        if addition_type:
            lines.append(f"**Edit:** {addition_type}")
        body = (p.get("proposed_text") or "").strip()
        if body:
            lines.append(f"**Proposed:**\n```md\n{_clip(body, 400)}\n```")
        cur = _section_excerpt(target, section, max_chars=250)
        if cur:
            lines.append(f"**Current §{section}:**\n```\n{cur}\n```")
        rationale = (p.get("rationale") or "").strip()
        if rationale:
            lines.append(f"**Rationale:** {_clip(rationale, 300)}")
        sources = p.get("sources") or []
        for s in sources[:1]:
            excerpt = (s.get("excerpt") or "").strip()
            if excerpt:
                lines.append(f"**Source:** `{s.get('path','?')}` > {_clip(excerpt, 200)}")

    lines.append(f"\nReact: {REACTION_APPROVE} approve · {REACTION_REJECT} reject · {REACTION_SKIP} skip")
    return "\n".join(lines)[:1990]


def _clip(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 3] + "..."


_DISCORD_IMG_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}
_DISCORD_MAX_DIM  = 1024
_DISCORD_MAX_BYTES = 8 * 1024 * 1024


def _resize_for_discord(path: Path) -> bytes | None:
    """Return JPEG bytes resized for Discord upload, or None if not an image."""
    ext = path.suffix.lower().lstrip(".")
    if ext not in _DISCORD_IMG_EXTS:
        return None
    try:
        from PIL import Image
        import io
        with Image.open(path) as img:
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            w, h = img.size
            if max(w, h) > _DISCORD_MAX_DIM:
                scale = _DISCORD_MAX_DIM / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
    except Exception:
        return None


def discord_post_with_file(channel_id: str, token: str, text: str,
                           file_data: bytes, filename: str) -> dict | None:
    """POST a Discord message with an image attachment (multipart/form-data)."""
    import uuid
    boundary = uuid.uuid4().hex
    CRLF = b"\r\n"
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += b'Content-Disposition: form-data; name="payload_json"\r\n'
    body += b'Content-Type: application/json\r\n\r\n'
    body += json.dumps({"content": text}).encode()
    body += CRLF
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="files[0]"; filename="{filename}"\r\n'.encode()
    body += b"Content-Type: image/jpeg\r\n\r\n"
    body += file_data
    body += CRLF
    body += f"--{boundary}--\r\n".encode()
    url = f"{DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "ArdenVulVaultProposals (rest-only, +local)",
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                delay = float(json.loads(e.read()).get("retry_after", 1.0))
                time.sleep(delay + 0.2)
                continue
            raise RuntimeError(f"Discord upload HTTP {e.code}: {e.read()[:200]}") from e
    return None


def cmd_post(args):
    token = load_token()
    proposals = all_proposals_indexed()
    index = index_load()
    consumed = consumed_load()

    pending = []
    for pid, (_kind, p) in proposals.items():
        if pid in index:
            continue
        if pid in consumed:
            continue
        pending.append(p)
    if args.limit:
        pending = pending[: args.limit]
    print(f"posting {len(pending)} new proposal(s) to channel {args.channel_id}")

    for p in pending:
        pid = p.get("proposal_id") or p.get("id")
        text = render_card_text(p)
        # For image proposals, attach the file so it renders inline in Discord.
        img_data = None
        img_name = None
        abs_path = p.get("absolute_path")
        if abs_path:
            img_data = _resize_for_discord(Path(abs_path))
            if img_data:
                img_name = Path(abs_path).stem[:80] + ".jpg"
        try:
            if img_data:
                msg = discord_post_with_file(args.channel_id, token, text, img_data, img_name)
            else:
                msg = discord_request("POST", f"/channels/{args.channel_id}/messages",
                                      token, {"content": text})
        except RuntimeError as e:
            print(f"  ERR  {pid}: {e}")
            continue
        if not msg or "id" not in msg:
            print(f"  ERR  {pid}: post returned no id")
            continue
        mid = msg["id"]
        # Add reactions (encode emoji as URL-percent so it survives the URL).
        for emoji in (REACTION_APPROVE, REACTION_REJECT, REACTION_SKIP):
            enc = urllib.parse.quote(emoji)
            try:
                discord_request("PUT",
                                f"/channels/{args.channel_id}/messages/{mid}/reactions/{enc}/@me",
                                token)
            except RuntimeError as e:
                print(f"  WARN add-reaction {pid}/{emoji}: {e}")
            time.sleep(0.25)
        append_jsonl(INDEX_PATH, {
            "proposal_id": pid,
            "channel_id": args.channel_id,
            "message_id": mid,
            "posted_at": datetime.now(timezone.utc).isoformat(),
            "kind": proposal_kind(p),
        })
        print(f"  OK   {pid} → message {mid}")
        time.sleep(0.4)
    return 0


# ---------- poll (reactions → decisions) ----------

def cmd_poll(args):
    token = load_token()
    allowed = set(x.strip() for x in (args.allowed_users or "").split(",") if x.strip())
    index = index_load()
    decisions = decisions_load()

    to_check = [(pid, rec) for pid, rec in index.items() if pid not in decisions]
    if args.limit:
        to_check = to_check[: args.limit]
    print(f"polling {len(to_check)} undecided message(s)")

    for pid, rec in to_check:
        cid = rec["channel_id"]
        mid = rec["message_id"]
        chosen_decision = None
        chosen_user = None
        for emoji, decision in REACTION_TO_DECISION.items():
            enc = urllib.parse.quote(emoji)
            try:
                users = discord_request("GET",
                                        f"/channels/{cid}/messages/{mid}/reactions/{enc}",
                                        token) or []
            except RuntimeError as e:
                print(f"  ERR {pid} reading {emoji}: {e}")
                continue
            # Filter out the bot itself
            human_users = [u for u in users if not u.get("bot")]
            if allowed:
                human_users = [u for u in human_users if str(u.get("id")) in allowed]
            if human_users:
                chosen_decision = decision
                chosen_user = human_users[0]
                break
            time.sleep(0.2)
        if not chosen_decision:
            continue
        append_jsonl(DECISIONS, {
            "proposal_id": pid,
            "decision": chosen_decision,
            "user_id": str(chosen_user.get("id")),
            "user_name": chosen_user.get("username") or chosen_user.get("global_name") or "",
            "ts": datetime.now(timezone.utc).isoformat(),
            "extra": {"message_id": mid, "channel_id": cid},
        })
        # Edit the message to mark resolved
        tag = {"approve": "✅ Approved", "reject": "❌ Rejected", "skip": "⏭ Skipped"}[chosen_decision]
        try:
            current = discord_request("GET", f"/channels/{cid}/messages/{mid}", token)
            new_content = (current or {}).get("content", "")
            if "\n\n— " not in new_content:
                new_content = new_content + f"\n\n— **{tag}** by {chosen_user.get('username','?')} · {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                discord_request("PATCH", f"/channels/{cid}/messages/{mid}", token,
                                {"content": new_content[:1990]})
        except RuntimeError as e:
            print(f"  WARN edit {pid}: {e}")
        print(f"  → {pid}: {chosen_decision} by {chosen_user.get('username')}")
        time.sleep(0.3)
    return 0


# ---------- apply (decisions → vault edits) ----------

def apply_article_edit(proposal: dict, apply: bool) -> tuple[str, str]:
    article_path = proposal.get("article_path")
    if not article_path:
        return "skipped", "no article_path"
    target = ROOT / article_path
    if not target.exists():
        return "error", f"target missing: {article_path}"
    text = target.read_text(encoding="utf-8")
    new_text = text
    add_type = proposal.get("addition_type")
    section = proposal.get("target_section") or ""
    body = proposal.get("proposed_text") or ""
    if add_type == "append_bullet_to_section":
        header_re = re.compile(rf"(?m)^## {re.escape(section)}\s*$")
        m = header_re.search(new_text)
        if not m:
            return "error", f"section '## {section}' not found"
        start = m.end()
        next_h2 = re.search(r"(?m)^## ", new_text[start:])
        end = (start + next_h2.start()) if next_h2 else len(new_text)
        section_block = new_text[start:end].rstrip()
        bullet = body if body.lstrip().startswith("-") else f"- {body.lstrip('- ').strip()}"
        section_block = section_block + "\n" + bullet
        new_text = new_text[:start].rstrip() + "\n" + section_block.lstrip("\n") + "\n" + new_text[end:].lstrip("\n")
    elif add_type == "add_alias":
        alias = body.strip().strip('"').strip("'")
        m = re.match(r"^(---\n.*?\n---\n)", new_text, flags=re.S)
        if not m:
            return "error", "no frontmatter"
        fm = m.group(1)
        tail = new_text[len(fm):]
        if re.search(r"^aliases:\s*\n", fm, flags=re.M):
            new_fm = re.sub(
                r"(^aliases:\s*\n(?:\s*-\s*[^\n]+\n)*)",
                lambda mm: mm.group(1) + f"  - {alias}\n", fm, count=1, flags=re.M,
            )
        else:
            new_fm = fm[: -len("---\n")] + f"aliases:\n  - {alias}\n---\n"
        new_text = new_fm + tail
    elif add_type == "extend_summary":
        sm = re.search(r"^## Summary\s*\n(.*?)(?=^## |\Z)", new_text, flags=re.M | re.S)
        if not sm:
            return "error", "no Summary section"
        new_block = sm.group(1).rstrip() + "\n" + body.strip() + "\n\n"
        new_text = new_text[: sm.start(1)] + new_block + new_text[sm.end():]
    else:
        return "error", f"unsupported addition_type: {add_type}"

    if new_text == text:
        return "noop", "no change"
    if apply:
        target.write_text(new_text, encoding="utf-8")
    return "applied" if apply else "would-apply", article_path


_MEDIA_IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "gif"}


def _inject_media_reference(target_path: Path, vault_path: str, pr: dict, apply: bool) -> None:
    """Insert ![[…]] (images) or [[…]] (binaries) under the target section."""
    text = target_path.read_text(encoding="utf-8")
    rel = vault_path[len("vault/"):] if vault_path.startswith("vault/") else vault_path
    ext = pr.get("ext", "").lower()
    if ext in _MEDIA_IMAGE_EXTS:
        line = f"- ![[{rel}]] — {pr.get('caption') or pr.get('filename', '')}"
    else:
        line = f"- [[{rel}|{pr.get('filename', rel.split('/')[-1])}]]"
    section = pr.get("target_section") or "Reference Images"
    header_re = re.compile(rf"(?m)^## {re.escape(section)}\s*$")
    if header_re.search(text):
        new = header_re.sub(rf"## {section}\n{line}", text, count=1)
    else:
        text = text if text.endswith("\n") else text + "\n"
        new = text + f"\n## {section}\n\n{line}\n"
    if apply:
        target_path.write_text(new, encoding="utf-8")


def apply_media_proposal(proposal: dict, apply: bool) -> tuple[str, str]:
    src = Path(proposal.get("absolute_path") or "")
    vault_path = proposal.get("vault_attachment_path") or ""
    target_page = proposal.get("target_page") or ""
    if not vault_path:
        return "error", "no vault_attachment_path"
    if not src.exists():
        return "error", f"source missing: {src}"
    dst = ROOT / vault_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    to_stage: list[str] = []
    if apply:
        shutil.copy2(src, dst)
        to_stage.append(vault_path)
    if target_page:
        target_path = ROOT / target_page
        if target_path.exists():
            _inject_media_reference(target_path, vault_path, proposal, apply=apply)
            if apply:
                to_stage.append(target_page)
    if apply and to_stage:
        r = subprocess.run(["git", "-C", str(ROOT), "add"] + to_stage,
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  WARN git add: {r.stderr.strip()}", file=sys.stderr)
        else:
            commit_msg = f"media: ingest {proposal.get('filename', vault_path.split('/')[-1])}"
            r2 = subprocess.run(["git", "-C", str(ROOT), "commit", "-m", commit_msg],
                                capture_output=True, text=True)
            if r2.returncode != 0 and "nothing to commit" not in r2.stdout:
                print(f"  WARN git commit: {r2.stderr.strip()}", file=sys.stderr)
    return ("applied" if apply else "would-apply"), vault_path


DISPATCH: dict[str, Callable[[dict, bool], tuple[str, str]]] = {
    "article_edit": apply_article_edit,
    "media": apply_media_proposal,
}


def cmd_apply(args):
    proposals = all_proposals_indexed()
    decisions = decisions_load()
    consumed = consumed_load()
    stats = {"approve": 0, "reject": 0, "skip": 0,
             "applied": 0, "noop": 0, "errors": 0, "already_consumed": 0}
    for pid, dec in decisions.items():
        if pid in consumed:
            stats["already_consumed"] += 1
            continue
        decision = dec.get("decision")
        if decision in ("reject", "skip"):
            stats[decision] += 1
            append_jsonl(CONSUMED, {"proposal_id": pid, "decision": decision,
                                    "result": "declined",
                                    "ts": datetime.now(timezone.utc).isoformat()})
            continue
        if decision != "approve":
            continue
        stats["approve"] += 1
        entry = proposals.get(pid)
        if not entry:
            append_jsonl(CONSUMED, {"proposal_id": pid, "decision": decision,
                                    "result": "orphan",
                                    "ts": datetime.now(timezone.utc).isoformat()})
            stats["errors"] += 1
            continue
        kind, prop = entry
        applier = DISPATCH.get(kind)
        if applier is None:
            append_jsonl(CONSUMED, {"proposal_id": pid, "decision": decision,
                                    "result": f"no-applier:{kind}",
                                    "ts": datetime.now(timezone.utc).isoformat()})
            stats["errors"] += 1
            continue
        result, detail = applier(prop, apply=args.apply)
        print(f"  {result:<12} {pid} → {detail}")
        if result == "applied":
            stats["applied"] += 1
        elif result == "noop":
            stats["noop"] += 1
        else:
            stats["errors"] += 1
        if args.apply or result == "noop":
            append_jsonl(CONSUMED, {"proposal_id": pid, "decision": decision,
                                    "result": result, "detail": detail,
                                    "ts": datetime.now(timezone.utc).isoformat()})
    print(f"\n{stats}")
    if not args.apply:
        print("(dry-run; pass --apply to write changes)")
    return 0


# ---------- status ----------

def cmd_status(args):
    proposals = all_proposals_indexed()
    index = index_load()
    decisions = decisions_load()
    consumed = consumed_load()
    pending_post = [pid for pid in proposals if pid not in index and pid not in consumed]
    pending_decision = [pid for pid in index if pid not in decisions and pid not in consumed]
    print(f"proposals available: {len(proposals)}")
    print(f"  posted to discord: {len(index)}")
    print(f"  pending post: {len(pending_post)}")
    print(f"decisions recorded: {len(decisions)}")
    print(f"  pending user reaction: {len(pending_decision)}")
    print(f"consumed by apply: {len(consumed)}")
    if args.show_pending:
        if pending_post:
            print("\nfirst 10 unposted:")
            for pid in pending_post[:10]:
                _, p = proposals[pid]
                label = p.get("article_title") or p.get("filename") or "?"
                body = (p.get("proposed_text") or p.get("caption") or "")[:80]
                print(f"  {pid}  {label}: {body}")
        if pending_decision:
            print("\nfirst 10 awaiting decision:")
            for pid in pending_decision[:10]:
                _, p = proposals.get(pid, ("?", {}))
                label = p.get("article_title") or p.get("filename") or "?"
                print(f"  {pid}  {label}  msg_id={index[pid].get('message_id')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_post = sub.add_parser("post")
    p_post.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    p_post.add_argument("--limit", type=int, default=0)
    p_post.set_defaults(func=cmd_post)

    p_poll = sub.add_parser("poll")
    p_poll.add_argument("--allowed-users", default="",
                        help="Comma-separated Discord user IDs; empty = anyone in channel")
    p_poll.add_argument("--limit", type=int, default=0)
    p_poll.set_defaults(func=cmd_poll)

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--apply", action="store_true",
                         help="Write changes to vault (default dry-run)")
    p_apply.set_defaults(func=cmd_apply)

    p_status = sub.add_parser("status")
    p_status.add_argument("--show-pending", action="store_true")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
