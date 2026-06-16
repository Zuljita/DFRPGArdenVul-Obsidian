#!/usr/bin/env python3
"""Build a typed location adjacency graph for the Arden Vul vault.

Curated trusted layer + deterministic signal fusion + an optional LLM pass.

Signals (each edge carries provenance + a confidence tier):
  seed        a curated, typed edge from config/location_edges_seed.json --
              the TRUSTED layer, hand-authored from canon; also suppresses
              travel/staging artifacts via its `reject` list
  explicit    bullets under a location page's `## Connections` header
  page-link   a location page body linking to another location page
  travel-seq  consecutive distinct location mentions in a session's prose
  plan        ordered location mentions inside Vallium's (Greybrown's)
              ooc-planning messages  --  PRIVATE, non-citable hint

Confidence tiers:
  confirmed   seed, explicit, >=2 distinct deterministic signals, OR an
              LLM-typed edge with a verbatim vault citation
  candidate   a single non-explicit deterministic signal
  hint        LLM says connected but produced no valid vault citation
  suppressed  on the seed reject list (a travel/staging artifact)

The local LLM pass is OPTIONAL and secondary: its judgement is not trusted on
its own, so the curated seed carries the map. When run, it can only *propose*
a type + a quote that is deterministically checked to appear verbatim in a
real vault file before the edge is promoted.

The LLM pass only ever *proposes/types* edges; a deterministic check that the
cited excerpt appears verbatim in a real `vault/sessions` or
`vault/notes/Discord Summary` file is what makes an edge RAG-eligible. This
honours the source boundary: raw Discord planning can suggest an edge but
cannot, by itself, put it in front of players.

Outputs:
  data/automation/location_graph.json
  vault/notes/Location Map.md     (Mermaid, community-clustered)

Usage:
  python3 scripts/location_graph.py build              # deterministic only
  python3 scripts/location_graph.py build --llm 15      # + verify 15 candidates
  python3 scripts/location_graph.py build --llm 15 --eval   # print LLM eval table
"""
from __future__ import annotations
import argparse, json, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAULT = ROOT / "vault"
OUT_JSON = ROOT / "data" / "automation" / "location_graph.json"
LLM_CACHE = ROOT / "data" / "automation" / "location_graph_llm_cache.json"
SEED_FILE = ROOT / "config" / "location_edges_seed.json"
MAP_NOTE = VAULT / "notes" / "Location Map.md"
NETWORK_NOTE = VAULT / "notes" / "Thothian Teleportation Circle Network.md"

WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")
DIRECTION_RE = re.compile(
    r"\b(north|south|east|west|northeast|northwest|southeast|southwest|up|down|above|below|"
    r"passage|corridor|tunnel|stairs?|ladder|ramp|teleporter|lift|ferry|bridge|door|gate)\b", re.I)
MSG_RE = re.compile(r"^## .*? - (.+?) - \d+\s*$")
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
# generic page names that are too ambiguous for free-text matching
TEXT_STOP = {"arena", "tomb", "tower", "market", "forum", "cave", "caves", "hall",
             "well", "river", "gate", "gates", "road", "lift", "lifts", "inn", "span",
             "vault", "keep", "residence", "donjon", "stair", "stairs", "pit", "shaft"}
SIGNAL_WEIGHT = {"seed": 6, "explicit": 3, "page-link": 1, "travel-seq": 1, "plan": 2}
# Travel cost per edge type (effort/time, not physical distance). Teleporters are
# ~free; a long surface hike is expensive. Overridable per-edge via seed "cost".
TYPE_COST = {"teleporter": 1, "rug": 1, "contains": 1, "region-contains": 1,
             "lift": 2, "ferry": 2, "stairs": 2, "door": 2, "gate": 2,
             "passage": 3, "climb": 4, "road": 6}
DEFAULT_COST = 3


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def norm_contains(haystack: str, needle: str) -> bool:
    n = re.sub(r"\s+", " ", needle).strip().lower()
    return bool(n) and n in re.sub(r"\s+", " ", haystack).strip().lower()


def rollup_root() -> Path:
    cfg = ROOT / "config" / "local_sources.json"
    if cfg.exists():
        root = json.loads(read(cfg)).get("discord_rollup_root")
        if root:
            return Path(root)
    return Path("/home/kyle/discord-chat-explorer/weekly-rollups")


# ---------------------------------------------------------------- lexicon
def frontmatter_aliases(text: str) -> list[str]:
    out: list[str] = []
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return out
    block = m.group(1)
    am = re.search(r"^aliases:\s*\n((?:\s*-\s.*\n?)+)", block, re.M)
    if am:
        out += [re.sub(r"^\s*-\s*", "", ln).strip().strip("\"'")
                for ln in am.group(1).splitlines() if ln.strip().startswith("-")]
    tm = re.search(r"^title:\s*(.+)$", block, re.M)
    if tm:
        out.append(tm.group(1).strip().strip("\"'"))
    return [a for a in out if a]


def build_lexicon():
    aliases: dict[str, set[str]] = {}
    for p in sorted(VAULT.glob("locations/*.md")):
        canon = p.stem
        aliases[canon] = {canon, *frontmatter_aliases(read(p))}
    # Canon-first resolution (matches the API): a page's own name always wins,
    # then aliases fill only the gaps -- so an alias can't shadow a real page.
    link_surface: dict[str, str] = {}
    for canon in aliases:
        link_surface[canon.lower()] = canon
    for canon, names in aliases.items():
        for n in names:
            link_surface.setdefault(n.lower(), canon)
    return aliases, link_surface


def resolve_link(target: str, link_surface: dict[str, str]) -> str | None:
    t = target.strip()
    t = t[len("vault/"):] if t.startswith("vault/") else t
    if t.lower().startswith("locations/"):
        return link_surface.get(Path(t).stem.lower())
    return link_surface.get(Path(t).stem.lower())


def build_text_matcher(aliases):
    surface: dict[str, str] = {}
    for canon, names in aliases.items():
        for n in names:
            key = n.lower()
            if len(key) >= 4 and key not in TEXT_STOP:
                surface[key] = canon
    pat = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(surface, key=len, reverse=True)) + r")\b", re.I)
    return pat, surface


def text_sequence(text: str, pat, surface) -> list[str]:
    seq: list[str] = []
    for m in pat.finditer(text):
        c = surface.get(m.group(1).lower())
        if c and (not seq or seq[-1] != c):
            seq.append(c)
    return seq


# ---------------------------------------------------------------- edges
def new_edge():
    return {"weight": 0, "signals": defaultdict(int), "sources": set(),
            "type": None, "access": None, "cost": None, "citation": None, "tier": None}


def add_edge(edges, a, b, signal, source, directed=False):
    # The graph is modelled as undirected: travel-sequence / plan order is just
    # movement order, not one-way passages, so A->B and B->A are the same edge.
    if a == b:
        return
    key = tuple(sorted((a, b)))
    e = edges[key]
    e["weight"] += SIGNAL_WEIGHT[signal]
    e["signals"][signal] += 1
    e["sources"].add(source)


def collect_deterministic(aliases, link_surface):
    edges: dict = defaultdict(new_edge)

    for p in sorted(VAULT.glob("locations/*.md")):
        canon, in_conn = p.stem, False
        for ln in read(p).splitlines():
            if ln.startswith("## "):
                in_conn = ln.strip().lower() == "## connections"
                continue
            for m in WIKILINK_RE.finditer(ln):
                other = resolve_link(m.group(1), link_surface)
                if other and other != canon:
                    if in_conn:
                        add_edge(edges, canon, other, "explicit", f"locations/{canon}", True)
                    else:
                        add_edge(edges, canon, other, "page-link", f"locations/{canon}",
                                 bool(DIRECTION_RE.search(ln)))

    for p in sorted(VAULT.glob("sessions/*.md")):
        seq = []
        for m in WIKILINK_RE.finditer(read(p)):
            other = resolve_link(m.group(1), link_surface)
            if other and (not seq or seq[-1] != other):
                seq.append(other)
        for a, b in zip(seq, seq[1:]):
            add_edge(edges, a, b, "travel-seq", f"sessions/{p.stem}", True)

    pat, surface = build_text_matcher(aliases)
    for ooc in sorted(rollup_root().glob("*/channels/ooc-planning.md")):
        week = ooc.parent.parent.name
        author, buf = None, []
        def flush():
            if author != "Greybrown":
                return
            seq = text_sequence("\n".join(buf), pat, surface)
            for a, b in zip(seq, seq[1:]):
                add_edge(edges, a, b, "plan", f"plan:{week}", True)
        for ln in read(ooc).splitlines():
            m = MSG_RE.match(ln)
            if m:
                flush(); author, buf = m.group(1).strip(), []
            else:
                buf.append(ln)
        flush()
    return edges


def apply_seed(edges, link_surface):
    """Ingest the curated trusted layer: typed edges + a reject (suppress) list."""
    if not SEED_FILE.exists():
        return 0, 0, []
    spec = json.loads(read(SEED_FILE))
    warnings: list[str] = []

    def canon(name):
        return link_surface.get(name.strip().lower())

    added = 0
    for ed in spec.get("edges", []):
        a, b = canon(ed.get("a", "")), canon(ed.get("b", ""))
        if not a or not b:
            warnings.append(f"seed edge endpoint not a location page: {ed.get('a')} / {ed.get('b')}")
            continue
        add_edge(edges, a, b, "seed", "seed:curated")
        e = edges[tuple(sorted((a, b)))]
        e["type"] = ed.get("type") or e["type"]
        if ed.get("access"):
            e["access"] = ed["access"]
        if ed.get("cost") is not None:
            e["cost"] = ed["cost"]
        e["citation"] = {"curated": ed.get("note", "")}
        added += 1

    rejected = 0
    reject_pairs = set()
    for rj in spec.get("reject", []):
        a, b = canon(rj.get("a", "")), canon(rj.get("b", ""))
        if a and b:
            reject_pairs.add(frozenset((a, b)))
    for key, e in edges.items():
        if frozenset(key) in reject_pairs:
            e["reject_reason"] = next((r.get("reason") for r in spec.get("reject", [])
                                       if {canon(r.get("a", "")), canon(r.get("b", ""))} == set(key)), "")
            e["suppressed"] = True
            rejected += 1

    # Base nodes (e.g. the Beacon): teleport-hub bases the party stages from.
    # Their real connectivity is fully curated in the seed; every other edge is
    # travel/recap co-occurrence, not a real passage -- suppress it.
    base = {c for c in (canon(b) for b in spec.get("base_nodes", [])) if c}
    for key, e in edges.items():
        if e.get("suppressed") or "seed" in e["signals"]:
            continue
        if base & set(key):
            e["suppressed"] = True
            e["reject_reason"] = "non-curated edge from a base node (staging/co-occurrence, not a real connection)"
            rejected += 1
    return added, rejected, warnings


def _register_virtual_node(aliases, link_surface, name, extra_aliases=()):
    aliases.setdefault(name, set()).add(name)
    aliases[name].update(extra_aliases)
    link_surface.setdefault(name.lower(), name)
    for a in extra_aliases:
        link_surface.setdefault(str(a).lower(), name)
    return name


def apply_teleport_network(edges, aliases, link_surface):
    """Wire the Thothian teleportation-circle network as a hub: every circle
    connects to one hub node, so any circle reaches any other in two hops
    (circle -> network -> circle). Circle names matching a real location page
    resolve to it; the rest become virtual nodes keyed by their circle name and
    aliased by their six-colour code."""
    if not SEED_FILE.exists():
        return 0
    net = json.loads(read(SEED_FILE)).get("teleport_network")
    if not net:
        return 0
    hub = net["hub"]
    etype = net.get("edge_type", "teleporter")
    _register_virtual_node(aliases, link_surface, hub)
    n = 0
    for c in net.get("circles", []):
        name, code = c["name"], c.get("code", "")
        canon = link_surface.get(name.lower())
        if canon:
            if code:
                aliases[canon].add(code)
                link_surface.setdefault(code.lower(), canon)
        else:
            canon = _register_virtual_node(aliases, link_surface, name, [code] if code else [])
        add_edge(edges, canon, hub, "seed", "seed:thothian-network")
        e = edges[tuple(sorted((canon, hub)))]
        e["type"] = etype
        e["access"] = ("Thothian teleportation circle: from any circle in the network, "
                       "dial the destination's six-colour code.")
        bits = [b for b in (code, c.get("hint", ""), f"[{c['status']}]" if c.get("status") else "") if b]
        e["citation"] = {"curated": " — ".join(bits)}
        n += 1
    return n


def write_network_note():
    if not SEED_FILE.exists():
        return
    net = json.loads(read(SEED_FILE)).get("teleport_network")
    if not net:
        return
    rows = ["---", "tags:", "  - note", "  - reference",
            "generated_by: scripts/location_graph.py", "---", "",
            "# Thothian Teleportation Circle Network", "",
            "Dial a destination's six-colour code from any circle in the network to "
            "teleport there. Codes and locations as catalogued by Vallium (Greybrown).", "",
            "| Code | Location | Status | Notes |", "|---|---|---|---|"]
    for c in net.get("circles", []):
        rows.append(f"| `{c.get('code','')}` | {c['name']} | {c.get('status','')} | "
                    f"{c.get('hint','').replace('|','/')} |")
    NETWORK_NOTE.write_text("\n".join(rows) + "\n", encoding="utf-8")


STRUCTURAL_SIGNALS = ("seed", "explicit", "page-link")


def drop_cooccurrence_only(edges):
    """Remove edges attested ONLY by travel-seq / plan co-occurrence.

    In this campaign the party teleports and back-tracks constantly, so
    "mentioned in sequence" does not imply "adjacent" -- those signals create a
    dense false mesh. Keep travel-seq/plan as CORROBORATION (they still add
    weight to edges that have a structural basis: a curated seed, an explicit
    `## Connections` entry, a location-page link, or an LLM citation), but never
    let them stand up an edge on their own.
    """
    drop = [k for k, e in edges.items()
            if not e.get("citation")
            and not any(s in e["signals"] for s in STRUCTURAL_SIGNALS)]
    for k in drop:
        del edges[k]
    return len(drop)


def assign_tiers(edges):
    for e in edges.values():
        if e.get("suppressed"):
            e["tier"] = "suppressed"
        elif "seed" in e["signals"] or "explicit" in e["signals"]:
            # Default-routing (confirmed) trusts only intentional adjacency:
            # curated seed or a page's `## Connections`. (LLM-cited edges are
            # promoted to confirmed separately in apply_llm_cache.) Page links
            # and travel/plan corroboration stay candidate -- "two weak signals"
            # is not enough, since cost-weighting turns a false edge into a
            # tempting shortcut.
            e["tier"] = "confirmed"
        else:
            e["tier"] = "candidate"


# ---------------------------------------------------------------- community detection
def detect_communities(edges):
    adj: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (a, b), e in edges.items():
        if e.get("tier") == "suppressed":
            continue
        adj[a][b] += e["weight"]
        adj[b][a] += e["weight"]
    degree = {n: sum(adj[n].values()) for n in adj}

    # Cross-region connectors (town, the surface ruins, the party's teleport
    # base) link everything and collapse label propagation into one blob.
    # Pull them out so genuine sub-regions separate; render them as a "Hubs"
    # group. A connector is a node whose weighted degree is a strong outlier.
    nonzero = sorted(degree.values())
    median = nonzero[len(nonzero) // 2] if nonzero else 0
    hubs = {n for n, d in degree.items() if d >= max(8, 5 * median)}
    hubs = set(sorted(hubs, key=lambda n: -degree[n])[:5])  # cap

    label = {n: n for n in adj if n not in hubs}
    for _ in range(30):
        changed = False
        for n in sorted(label):
            tally: dict[str, int] = defaultdict(int)
            for nb, w in adj[n].items():
                if nb in label:                      # ignore hub neighbours
                    tally[label[nb]] += w
            if tally:
                best = max(sorted(tally), key=lambda l: tally[l])
                if label[n] != best:
                    label[n] = best; changed = True
        if not changed:
            break
    comms: dict[str, list[str]] = defaultdict(list)
    for n, l in label.items():
        comms[l].append(n)
    named = {}
    for members in comms.values():
        hub = max(members, key=lambda n: degree.get(n, 0))
        named[hub] = sorted(members)
    if hubs:
        named["Hubs"] = sorted(hubs)
    return named, degree


# ---------------------------------------------------------------- serialise + map
VAULT_SIGNALS = ("explicit", "page-link", "travel-seq")


def edge_records(edges):
    recs = []
    for (a, b), e in edges.items():
        if e.get("tier") == "suppressed":
            continue
        # An edge may go to the player-facing RAG only if it has a vault-sourced
        # basis: a curated seed, an explicit/page/session signal, or an
        # LLM-validated citation. The `plan` signal alone (raw Discord) never is.
        has_basis = ("seed" in e["signals"] or any(s in e["signals"] for s in VAULT_SIGNALS)
                     or bool(e["citation"]))
        cost = e.get("cost")
        if cost is None:
            cost = TYPE_COST.get(e["type"], DEFAULT_COST)
        recs.append({
            "a": a, "b": b, "directed": False, "weight": e["weight"], "cost": cost,
            "tier": e["tier"], "type": e["type"], "access": e.get("access"), "citation": e["citation"],
            "signals": dict(e["signals"]), "sources": sorted(e["sources"])[:6],
            "rag_eligible": e["tier"] == "confirmed" and has_basis,
        })
    recs.sort(key=lambda r: r["weight"], reverse=True)
    return recs


def mermaid_id(name):
    return "n_" + re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_")


def write_map_note(edges, comms, degree):
    confirmed = [(a, b, e) for (a, b), e in edges.items() if e["tier"] == "confirmed"]
    lines = ["---", "tags:", "  - note", "  - map", "generated_by: scripts/location_graph.py",
             "---", "", "# Location Map", "",
             "Auto-generated adjacency map of Arden Vul locations, clustered by graph "
             "community. Only **confirmed** edges are drawn: a curated typed edge "
             "(`config/location_edges_seed.json`), an explicit page connection, or one "
             "backed by ≥2 independent signals. Travel/staging artifacts (e.g. teleporting "
             "from the Beacon base) are suppressed. Edge labels show the connection type. "
             "Inferred from canon + Vallium's route plans; may contain errors.", "",
             "```mermaid", "flowchart LR"]
    drawn_nodes = set()
    for hub, members in sorted(comms.items(), key=lambda kv: -len(kv[1])):
        memberset = set(members)
        sub = [(a, b, e) for (a, b, e) in confirmed if a in memberset and b in memberset]
        if not sub:
            continue
        lines.append(f'  subgraph c_{mermaid_id(hub)}["{hub} cluster"]')
        for a, b, e in sub:
            for n in (a, b):
                if n not in drawn_nodes:
                    lines.append(f'    {mermaid_id(n)}["{n}"]')
                    drawn_nodes.add(n)
        lines.append("  end")
    for a, b, e in sorted(confirmed, key=lambda x: -x[2]["weight"]):
        lbl = e["type"] or ""
        lab = f"|{lbl}|" if lbl else ""
        lines.append(f"  {mermaid_id(a)} ---{lab} {mermaid_id(b)}")
    lines += ["```", ""]
    MAP_NOTE.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- LLM proposer/verifier
def evidence_sentences(a, b, aliases, max_n=6):
    """Vault sentences (sessions + Discord summaries) mentioning both endpoints."""
    names_a = [n for n in aliases[a]]
    names_b = [n for n in aliases[b]]
    out = []
    pool = list(VAULT.glob("sessions/*.md")) + list(VAULT.glob("notes/Discord Summary*.md"))
    for p in pool:
        rel = f"vault/{p.relative_to(VAULT)}"
        for sent in SENT_SPLIT.split(re.sub(r"\s+", " ", read(p))):
            la = any(n.lower() in sent.lower() for n in names_a)
            lb = any(n.lower() in sent.lower() for n in names_b)
            if la and lb:
                out.append({"file": rel, "quote": sent.strip()[:300]})
                if len(out) >= max_n:
                    return out
    return out


def verify_prompt(a, b, evidence):
    ev = "\n".join(f'- FILE: {e["file"]}\n  TEXT: "{e["quote"]}"' for e in evidence) or "(none found)"
    return (
        f'Two candidate locations in the dungeon "Arden Vul": A="{a}", B="{b}".\n'
        f"Vault excerpts that mention both:\n{ev}\n\n"
        "Decide if A and B are DIRECTLY connected (one is reachable from the other without "
        "passing through a third named location), based ONLY on the excerpts.\n"
        "Return strict JSON with keys:\n"
        '  connected (bool),\n'
        '  type (one of: passage, stairs, door, teleporter, lift, ferry, bridge, road, region-contains, unknown),\n'
        '  direction (short string like "A is north of B", or ""),\n'
        '  citation (object {file, quote} where quote is copied VERBATIM from one excerpt above and '
        "supports a direct connection, or null if no excerpt supports it).\n"
        "Do not invent quotes. If no excerpt supports a direct connection, set connected=false and citation=null."
    )


def cache_key(a, b):
    return "|||".join(sorted((a, b)))


def load_llm_cache() -> dict:
    return json.loads(read(LLM_CACHE)) if LLM_CACHE.exists() else {}


def apply_llm_cache(edges):
    """Merge previously-verified LLM verdicts onto the freshly-built edges."""
    cache = load_llm_cache()
    applied = 0
    for (a, b), e in edges.items():
        if e.get("suppressed"):
            continue
        v = cache.get(cache_key(a, b))
        if not v or not v.get("validated"):
            continue
        e["type"] = v.get("type") or e["type"]
        e["citation"] = v.get("citation")
        e["tier"] = "confirmed"
        applied += 1
    return applied


def run_llm_pass(edges, aliases, limit, eval_mode):
    from vault_automation import llm_chat_json  # reuse configured client
    cache = load_llm_cache()
    candidates = [(k, e) for k, e in edges.items()
                  if e["tier"] == "candidate" and cache_key(*k) not in cache]
    # prioritise plan-only leads (most interesting: only Vallium suggests them)
    candidates.sort(key=lambda kv: (("plan" not in kv[1]["signals"]), -kv[1]["weight"]))
    sample = candidates[:limit]
    rows = []
    for (a, b), e in sample:
        ev = evidence_sentences(a, b, aliases)
        verdict, note = None, ""
        try:
            verdict = llm_chat_json(verify_prompt(a, b, ev), timeout=120)
        except Exception as exc:
            note = f"LLM error: {str(exc)[:80]}"
        result = "skip"
        if verdict and verdict.get("connected"):
            cit = verdict.get("citation") or None
            valid = False
            if isinstance(cit, dict) and cit.get("file") and cit.get("quote"):
                fpath = ROOT / cit["file"] if cit["file"].startswith("vault/") else None
                if fpath and fpath.exists() and norm_contains(read(fpath), cit["quote"]):
                    valid = True
            e["type"] = (verdict.get("type") or "unknown")
            if valid:
                e["tier"] = "confirmed"; e["citation"] = cit; result = "confirmed+cited"
            else:
                e["tier"] = "hint"; result = "hint (no valid citation)"
            cache[cache_key(a, b)] = {"connected": True, "validated": valid,
                                      "type": e["type"], "citation": cit if valid else None}
        elif verdict is not None:
            result = "rejected"
            cache[cache_key(a, b)] = {"connected": False, "validated": False}
        rows.append({"a": a, "b": b, "signals": dict(e["signals"]),
                     "evidence": len(ev), "result": result, "note": note,
                     "type": e.get("type"), "citation": e.get("citation")})
    LLM_CACHE.parent.mkdir(parents=True, exist_ok=True)
    LLM_CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    if eval_mode:
        print("\n=== LLM verifier evaluation ===")
        print(f"{'result':<26}{'type':<16}{'ev':>3}  edge")
        for r in rows:
            print(f"{r['result']:<26}{str(r['type'] or ''):<16}{r['evidence']:>3}  "
                  f"{r['a']} -> {r['b']}  {dict(r['signals'])}")
        from collections import Counter
        tally = Counter(r["result"] for r in rows)
        print("\nsummary:", dict(tally))
    return rows


# ---------------------------------------------------------------- main
def cmd_build(args):
    aliases, link_surface = build_lexicon()
    edges = collect_deterministic(aliases, link_surface)
    seeded, suppressed, warns = apply_seed(edges, link_surface)  # curated trusted layer
    circles = apply_teleport_network(edges, aliases, link_surface)
    assign_tiers(edges)
    if args.llm:
        run_llm_pass(edges, aliases, args.llm, args.eval)
    cached = apply_llm_cache(edges)   # merge all prior verified verdicts
    dropped_cooc = drop_cooccurrence_only(edges)   # travel-seq/plan are corroboration-only
    comms, degree = detect_communities(edges)
    recs = edge_records(edges)
    graph_json = json.dumps({
        "nodes": {c: {"aliases": sorted(aliases[c]), "degree": degree.get(c, 0)} for c in sorted(aliases)},
        "communities": {hub: members for hub, members in comms.items()},
        "edges": recs,
    }, indent=2)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(graph_json, encoding="utf-8")
    if args.publish:
        pub = Path(args.publish)
        pub.parent.mkdir(parents=True, exist_ok=True)
        pub.write_text(graph_json, encoding="utf-8")
        print(f"published graph -> {pub}")
    write_map_note(edges, comms, degree)
    write_network_note()

    tiers = Counter_tier(recs)
    print(f"nodes: {len(aliases)}   edges: {len(recs)}   communities: {len(comms)}")
    print(f"  seeded(curated): {seeded}   suppressed(artifacts): {suppressed}   teleport-circles: {circles}")
    print(f"  dropped co-occurrence-only (travel-seq/plan): {dropped_cooc}")
    print(f"  confirmed: {tiers['confirmed']}   candidate: {tiers['candidate']}   hint: {tiers['hint']}")
    print(f"  rag-eligible: {sum(1 for r in recs if r['rag_eligible'])}   (LLM-cited applied: {cached})")
    for w in warns:
        print(f"  WARN: {w}")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} and {MAP_NOTE.relative_to(ROOT)}")
    return 0


def Counter_tier(recs):
    out = defaultdict(int)
    for r in recs:
        out[r["tier"]] += 1
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the Arden Vul location graph")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the graph + map")
    b.add_argument("--llm", type=int, default=0, metavar="N",
                   help="run the LLM verifier on N candidate edges")
    b.add_argument("--eval", action="store_true", help="print an LLM evaluation table")
    b.add_argument("--publish", metavar="PATH", default=None,
                   help="also write the graph JSON to PATH (e.g. the RAG API's mounted data file)")
    b.set_defaults(func=cmd_build)
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
