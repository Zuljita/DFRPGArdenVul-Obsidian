#!/usr/bin/env python3
"""
LCE helper (dry-run by default):
- Collects session windows mentioning a target location
- Screens windows for connections (YES/NO)
- Extracts edges/routes (A -> B [via/method/feature])
- Attempts canonical mapping to vault/locations files (and aliases)
- Prints suggested Connections bullets + Sources for review

Requires a local OpenAI-compatible endpoint (LM Studio):
  export LLM_ENDPOINT=http://192.168.21.76:1234/v1/chat/completions
  export LLM_MODEL=qwen2.5-7b-instruct

Usage examples:
  python3 scripts/lce_extract.py --location "Great Cavern" --dry-run
  python3 scripts/lce_extract.py --session "vault/sessions/Session 32 - Fast Exploration.md" --location "Arena" --dry-run
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

DEFAULT_ENDPOINT = os.environ.get("LLM_ENDPOINT", "http://192.168.21.76:1234/v1/chat/completions")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "qwen2.5-7b-instruct")

# Resolve repository root relative to this script so it works from any CWD
ROOT = Path(__file__).resolve().parents[1]

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return p.read_text(errors="ignore")

def list_location_files(root: Path) -> Dict[str, Path]:
    loc_dir = root / "vault" / "locations"
    out = {}
    for p in loc_dir.glob("*.md"):
        name = p.stem
        out[name.lower()] = p
    return out

def load_aliases_for_locations(root: Path) -> Dict[str, Path]:
    loc_dir = root / "vault" / "locations"
    alias_map: Dict[str, Path] = {}
    for p in loc_dir.glob("*.md"):
        txt = read_text(p)
        # frontmatter alias block
        m = re.search(r"^---\n.*?\n---", txt, re.S | re.M)
        if not m:
            continue
        fm = m.group(0)
        # crude parse: lines after 'aliases:' that start with '-' or '  -'
        if "aliases:" not in fm:
            continue
        block = fm.split("aliases:", 1)[1]
        for line in block.splitlines()[1:]:
            if re.match(r"\s*-\s*", line):
                alias = re.sub(r"^\s*-\s*", "", line).strip()
                if alias:
                    alias_map[alias.lower()] = p
            else:
                break
    return alias_map

def split_paragraphs(text: str) -> List[str]:
    paras = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paras if p.strip()]

CONNECT_RE = re.compile(r"\b(connect|lead|via|through|across|toward|into|onto|to|from|down|up|entrance|exit|gate|basket|rappel|levitat|teleport|stair|hole)\b", re.I)

def collect_windows_for_location(root: Path, location: str, session_path: Path = None, para_window: int = 1, full_context: bool = False) -> List[Tuple[Path, str]]:
    windows: List[Tuple[Path, str]] = []
    sessions_dir = root / "vault" / "sessions"
    loc_pat = re.compile(re.escape(location), re.I)
    link_pat = re.compile(r"\[\[([^\]]+)\]\]")
    files = [session_path] if session_path else list(sessions_dir.glob("*.md"))
    for p in files:
        if not p or not p.exists():
            continue
        txt = read_text(p)
        paras = split_paragraphs(txt)
        if full_context:
            chunk = "\n\n".join(paras)
            if CONNECT_RE.search(chunk):
                windows.append((p, chunk))
        else:
            for i, para in enumerate(paras):
                if loc_pat.search(para) or any(location.lower() in m.group(1).lower() for m in link_pat.finditer(para)):
                    # Grab context window of +- N paragraphs
                    lo = max(0, i-para_window)
                    hi = min(len(paras), i+para_window+1)
                    chunk = "\n\n".join(paras[lo:hi])
                    if CONNECT_RE.search(chunk):
                        windows.append((p, chunk))
    return windows

def call_llm(endpoint: str, model: str, system: str, user: str, temperature: float, max_tokens: int) -> str:
    import urllib.request
    data = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(endpoint, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8")
        j = json.loads(body)
        return j["choices"][0]["message"]["content"].strip()

YESNO_SYS = "Answer YES or NO only."
YESNO_USER_TMPL = (
    "Does this text segment describe movement or explicit connections between named locations (including multi-step routes)? "
    "Answer only YES or NO.\n\n{chunk}"
)

EXTRACT_SYS = "Extract connections only. No invention. Use names exactly as in text."
EXTRACT_USER_TMPL = (
    "From the text, extract ONLY explicit connections between named locations and multi-step routes. "
    "Output two sections:\n"
    "1) Edges: one per line as 'A -> B [via X if stated] [method: M if stated] [feature: F if stated]'.\n"
    "2) Routes: one per line as 'A -> B -> C ...' including [via/method/feature] after the hop where the text states it.\n"
    "Use Title Case for names exactly as they appear; do not invent or normalize; exclude non-locations. No extra commentary.\n\n{chunk}"
)

def parse_edges(text: str) -> List[str]:
    lines = [l.strip("- ") for l in text.splitlines() if "->" in l]
    # Best-effort keepers only
    return [l for l in lines if "->" in l]

def build_mapping(root: Path) -> Dict[str, Path]:
    files = list_location_files(root)
    aliases = load_aliases_for_locations(root)
    mapping = {}
    mapping.update(files)
    mapping.update(aliases)
    return mapping

def canonicalize(name: str) -> str:
    return name.strip().strip("[]").strip().lower()

def map_name(name: str, mapping: Dict[str, Path]) -> Tuple[str, Path]:
    key = canonicalize(name)
    # exact match by display name
    if key in mapping:
        return (name, mapping[key])
    # try common 'locations/' prefix removal
    key2 = key.replace("locations/", "").strip()
    if key2 in mapping:
        return (name, mapping[key2])
    return (name, None)

def to_wikilink(p: Path) -> str:
    return f"[[{p.stem}]]"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--location", help="Target location name (Title Case)")
    ap.add_argument("--session", help="Optional single session file to scan")
    ap.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument("--para-window", type=int, default=1, help="Context paragraphs on each side (default: 1)")
    ap.add_argument("--full-context", action="store_true", help="Use entire session text for extraction")
    args = ap.parse_args()

    # Use repo root resolved from this script
    root = ROOT
    if not args.location:
        print("--location is required", file=sys.stderr)
        sys.exit(2)

    session_path = Path(args.session) if args.session else None
    windows = collect_windows_for_location(root, args.location, session_path, para_window=args.para_window, full_context=args.full_context)
    if not windows:
        print("No candidate windows found with connectors.")
        sys.exit(0)

    mapping = build_mapping(root)
    edges_accum: List[Tuple[Path, str]] = []

    for p, chunk in windows:
        yn = call_llm(args.endpoint, args.model, YESNO_SYS, YESNO_USER_TMPL.format(chunk=chunk), 0.1, 10)
        if yn.strip().upper().startswith("Y"):
            extracted = call_llm(args.endpoint, args.model, EXTRACT_SYS, EXTRACT_USER_TMPL.format(chunk=chunk), 0.1, 500)
            for line in parse_edges(extracted):
                edges_accum.append((p, line))

    if not edges_accum:
        print("No edges extracted.")
        sys.exit(0)

    print("# LCE Suggestions (dry-run)")
    print(f"Location: {args.location}")
    print()
    print("## Proposed Connections (mapped where possible)")
    sources = set()
    for p, line in edges_accum:
        sources.add(p)
        # attempt mapping of endpoints (best-effort: split on '->' and brackets)
        parts = [x.strip() for x in line.split('->')]
        if len(parts) >= 2:
            left = re.split(r"\[via|\[method|\[feature", parts[0])[0].strip()
            right_part = parts[1]
            right = re.split(r"\[via|\[method|\[feature", right_part)[0].strip()
            _, lp = map_name(left, mapping)
            _, rp = map_name(right, mapping)
            left_w = to_wikilink(lp) if lp else left
            right_w = to_wikilink(rp) if rp else right
            # Preserve annotation suffix
            suffix = right_part[len(re.split(r"\[via|\[method|\[feature", right_part)[0]):].strip()
            if suffix:
                print(f"- {left_w} -> {right_w} {suffix}")
            else:
                print(f"- {left_w} -> {right_w}")
        else:
            print(f"- {line}")

    print()
    print("## Sources")
    for s in sorted(sources):
        rel = s.as_posix()
        name = s.stem
        print(f"- [[{rel}|{name}]]")

if __name__ == "__main__":
    main()
