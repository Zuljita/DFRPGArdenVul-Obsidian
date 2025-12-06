#!/usr/bin/env python3
"""
CAC (Crosscheck and Cleanup) for a single vault note.

For the given input article, parse wikilinks, open each linked article, and ask the local LLM to:
- references_present: does the linked article actually reference the source article's subject?
- should_exist: should this linked article exist as a separate page in a TTRPG vault (vs. being folded/merged)?
- data_match: does the data in the source and linked article match (no contradictions)?
- info_to_pull: short bullets of information in the linked page that should be pulled into the source

Outputs a report and (optionally) appends TODOs to the source article.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List, Dict
import subprocess

ROOT = Path(__file__).resolve().parents[1]
VAULT = ROOT / 'vault'

LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

SYSTEM_PROMPT = (
    "You are auditing wiki articles for a tabletop RPG campaign. "
    "Be concise and avoid invention. Respond with strict JSON only."
)

USER_TMPL = (
    "Subject: {subject}\n\n"
    "SOURCE ARTICLE (excerpt):\n{src_excerpt}\n\n"
    "LINKED ARTICLE (excerpt):\n{dst_excerpt}\n\n"
    "Tasks:\n"
    "1) references_present: Does the linked article actually reference the Subject (YES/NO)?\n"
    "2) should_exist: Should the linked article exist as a separate page for a TTRPG group (YES/NO)?\n"
    "3) data_match: Is information consistent (YES/NO)?\n"
    "4) info_to_pull: Short bullets of concrete info that should be pulled into the source (if any).\n"
    "Return strict JSON with keys: references_present, should_exist, data_match, info_to_pull (array), reasons (short)."
)

def call_llm(system: str, user: str, endpoint: str, model: str, temperature: float = 0.1, max_tokens: int = 300, timeout: int = 60) -> str:
    cmd = [
        'python3', str(ROOT / 'scripts' / 'local_llm_client.py'),
        '--endpoint', endpoint,
        '--model', model,
        '--system', system,
        '--prompt', user,
        '--temperature', str(temperature),
        '--max-tokens', str(max_tokens),
        '--timeout', str(timeout),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"LLM call failed: {res.stderr}\n{res.stdout}")
    return res.stdout.strip()

def read_text(p: Path) -> str:
    return p.read_text(encoding='utf-8', errors='ignore')

def extract_title_and_content(p: Path) -> (str, str):
    text = read_text(p)
    # Title: from frontmatter title or first H1 or filename
    m_fm = re.match(r"---\n(.*?)\n---\n", text, re.S)
    title = None
    if m_fm:
        fm = m_fm.group(1)
        m_title = re.search(r"^title:\s*\"?([^\n\"]+)\"?\s*$", fm, re.M)
        if m_title:
            title = m_title.group(1).strip()
    if not title:
        m_h1 = re.search(r"^#\s+(.+)$", text, re.M)
        if m_h1:
            title = m_h1.group(1).strip()
        else:
            title = p.stem
    return title, text

def resolve_wikilink(target: str) -> Path | None:
    # Supports bare [[Name]] or [[folder/Name.md]] or [[folder/Name|label]] (already split)
    if target.endswith('.md'):
        abs_path = VAULT / target
        return abs_path if abs_path.exists() else None
    # If includes folder without extension
    if '/' in target:
        abs_path = VAULT / (target + '.md')
        return abs_path if abs_path.exists() else None
    # Fallback: search by basename
    candidates = list(VAULT.rglob(f"{target}.md"))
    return candidates[0] if candidates else None

def main():
    ap = argparse.ArgumentParser(description='CAC: Crosscheck and Cleanup for a single note')
    ap.add_argument('--input', required=True, help='Path to source note in vault')
    ap.add_argument('--endpoint', default='http://192.168.21.76:1234', help='LLM endpoint base URL')
    ap.add_argument('--model', default='qwen2.5-7b-instruct', help='LLM model name')
    ap.add_argument('--report', default=None, help='Path to write a CAC report (Markdown)')
    ap.add_argument('--write', action='store_true', help='Append TODOs to the source article')
    args = ap.parse_args()

    src = VAULT / args.input if not str(args.input).startswith(str(VAULT)) else Path(args.input)
    if not src.exists():
        raise SystemExit(f"Not found: {src}")

    subject, src_text = extract_title_and_content(src)
    # Collect links
    links = []
    for m in LINK_RE.finditer(src_text):
        target = m.group(1).strip()
        label = (m.group(2) or target).strip()
        links.append((target, label))
    # De-dup by target
    seen = set(); uniq_links = []
    for t,lbl in links:
        if (t,lbl) in seen:
            continue
        seen.add((t,lbl)); uniq_links.append((t,lbl))

    # Prepare report entries
    report_lines = [f"# CAC Report for {subject}", '', f"Source: {src.relative_to(VAULT)}", '']
    todos: List[str] = []
    src_excerpt = src_text[:1600]

    for target, label in uniq_links:
        dst = resolve_wikilink(target)
        if not dst:
            report_lines.append(f"- {label}: TARGET NOT FOUND ({target})")
            todos.append(f"- Link [[{target}|{label}]] is broken; target not found.")
            continue
        _, dst_text = extract_title_and_content(dst)
        dst_excerpt = dst_text[:2000]
        user = USER_TMPL.format(subject=subject, src_excerpt=src_excerpt, dst_excerpt=dst_excerpt)
        try:
            out = call_llm(SYSTEM_PROMPT, user, args.endpoint, args.model, temperature=0.1, max_tokens=400, timeout=90)
            data = json.loads(out)
        except Exception as e:
            # On failure, note and continue
            report_lines.append(f"- [[{dst.relative_to(VAULT)}|{label}]]: LLM error: {e}")
            todos.append(f"- Review [[{dst.relative_to(VAULT)}|{label}]] manually (LLM error)")
            continue

        ref = str(data.get('references_present', '')).upper()
        exi = str(data.get('should_exist', '')).upper()
        mat = str(data.get('data_match', '')).upper()
        info = data.get('info_to_pull', []) or []
        reasons = data.get('reasons', '')

        report_lines.append(f"## Link: [[{dst.relative_to(VAULT)}|{label}]]")
        report_lines.append(f"- references_present: {ref}")
        report_lines.append(f"- should_exist: {exi}")
        report_lines.append(f"- data_match: {mat}")
        if info:
            report_lines.append(f"- info_to_pull:")
            for it in info:
                report_lines.append(f"  - {it}")
        if reasons:
            report_lines.append(f"- reasons: {reasons}")
        report_lines.append('')

        # Build TODOs on problematic answers
        if ref.startswith('NO'):
            todos.append(f"- Linked page [[{dst.relative_to(VAULT)}|{label}]] doesn’t reference {subject} — check if link is appropriate.")
        if exi.startswith('NO'):
            todos.append(f"- Consider merging [[{dst.relative_to(VAULT)}|{label}]] into a broader note; may not warrant a separate page.")
        if mat.startswith('NO'):
            todos.append(f"- Data mismatch with [[{dst.relative_to(VAULT)}|{label}]] — review and reconcile.")
        if info:
            todos.append(f"- Pull from [[{dst.relative_to(VAULT)}|{label}]]: {', '.join(info[:3])}")

    # Write report
    report_path = Path(args.report) if args.report else (ROOT / 'docs' / 'CAC' / (src.stem + '.md'))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding='utf-8')
    print(f"Wrote {report_path}")

    # Optionally append TODOs to source file
    if args.write and todos:
        text = read_text(src)
        if '\n## TODO' in text:
            text = text + "\n" + "\n".join(todos) + "\n"
        else:
            text = text + "\n\n## TODOs (CAC)\n" + "\n".join(todos) + "\n"
        src.write_text(text, encoding='utf-8')
        print(f"Appended TODOs to {src.relative_to(VAULT)}")

if __name__ == '__main__':
    main()

