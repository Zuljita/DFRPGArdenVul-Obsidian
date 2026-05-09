---
name: arden-vul-discord-pipeline
description: Operate and troubleshoot the DFRPG Arden Vul Discord ingestion, weekly rollup, LLM digest, QA/revision, Obsidian import, and IAC workflows. Use when working on Discord chat explorer data on Brain, LM Studio model calls on the workstation, weekly digest files, import into this Obsidian repo, or article-candidate extraction scripts.
---

# Arden Vul Discord Pipeline

## Guardrails

1. Do not print or commit secrets. The Discord token lives outside this repo on Brain; use it only in place.
2. Do not commit raw Discord transcripts unless explicitly requested. The repo should receive curated/revised outputs.
3. Treat `revised-digest.md` as the final weekly article, not `digest.md` or `qa.md`.
4. Keep old `vault/notes/Discord Summary YYYY-WNN.md` files unless the user explicitly asks to replace/remove them.
5. Prefer dry runs for IAC and stub creation. Review `would_create` before writing files.

## Hosts And Paths

- Brain pipeline root: `/home/kyle/discord-chat-explorer`
- Brain weekly rollups: `/home/kyle/discord-chat-explorer/weekly-rollups`
- Brain weekly digests: `/home/kyle/discord-chat-explorer/weekly-digests`
- Final per-week output: `weekly-digests/week-ending-YYYY-MM-DD-2300-central/revised-digest.md`
- Obsidian repo local clone: `/home/kylenorton/openclawject/work/DFRPGArdenVul-Obsidian`
- Imported vault notes: `vault/notes/weekly-digests/Week Ending YYYY-MM-DD.md`
- Workstation LM Studio base URL: `http://100.76.165.94:1234`
- Preferred digest model: `google/gemma-4-26b-a4b`
- Preferred QA/revision model when available: `qwen/qwen3.6-35b-a3b`, loaded with context `65536` to avoid RAM spill/crawling.

Use the local homelab SSH skill for hostnames, SSH details, and sudo handling. Never copy those secrets into this repo.

## Discord Export

Primary script on Brain:

```bash
/home/kyle/discord-chat-explorer/discord_chat_explorer.py
```

Exports messages to:

```text
/home/kyle/discord-chat-explorer/guilds/1346534955357835336/streams/*.jsonl
```

Known working behavior:

- Guild: `DFRPG Arden Vul`
- Captures normal channels and threads.
- Thread parent channel types must include `0, 5, 15, 16`.
- State is in `/home/kyle/discord-chat-explorer/state/state.json`.
- Timer/service: `discord-chat-explorer.timer` and `discord-chat-explorer.service`.

Useful checks:

```bash
systemctl status discord-chat-explorer.timer discord-chat-explorer.service --no-pager
journalctl -u discord-chat-explorer.service -n 120 --no-pager
find /home/kyle/discord-chat-explorer/guilds/1346534955357835336/streams -name '*.jsonl' | wc -l
```

## Weekly Rollups

Rollup script:

```bash
/home/kyle/discord-chat-explorer/discord_weekly_rollup.py
```

Week boundary is Friday at 11 PM Central. Output shape:

```text
weekly-rollups/week-ending-YYYY-MM-DD-2300-central/
  all-messages.md
  manifest.json
  channels/*.md
```

Rollup service:

```bash
systemctl status discord-weekly-rollup.service --no-pager
```

The latest rollup can include the in-progress future Friday. Do not generate a digest for that partial week.

## Digest, QA, Revision

There are three LLM stages:

1. `discord_weekly_digest.py` creates `digest.md` using Gemma.
2. `discord_digest_qa.py` creates `qa.md` using Qwen QA/fact-checking.
3. `discord_digest_revise.py` creates `revised-digest.md` by synthesizing original digest, QA, and transcript.

The Saturday digest automation must target the latest completed Friday boundary:

```bash
/usr/bin/python3 /home/kyle/discord-chat-explorer/discord_weekly_digest.py --root /home/kyle/discord-chat-explorer --week latest-completed
```

Do not use `--week latest` in automation; it can pick a partial next-week rollup.

Count completion:

```bash
root=/home/kyle/discord-chat-explorer
find "$root/weekly-digests" -maxdepth 2 -type f -name digest.md | wc -l
find "$root/weekly-digests" -maxdepth 2 -type f -name qa.md | wc -l
find "$root/weekly-digests" -maxdepth 2 -type f -name revised-digest.md | wc -l
```

Resume missing QA:

```bash
QA_TIMEOUT_SECONDS=1800 QA_MAX_TOKENS=5000 \
  /usr/bin/python3 /home/kyle/discord-chat-explorer/discord_digest_qa.py --week missing
```

Resume missing revision:

```bash
REVISE_TIMEOUT_SECONDS=1800 REVISE_MAX_TOKENS=9000 \
  /usr/bin/python3 /home/kyle/discord-chat-explorer/discord_digest_revise.py --week missing
```

## LM Studio Lessons

- Gemma 4 is good for digesting and IAC-style extraction.
- Qwen 3.6 35B is useful for QA/revision, but 131k context caused low GPU utilization and spillover. Reload at 65,536 context for this workload.
- Check current LM Studio state with:

```bash
/mnt/c/Users/KyleNorton/.lmstudio/bin/lms.exe ps
```

- Good Qwen reload pattern:

```bash
/mnt/c/Users/KyleNorton/.lmstudio/bin/lms.exe unload qwen/qwen3.6-35b-a3b
/mnt/c/Users/KyleNorton/.lmstudio/bin/lms.exe load qwen/qwen3.6-35b-a3b --identifier qwen/qwen3.6-35b-a3b --gpu max --context-length 65536 -y
```

- Reasoning-capable models may put useful text in `reasoning_content` or produce empty `message.content`. For extractor scripts, prefer `/no_think`, strict JSON prompts, `reasoning_effort: none`, and `enable_thinking: false`.
- If GPU utilization is very low and generations are slow, suspect over-large context or CPU/RAM spill rather than prompt difficulty.

## Obsidian Import

This repo imports final weekly digests from Brain into:

```text
vault/notes/weekly-digests/
```

Use:

```bash
rm -rf /tmp/arden-vul-revised-digests
mkdir -p /tmp/arden-vul-revised-digests
ssh brain 'cd /home/kyle/discord-chat-explorer/weekly-digests && tar -czf - week-ending-*/revised-digest.md' \
  | tar -xzf - -C /tmp/arden-vul-revised-digests
python3 scripts/import_revised_weekly_digests.py /tmp/arden-vul-revised-digests
```

Adjust the `ssh brain` alias to the actual SSH command provided by the homelab SSH skill if no alias exists.

Import helper:

```bash
scripts/import_revised_weekly_digests.py
```

It adds frontmatter, writes `Week Ending YYYY-MM-DD.md`, and regenerates `vault/notes/weekly-digests/Index.md`.

## IAC Workflow

Maintained path:

```bash
python3 scripts/run_iac.py --file "vault/sessions/Session 50 - The Iron Circlet of Ghanor.md" --dry-run --kinds NPC,Location,Faction --chunk-size 6000
```

Current defaults:

- Endpoint: `http://100.76.165.94:1234`
- Model: `google/gemma-4-26b-a4b`

Override with:

```bash
LMSTUDIO_BASE_URL=http://100.76.165.94:1234 LMSTUDIO_IAC_MODEL=google/gemma-4-26b-a4b python3 scripts/run_iac.py ...
```

Important behavior:

- `run_iac.py` maps candidates to existing canonical pages using filenames, frontmatter aliases, implicit article stripping, short-name aliases, and fuzzy matching.
- Treat `would_create` as a triage list, not an instruction to blindly create stubs.
- `entity_curator.py` is older and noisier. Use it only for exploratory review unless its mapping logic is upgraded.
- Candidate quality improves with chunks around 6000 chars for Gemma 4.

Validation:

```bash
python3 -m py_compile scripts/local_llm_client.py scripts/run_iac.py scripts/entity_curator.py scripts/llm_benchmark.py
python3 scripts/check_wikilinks.py
git diff --stat
```
