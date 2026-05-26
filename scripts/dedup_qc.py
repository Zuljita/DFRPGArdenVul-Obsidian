#!/usr/bin/env python3
"""Vault-wide duplicate detection + rules-RAG quality check.

Subcommands:
  propose-dedup           Cluster candidate-duplicate articles (alias overlap,
                          canonical backlinks, title Jaccard, RAG similarity).
  verify-dedup            Send each cluster to the LLM with vault-rag excerpts;
                          classify confirmed | related | not-duplicate.
  apply-dedup             Auto-apply low-risk merges (explicit canonical
                          backlink AND LLM confirmed); write review doc for
                          everything else.

  propose-rules-rag-qc    For each article in items/monsters/spells/concepts,
                          query the DFRPG MechanicsVault rules collection. Flag
                          articles whose top hit is a strong literal/semantic
                          match (likely generic rulebook material).
  verify-rules-rag-qc     LLM classifies each flagged article as
                          campaign-specific or generic-rulebook.

Outputs land under data/automation/proposals/ and never modify vault content
unless `apply-dedup` runs with --apply.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Import existing helpers from vault_automation so we use the same Chroma /
# LLM / embedding plumbing.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import vault_automation as va  # type: ignore

VAULT = va.VAULT
ROOT = va.ROOT
PROPOSALS_DIR = va.AUTOMATION_DIR / "proposals"
PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

# Folders we treat as articles eligible for dedup. notes/ excluded because
# Discord summaries, recording notes, etc. are not entity pages.
ARTICLE_DIRS = ("npcs", "pcs", "locations", "factions", "items", "monsters",
                "spells", "concepts", "lore")

# Folders eligible for the rules-RAG collision check (these are the kinds of
# articles that risk being just generic rulebook material).
RULES_RAG_DIRS = ("items", "monsters", "spells", "concepts")

# Word-set Jaccard threshold for title+alias-based duplicate candidacy.
TITLE_JACCARD_MIN = 0.5
# RAG-distance threshold for content-similarity candidacy. Cosine distance, so
# 0 = identical, 1 = orthogonal. 0.20 is fairly strict but our embeddings are
# good for in-domain text.
RAG_SIMILARITY_MAX_DISTANCE = 0.20
# Rules-RAG flags an article if mechanics_rag_search returns a hit with this
# distance or better.
RULES_RAG_FLAG_DISTANCE = 0.30

# Common English words we ignore when computing title Jaccard so two unrelated
# pages don't cluster just because they share "the", "of", etc.
STOPWORDS = {
    "the", "of", "a", "an", "and", "or", "in", "on", "at", "to", "for",
    "from", "with", "by", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "his", "her",
    "him", "she", "he", "they", "them", "their", "we", "our", "us", "you",
    "your", "i", "my", "me",
}


@dataclass
class Article:
    path: Path                 # absolute
    rel_path: str              # relative to repo root, posix
    folder: str                # top-level vault folder (npcs, items, …)
    title: str
    aliases: list[str]
    tags: list[str]
    body: str
    word_set: frozenset[str]
    canonical_target: str | None  # rel path the article points at, if any

    def as_summary(self) -> dict:
        return {
            "path": self.rel_path,
            "title": self.title,
            "aliases": self.aliases,
            "tags": self.tags,
            "canonical_target": self.canonical_target,
        }


def normalize_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


def parse_article(path: Path) -> Article | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        try:
            text = path.read_text(encoding="latin-1")
        except OSError:
            return None
    fm = va.parse_frontmatter(text)  # returns dict-ish

    # Title: prefer first H1, fall back to filename stem.
    h1 = re.search(r"^# (.+)$", text, flags=re.M)
    title = (h1.group(1).strip() if h1 else path.stem).strip()

    aliases: list[str] = []
    raw_aliases = fm.get("aliases") if isinstance(fm, dict) else None
    if isinstance(raw_aliases, list):
        aliases = [str(a).strip() for a in raw_aliases if str(a).strip()]
    elif isinstance(raw_aliases, str):
        # frontmatter parser may collapse a single-element list
        aliases = [raw_aliases.strip()]

    tags: list[str] = []
    raw_tags = fm.get("tags") if isinstance(fm, dict) else None
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str):
        tags = [raw_tags.strip()]

    # Canonical-target detection: "Canonical page: [[items/Foo.md|Foo]]" or
    # similar. First wikilink after the phrase, normalized to vault-relative.
    canonical_target = None
    m = re.search(r"[Cc]anonical(?:\s+pages?|\s+family\s+page)?[^\n]*?\[\[([^\]|#]+)", text)
    if m:
        canonical_target = m.group(1).strip()
        # Normalize: strip leading vault/, strip .md if absent
        canonical_target = re.sub(r"^vault/", "", canonical_target)

    word_set = frozenset(normalize_words(title) + sum((normalize_words(a) for a in aliases), []))

    rel_path = str(path.relative_to(ROOT)).replace("\\", "/")
    folder = rel_path.split("/")[1] if rel_path.startswith("vault/") else ""

    body = text
    return Article(
        path=path,
        rel_path=rel_path,
        folder=folder,
        title=title,
        aliases=aliases,
        tags=tags,
        body=body,
        word_set=word_set,
        canonical_target=canonical_target,
    )


def load_articles(folders: tuple[str, ...] = ARTICLE_DIRS) -> list[Article]:
    out: list[Article] = []
    for folder in folders:
        root = VAULT / folder
        if not root.exists():
            continue
        for md in sorted(root.rglob("*.md")):
            if md.stem.lower() in {"index", "readme"}:
                continue
            art = parse_article(md)
            if art:
                out.append(art)
    return out


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


# ---------- propose-dedup ----------

@dataclass
class ClusterCandidate:
    members: list[str] = field(default_factory=list)            # rel paths
    signals: list[str] = field(default_factory=list)            # human-readable
    method: set[str] = field(default_factory=set)               # alias|canonical|title|rag
    confidence: str = "low"                                     # high|med|low

    def merge(self, other: "ClusterCandidate") -> None:
        for m in other.members:
            if m not in self.members:
                self.members.append(m)
        for s in other.signals:
            if s not in self.signals:
                self.signals.append(s)
        self.method |= other.method


class ClusterUnion:
    """Union-find over article paths for cluster merging."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.cluster_data: dict[str, ClusterCandidate] = {}

    def add(self, p: str) -> None:
        if p not in self.parent:
            self.parent[p] = p
            self.cluster_data[p] = ClusterCandidate(members=[p])

    def find(self, p: str) -> str:
        self.add(p)
        while self.parent[p] != p:
            self.parent[p] = self.parent[self.parent[p]]
            p = self.parent[p]
        return p

    def union(self, a: str, b: str, signal: str, method: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            cluster = self.cluster_data[ra]
            if signal not in cluster.signals:
                cluster.signals.append(signal)
            cluster.method.add(method)
            return
        self.parent[rb] = ra
        cluster = self.cluster_data[ra]
        cluster.merge(self.cluster_data[rb])
        if signal not in cluster.signals:
            cluster.signals.append(signal)
        cluster.method.add(method)
        del self.cluster_data[rb]

    def clusters(self) -> list[ClusterCandidate]:
        # Roll up: ensure every cluster's members are unique and >=2.
        out = []
        seen_keys = set()
        for root_path, cluster in self.cluster_data.items():
            root = self.find(root_path)
            if root != root_path:
                continue
            if len(set(cluster.members)) < 2:
                continue
            key = tuple(sorted(set(cluster.members)))
            if key in seen_keys:
                continue
            seen_keys.add(key)
            cluster.members = list(key)
            out.append(cluster)
        return out


def _index_to_path(arts: list[Article]) -> dict[str, Article]:
    return {a.rel_path: a for a in arts}


def cluster_by_aliases(arts: list[Article], union: ClusterUnion) -> None:
    """Pages that share an alias (case-insensitive) are duplicate candidates."""
    by_alias: dict[str, list[Article]] = defaultdict(list)
    for art in arts:
        seen = set()
        for a in [art.title, *art.aliases]:
            key = re.sub(r"\s+", " ", a.lower()).strip()
            if key and key not in seen:
                seen.add(key)
                by_alias[key].append(art)
    for alias_key, group in by_alias.items():
        if len(group) < 2:
            continue
        anchor = group[0]
        for other in group[1:]:
            union.union(
                anchor.rel_path,
                other.rel_path,
                signal=f"shared alias '{alias_key}'",
                method="alias",
            )


def cluster_by_canonical_backlink(arts: list[Article], union: ClusterUnion) -> None:
    """If page A says 'Canonical page: [[B]]', cluster A with B."""
    by_path = _index_to_path(arts)
    # Build an index from various path forms used in wikilinks.
    index_by_link: dict[str, str] = {}
    for art in arts:
        # Forms: "items/Foo", "items/Foo.md", "Foo"
        rel_in_vault = art.rel_path[len("vault/"):]  # e.g. items/Foo.md
        no_ext = re.sub(r"\.md$", "", rel_in_vault)
        index_by_link[rel_in_vault.lower()] = art.rel_path
        index_by_link[no_ext.lower()] = art.rel_path
        index_by_link[art.path.stem.lower()] = art.rel_path

    for art in arts:
        if not art.canonical_target:
            continue
        key = art.canonical_target.lower()
        target_rel = (
            index_by_link.get(key)
            or index_by_link.get(re.sub(r"\.md$", "", key))
            or index_by_link.get(key.split("/")[-1])
        )
        if target_rel and target_rel != art.rel_path:
            union.union(
                art.rel_path,
                target_rel,
                signal=f"explicit canonical backlink: '{art.canonical_target}'",
                method="canonical",
            )


def cluster_by_title_jaccard(arts: list[Article], union: ClusterUnion,
                             min_jaccard: float = TITLE_JACCARD_MIN) -> None:
    """O(N^2) over the same folder is fine at vault size."""
    # Group by folder to avoid clustering an NPC with an unrelated item by title.
    # Recording notes are date-stamped and chain by year/month — exclude.
    by_folder: dict[str, list[Article]] = defaultdict(list)
    for art in arts:
        if art.rel_path.startswith("vault/lore/recording-notes/"):
            continue
        by_folder[art.folder].append(art)
    for folder, group in by_folder.items():
        n = len(group)
        for i in range(n):
            a = group[i]
            if not a.word_set:
                continue
            for j in range(i + 1, n):
                b = group[j]
                if not b.word_set:
                    continue
                shared = a.word_set & b.word_set
                # Require at least 2 shared NON-NUMERIC content words —
                # otherwise date-stamped or numbered pages chain on "2025"
                # / "session" / etc.
                non_numeric_shared = {w for w in shared if not w.isdigit()}
                if len(non_numeric_shared) < 2:
                    continue
                jac = jaccard(a.word_set, b.word_set)
                if jac >= min_jaccard:
                    union.union(
                        a.rel_path,
                        b.rel_path,
                        signal=f"title/alias Jaccard {jac:.2f} on {sorted(shared)}",
                        method="title",
                    )


def cluster_by_rag_similarity(arts: list[Article], union: ClusterUnion,
                              max_distance: float = RAG_SIMILARITY_MAX_DISTANCE,
                              top_k: int = 4) -> None:
    """Use the vault-rag Chroma collection to find near-neighbor articles.

    Skips the chunked RAG (which would dominate by sub-section). Uses the
    article title + first H2 paragraph as the query so we're looking for
    pages that match the entity headline, not a deep-buried mention.
    """
    if not va.CHROMA_AVAILABLE:
        print("(skipping RAG similarity: chromadb not available)", file=sys.stderr)
        return

    coll = va.vault_rag_collection()
    by_path = _index_to_path(arts)

    for i, art in enumerate(arts, 1):
        query = build_rag_query(art)
        if not query:
            continue
        try:
            emb = va.vault_rag_embed(query)
        except Exception as e:
            print(f"  embed failed for {art.rel_path}: {e}", file=sys.stderr)
            continue
        try:
            res = coll.query(
                query_embeddings=[emb],
                n_results=top_k * 3,  # we'll filter to articles only
                include=["metadatas", "distances", "documents"],
            )
        except Exception as e:
            print(f"  chroma query failed for {art.rel_path}: {e}", file=sys.stderr)
            continue
        ids = (res.get("ids") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for cid, meta, dist in zip(ids, metas, dists):
            if dist is None or dist > max_distance:
                continue
            # Chunk IDs look like "vault/items/Foo.md#0:abc12345"
            chunk_path = (meta or {}).get("path") or cid.split("#", 1)[0]
            if not chunk_path:
                continue
            chunk_path = chunk_path.replace("\\", "/")
            if not chunk_path.startswith("vault/"):
                continue
            if chunk_path == art.rel_path:
                continue
            target = by_path.get(chunk_path)
            if not target:
                continue
            # Only cluster within the same vault folder — cross-folder RAG hits
            # are usually "this NPC is mentioned in this location" rather than
            # a duplicate.
            if target.folder != art.folder:
                continue
            union.union(
                art.rel_path,
                target.rel_path,
                signal=f"RAG similarity dist={dist:.3f}",
                method="rag",
            )
        if i % 50 == 0:
            print(f"  rag-similarity progress: {i}/{len(arts)}", file=sys.stderr)


def build_rag_query(art: Article) -> str:
    """Use title + first ~400 chars of body (post-frontmatter) as the RAG query."""
    body = va.VAULT_RAG_FRONTMATTER_RE.sub("", art.body)
    body = re.sub(r"^#.*$", "", body, count=1, flags=re.M).strip()
    snippet = body[:400]
    return f"{art.title}\n{snippet}".strip()


def score_cluster(cluster: ClusterCandidate, arts_by_path: dict[str, Article]) -> str:
    """Assign confidence based on signal strength."""
    # High: any alias-collision OR explicit canonical-backlink.
    if "alias" in cluster.method or "canonical" in cluster.method:
        return "high"
    # Med: title Jaccard + RAG both fired.
    if "title" in cluster.method and "rag" in cluster.method:
        return "med"
    # Low: only one of title/rag.
    return "low"


def propose_dedup(args: argparse.Namespace) -> int:
    print("loading articles…")
    arts = load_articles()
    print(f"  {len(arts)} articles across {len(set(a.folder for a in arts))} folders")
    by_path = _index_to_path(arts)
    union = ClusterUnion()
    for art in arts:
        union.add(art.rel_path)

    print("clustering by alias overlap…")
    cluster_by_aliases(arts, union)
    print("clustering by canonical backlink…")
    cluster_by_canonical_backlink(arts, union)
    print("clustering by title/alias Jaccard…")
    cluster_by_title_jaccard(arts, union)
    if not args.skip_rag:
        print("clustering by RAG content similarity (this is the slow step)…")
        cluster_by_rag_similarity(arts, union, top_k=args.rag_top_k)

    clusters = union.clusters()
    print(f"  produced {len(clusters)} candidate clusters")

    # Score & sort
    scored = []
    for cluster in clusters:
        cluster.confidence = score_cluster(cluster, by_path)
        scored.append(cluster)
    scored.sort(key=lambda c: ({"high": 0, "med": 1, "low": 2}[c.confidence], -len(c.members)))

    # Write JSON + Markdown reports.
    json_path = PROPOSALS_DIR / "dedup_clusters.json"
    md_path = PROPOSALS_DIR / "dedup_clusters.md"

    serialized = []
    for c in scored:
        serialized.append({
            "confidence": c.confidence,
            "method": sorted(c.method),
            "signals": c.signals,
            "members": [by_path[p].as_summary() for p in c.members],
        })
    json_path.write_text(json.dumps(serialized, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "# Dedup Candidate Clusters",
        "",
        f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
        f"Total clusters: {len(scored)} "
        f"(high={sum(1 for c in scored if c.confidence=='high')}, "
        f"med={sum(1 for c in scored if c.confidence=='med')}, "
        f"low={sum(1 for c in scored if c.confidence=='low')})",
        "",
        "Confidence: **high** = alias or canonical-backlink signal; **med** = title Jaccard + RAG both fired; **low** = single weaker signal.",
        "",
    ]
    for cluster in scored:
        md_lines.append(f"## [{cluster.confidence}] cluster ({len(cluster.members)} members)")
        md_lines.append("")
        md_lines.append("Signals:")
        for s in cluster.signals:
            md_lines.append(f"  - {s}")
        md_lines.append("")
        md_lines.append("Members:")
        for p in cluster.members:
            art = by_path[p]
            tag_str = ", ".join(f"`{t}`" for t in art.tags)
            alias_str = ", ".join(f"`{a}`" for a in art.aliases) or "—"
            canon_str = f" (→ canonical: `{art.canonical_target}`)" if art.canonical_target else ""
            md_lines.append(f"  - [[{p[len('vault/'):]}|{art.title}]]{canon_str}")
            md_lines.append(f"    - tags: {tag_str or '—'}")
            md_lines.append(f"    - aliases: {alias_str}")
        md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


# ---------- verify-dedup ----------

VERIFIER_SYSTEM = """You are an expert curator for an Obsidian vault that documents an ongoing DFRPG (Dungeon Fantasy Roleplaying Game) campaign in the Arden Vul megadungeon. You are given a set of vault pages that a heuristic flagged as possible duplicates of the same canonical entity (an NPC, item, location, etc.).

Your job is to classify the cluster as one of:
  - confirmed_duplicate: the pages describe the SAME entity and should be merged into one canonical page.
  - related_but_distinct: the pages are about related entities (e.g., a faction and one of its members) but should remain separate pages.
  - not_duplicate: the pages are not about the same thing; the cluster is a false positive.

If confirmed_duplicate, also identify:
  - canonical_path: which member SHOULD be the canonical page (the one others merge INTO). Prefer the most thoroughly-written page, the one with the most aliases / sessions linked, or the one already referenced as canonical by other members.
  - synonyms: which of the other members are the same entity (list of paths).

Output JSON exactly:
{"classification":"confirmed_duplicate|related_but_distinct|not_duplicate","canonical_path":"vault/.../X.md","synonyms":["vault/.../Y.md", ...],"reason":"one short sentence"}
"""


def verify_dedup(args: argparse.Namespace) -> int:
    proposals_path = PROPOSALS_DIR / "dedup_clusters.json"
    if not proposals_path.exists():
        print(f"no proposals at {proposals_path}; run propose-dedup first", file=sys.stderr)
        return 2
    clusters = json.loads(proposals_path.read_text(encoding="utf-8"))
    if args.confidence:
        clusters = [c for c in clusters if c["confidence"] in args.confidence]
    if args.limit:
        clusters = clusters[: args.limit]

    arts = load_articles()
    by_path = _index_to_path(arts)

    verified = []
    for i, cluster in enumerate(clusters, 1):
        member_paths = [m["path"] for m in cluster["members"]]
        members_with_body = []
        for p in member_paths:
            art = by_path.get(p)
            if not art:
                continue
            body = va.VAULT_RAG_FRONTMATTER_RE.sub("", art.body)
            snippet = body[:1500]
            members_with_body.append({
                "path": art.rel_path,
                "title": art.title,
                "tags": art.tags,
                "aliases": art.aliases,
                "snippet": snippet,
            })
        user_prompt = (
            "Heuristic signals that flagged this cluster:\n  - " + "\n  - ".join(cluster["signals"]) +
            "\n\nCluster members:\n\n"
        )
        for m in members_with_body:
            user_prompt += (
                f"--- {m['path']} ---\n"
                f"title: {m['title']}\n"
                f"tags: {m['tags']}\n"
                f"aliases: {m['aliases']}\n"
                f"body (first 1500 chars):\n{m['snippet']}\n\n"
            )
        user_prompt += "Classify per your instructions. Respond with JSON only."

        try:
            content = llm_chat_json(VERIFIER_SYSTEM, user_prompt, max_tokens=4000, temperature=0.1)
        except Exception as e:
            print(f"  cluster {i}: LLM error: {e}", file=sys.stderr)
            continue
        verified.append({
            "cluster_index": i,
            "confidence": cluster["confidence"],
            "method": cluster["method"],
            "signals": cluster["signals"],
            "members": [m["path"] for m in cluster["members"]],
            "verdict": content,
        })
        print(f"  cluster {i}/{len(clusters)} [{cluster['confidence']}] → {content.get('classification','?')}: {content.get('reason','')[:80]}")

    out_path = PROPOSALS_DIR / "dedup_verified.json"
    out_path.write_text(json.dumps(verified, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


def llm_chat_json(system: str, user: str, *, max_tokens: int = 800, temperature: float = 0.1) -> dict:
    """Call the LM Studio gateway and parse the response as JSON. Strips
    triple-backtick fences if present."""
    sources = va.load_local_sources()
    base_url = sources.get("llm_base_url") or "http://100.76.165.94:1234/v1"
    model = sources.get("llm_model") or "google/gemma-4-26b-a4b"
    import urllib.request
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    content = (data["choices"][0]["message"].get("content") or "").strip()
    # Strip code fences.
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```\s*$", "", content)
    # Find the first {...} block.
    m = re.search(r"\{.*\}", content, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"classification": "parse_error", "raw": content[:600]}


# ---------- apply-dedup ----------

def apply_dedup(args: argparse.Namespace) -> int:
    verified_path = PROPOSALS_DIR / "dedup_verified.json"
    if not verified_path.exists():
        print(f"no verified results at {verified_path}; run verify-dedup first", file=sys.stderr)
        return 2
    verified = json.loads(verified_path.read_text(encoding="utf-8"))

    auto_applied: list[dict] = []
    review_needed: list[dict] = []

    for entry in verified:
        verdict = entry.get("verdict", {})
        cls = verdict.get("classification")
        if cls != "confirmed_duplicate":
            continue
        canonical = verdict.get("canonical_path") or ""
        synonyms = verdict.get("synonyms") or []
        if not canonical or not synonyms:
            continue

        # Low-risk gate: high confidence (alias or canonical backlink signal).
        is_low_risk = entry.get("confidence") == "high" and "canonical" in entry.get("method", [])
        if not is_low_risk:
            review_needed.append(entry)
            continue

        # Stage 1: rewrite synonyms into redirect stubs pointing at canonical.
        for syn in synonyms:
            syn_path = ROOT / syn
            if not syn_path.exists():
                continue
            stub = render_redirect_stub(syn_path, canonical)
            if args.apply:
                syn_path.write_text(stub, encoding="utf-8")
            auto_applied.append({"action": "redirect_stub", "from": syn, "to": canonical, "applied": args.apply})

    out = {
        "auto_applied": auto_applied,
        "review_needed_count": len(review_needed),
    }
    review_md = render_review_md(review_needed)
    (PROPOSALS_DIR / "dedup_apply_summary.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (PROPOSALS_DIR / "dedup_review_needed.md").write_text(review_md, encoding="utf-8")
    print(f"auto-applied actions: {len(auto_applied)}   review-needed: {len(review_needed)}")
    if not args.apply:
        print("(dry run — pass --apply to write changes)")
    return 0


def render_redirect_stub(syn_path: Path, canonical_rel: str) -> str:
    art = parse_article(syn_path)
    canonical_link = canonical_rel[len("vault/"):] if canonical_rel.startswith("vault/") else canonical_rel
    canonical_label = Path(canonical_rel).stem
    tags = art.tags if art else []
    aliases = art.aliases if art else []
    title = art.title if art else syn_path.stem
    return (
        "---\n"
        f"title: \"{title}\"\n"
        + ("tags:\n" + "\n".join(f"  - {t}" for t in tags) + "\n" if tags else "")
        + ("aliases:\n" + "\n".join(f"  - {a}" for a in aliases) + "\n" if aliases else "")
        + f"redirect_to: {canonical_rel}\n"
        "status: redirect\n"
        "---\n\n"
        f"# {title}\n\n"
        f"This entry has been merged into the canonical page: [[{canonical_link}|{canonical_label}]].\n"
    )


def render_review_md(entries: list[dict]) -> str:
    lines = ["# Dedup — Review Needed", "",
             f"Total: {len(entries)}", "",
             "These were classified by the verifier as confirmed duplicates, but lacked the explicit-canonical-backlink signal required for auto-merge. Confirm canonical + synonyms by hand.", ""]
    for entry in entries:
        v = entry.get("verdict", {})
        lines.append(f"## cluster #{entry['cluster_index']}  [{entry['confidence']}]")
        lines.append(f"Reason: {v.get('reason','')}")
        lines.append(f"LLM canonical: `{v.get('canonical_path','?')}`")
        lines.append(f"LLM synonyms: {v.get('synonyms', [])}")
        lines.append("Members:")
        for m in entry.get("members", []):
            lines.append(f"  - {m}")
        lines.append("")
    return "\n".join(lines)


# ---------- rules-RAG QC ----------

def propose_rules_rag_qc(args: argparse.Namespace) -> int:
    """For each article in items/monsters/spells/concepts, query MechanicsVault.

    Flag articles whose top hit is within RULES_RAG_FLAG_DISTANCE OR has a
    literal-match signal AND the page title appears verbatim in the rulebook.
    """
    arts = load_articles(folders=RULES_RAG_DIRS)
    print(f"checking {len(arts)} articles against MechanicsVault rules RAG…")
    flagged = []
    for i, art in enumerate(arts, 1):
        try:
            hits = va.mechanics_rag_search(art.title, top_k=3)
        except Exception as e:
            print(f"  {art.rel_path}: mechanics_rag_search error: {e}", file=sys.stderr)
            continue
        if not hits:
            continue
        top = hits[0]
        dist = top.get("distance") if top.get("distance") is not None else 1.0
        is_literal = top.get("match_type") == "literal"
        if is_literal or dist <= RULES_RAG_FLAG_DISTANCE:
            flagged.append({
                "path": art.rel_path,
                "title": art.title,
                "tags": art.tags,
                "top_hit": top,
                "all_hits": hits,
            })
        if i % 25 == 0:
            print(f"  progress: {i}/{len(arts)} ({len(flagged)} flagged so far)", file=sys.stderr)

    out_json = PROPOSALS_DIR / "rules_rag_collisions.json"
    out_md = PROPOSALS_DIR / "rules_rag_collisions.md"
    out_json.write_text(json.dumps(flagged, indent=2, ensure_ascii=False), encoding="utf-8")

    md = ["# Rules-RAG Collisions",
          "",
          f"Generated: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
          f"Articles flagged: {len(flagged)} / {len(arts)} scanned",
          "",
          "These vault pages may be generic DFRPG rulebook material rather than campaign-specific content. The verifier step decides per-page.",
          "",
          "| Path | Title | Match | Book | Page | Section |",
          "| --- | --- | --- | --- | --- | --- |"]
    for f in flagged:
        h = f["top_hit"]
        md.append(
            f"| `{f['path']}` | {f['title']} | "
            f"{h.get('match_type','?')} d={h.get('distance', '—'):.3f} | "
            f"{h.get('book','?')} | {h.get('printed_page','?')} | {h.get('section','?')} |"
            if isinstance(h.get('distance'), float) else
            f"| `{f['path']}` | {f['title']} | {h.get('match_type','?')} | "
            f"{h.get('book','?')} | {h.get('printed_page','?')} | {h.get('section','?')} |"
        )
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"flagged {len(flagged)} articles")
    print(f"wrote {out_json}")
    print(f"wrote {out_md}")
    return 0


RULES_QC_SYSTEM = """You decide whether a vault page is generic DFRPG rulebook material (and therefore should not have its own campaign vault article) or campaign-specific lore (and should remain).

Generic rulebook material includes: published spells from DFA / GURPS Magic, generic monster stat blocks, baseline equipment with no campaign-specific provenance, base game classes, etc.

Campaign-specific includes: items the party discovered or that have campaign provenance, named/customized monsters tied to Arden Vul, unique magic items, spells with campaign-specific origins, factions/concepts.

You are given: (1) the vault article body, (2) the top rulebook RAG hit it semantically matches.

Decide:
  - generic_rulebook: this article is mostly the published rulebook entry and should be removed.
  - campaign_specific: this article is campaign content (keep).
  - hybrid: article mixes generic stat block with campaign provenance; refactor to keep only the provenance and link to rulebook.

Respond with JSON: {"classification":"generic_rulebook|campaign_specific|hybrid","reason":"one short sentence","keep_sections":["section names to retain if hybrid"]}
"""


def verify_rules_rag_qc(args: argparse.Namespace) -> int:
    flagged_path = PROPOSALS_DIR / "rules_rag_collisions.json"
    if not flagged_path.exists():
        print(f"no flagged list at {flagged_path}; run propose-rules-rag-qc first", file=sys.stderr)
        return 2
    flagged = json.loads(flagged_path.read_text(encoding="utf-8"))
    if args.limit:
        flagged = flagged[: args.limit]

    arts = load_articles(folders=RULES_RAG_DIRS)
    by_path = _index_to_path(arts)

    verified = []
    for i, entry in enumerate(flagged, 1):
        art = by_path.get(entry["path"])
        if not art:
            continue
        body = va.VAULT_RAG_FRONTMATTER_RE.sub("", art.body)[:2500]
        hit = entry["top_hit"]
        rag_excerpt = hit.get("text") or hit.get("document") or ""
        rag_meta = f"{hit.get('book','?')} p{hit.get('printed_page','?')} §{hit.get('section','?')}"
        user_prompt = (
            f"Vault article path: {art.rel_path}\n"
            f"Title: {art.title}\n"
            f"Tags: {art.tags}\n"
            f"Aliases: {art.aliases}\n\n"
            f"--- ARTICLE BODY ---\n{body}\n\n"
            f"--- TOP RULEBOOK HIT ({rag_meta}, match={hit.get('match_type')}, "
            f"distance={hit.get('distance')}) ---\n{rag_excerpt[:1500]}\n\n"
            "Classify per your instructions. Respond with JSON only."
        )
        try:
            verdict = llm_chat_json(RULES_QC_SYSTEM, user_prompt, max_tokens=4000, temperature=0.1)
        except Exception as e:
            print(f"  {art.rel_path}: LLM error: {e}", file=sys.stderr)
            continue
        verified.append({
            "path": art.rel_path,
            "title": art.title,
            "top_hit_book": hit.get("book"),
            "top_hit_section": hit.get("section"),
            "top_hit_distance": hit.get("distance"),
            "top_hit_match_type": hit.get("match_type"),
            "verdict": verdict,
        })
        print(f"  {i}/{len(flagged)} {art.rel_path} → {verdict.get('classification','?')}")

    out = PROPOSALS_DIR / "rules_rag_verified.json"
    out.write_text(json.dumps(verified, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pd = sub.add_parser("propose-dedup")
    p_pd.add_argument("--skip-rag", action="store_true",
                      help="Skip the slow RAG-similarity step (alias/canonical/title only)")
    p_pd.add_argument("--rag-top-k", type=int, default=4)
    p_pd.set_defaults(func=propose_dedup)

    p_vd = sub.add_parser("verify-dedup")
    p_vd.add_argument("--confidence", nargs="+", choices=["high", "med", "low"],
                      help="Only verify clusters at these confidence levels")
    p_vd.add_argument("--limit", type=int, default=0)
    p_vd.set_defaults(func=verify_dedup)

    p_ad = sub.add_parser("apply-dedup")
    p_ad.add_argument("--apply", action="store_true",
                      help="Write changes (default is dry-run)")
    p_ad.set_defaults(func=apply_dedup)

    p_pr = sub.add_parser("propose-rules-rag-qc")
    p_pr.set_defaults(func=propose_rules_rag_qc)

    p_vr = sub.add_parser("verify-rules-rag-qc")
    p_vr.add_argument("--limit", type=int, default=0)
    p_vr.set_defaults(func=verify_rules_rag_qc)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
