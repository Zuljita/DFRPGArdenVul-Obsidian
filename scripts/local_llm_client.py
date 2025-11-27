#!/usr/bin/env python3
"""
Lightweight client for querying a local OpenAI-compatible LM endpoint (e.g., LM Studio).

Defaults to http://192.168.21.76:1234 and model `meta-llama-3.1-8b-instruct`.

Usage examples:
  python3 scripts/local_llm_client.py --prompt "Extract canonical entities" \
    --files vault/sessions/Session 12.md

  python3 scripts/local_llm_client.py --system "You are a junior data extractor." \
    --prompt "Summarize this session and list NPCs." --files vault/sessions/Session 10.md

Notes:
- Assumes OpenAI-compatible chat API: POST /v1/chat/completions
- No API key by default for LM Studio; add --api-key if your server requires it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

import requests


def build_messages(prompt: str, files: List[Path], system: Optional[str]) -> list:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})

    file_blobs = []
    for fp in files:
        try:
            text = fp.read_text(encoding="utf-8")
            file_blobs.append(f"<file path=\"{fp.as_posix()}\">\n{text}\n</file>")
        except Exception as e:
            file_blobs.append(f"<file path=\"{fp.as_posix()}\" error=\"{e}\" />")

    file_section = "\n\n".join(file_blobs)

    if file_section:
        merged_prompt = (
            "You will read one or more files provided below and follow the user instruction.\n"
            "Respond concisely and do not invent entities.\n\n"
            f"USER INSTRUCTION:\n{prompt}\n\nFILES:\n{file_section}\n"
        )
    else:
        merged_prompt = prompt

    messages.append({"role": "user", "content": merged_prompt})
    return messages


def chat(
    prompt: str,
    files: List[Path],
    system: Optional[str],
    endpoint: str,
    model: str,
    temperature: float,
    max_tokens: Optional[int],
    api_key: Optional[str],
    timeout: int,
):
    url = endpoint.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": build_messages(prompt, files, system),
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    # Prefer assistant content; fall back to raw JSON if missing
    try:
        return data["choices"][0]["message"]["content"], data
    except Exception:
        return json.dumps(data, indent=2), data


def main(argv=None):
    p = argparse.ArgumentParser(description="Query local OpenAI-compatible LLM (LM Studio)")
    p.add_argument("--endpoint", default="http://192.168.21.76:1234", help="Base URL (no trailing slash)")
    p.add_argument("--model", default="meta-llama-3.1-8b-instruct", help="Model name")
    p.add_argument("--system", default=None, help="Optional system prompt")
    p.add_argument("--prompt", required=True, help="User prompt")
    p.add_argument("--files", nargs="*", default=[], help="Files to include in the prompt")
    p.add_argument("--temperature", type=float, default=0.2, help="Sampling temperature")
    p.add_argument("--max-tokens", type=int, default=None, help="Max tokens (optional)")
    p.add_argument("--api-key", default=None, help="API key if your server requires it")
    p.add_argument("--timeout", type=int, default=120, help="Request timeout (seconds)")
    p.add_argument("--json", action="store_true", help="Print full JSON response to stdout")

    args = p.parse_args(argv)

    files = [Path(f).resolve() for f in args.files]
    content, raw = chat(
        prompt=args.prompt,
        files=files,
        system=args.system,
        endpoint=args.endpoint,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        api_key=args.api_key,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(raw, indent=2))
    else:
        print(content)


if __name__ == "__main__":
    sys.exit(main())

