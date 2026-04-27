"""
src/api/websearch.py — fast search/weather replies via OpenAI Responses API
with the built-in `web_search` tool.

Primary path for search/weather intents. On failure the API falls back
to a plain OpenAI Responses call in `src/api/app.py`
(see exec-plans 006 and 010).

Rollback: set env `VOICEASSIST_DISABLE_WEBSEARCH=1` to short-circuit.
"""
from __future__ import annotations

import os
from typing import Optional


WEBSEARCH_MODEL = os.environ.get("ZERO_WEBSEARCH_MODEL", "gpt-4o-mini")
DEFAULT_SYSTEM_PROMPT = (
    "你是一個自然、親切的語音助理，會使用網路搜尋工具回答即時資訊。\n\n"
    "回答規則：\n"
    "1. 用口語回答，不要像寫文章。\n"
    "2. 句子要短，控制在 1~3 句。\n"
    "3. 不要用條列式、不要列出網址。\n"
    "4. 講重點：地名 / 時間 / 數字。\n"
    "5. 不要說「根據網路搜尋」之類的話，直接告訴我答案。"
)


def _resolve_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    # Fallback: read from ~/.bashrc the same way app.py does
    from pathlib import Path
    import re
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        text = bashrc.read_text(errors="ignore")
        m = re.search(r'OPENAI_API_KEY\s*=\s*"([^"]+)"', text)
        if m:
            return m.group(1).strip()
    return ""


def _extract_output_text(resp) -> str:
    """Pull plain text out of an OpenAI Responses API result."""
    # Prefer the convenience attribute if present.
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()

    parts: list[str] = []
    for item in getattr(resp, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            ctype = getattr(content, "type", None)
            if ctype in ("output_text", "text"):
                t = getattr(content, "text", None)
                if isinstance(t, str) and t.strip():
                    parts.append(t.strip())
    return "\n".join(parts).strip()


def run_websearch(query: str, *, system_prompt: Optional[str] = None) -> str:
    """Run a search/weather query through OpenAI Responses + web_search tool.

    Returns clean reply text. Raises on any failure so caller can fall back.
    """
    if os.environ.get("VOICEASSIST_DISABLE_WEBSEARCH", "").strip() == "1":
        raise RuntimeError("websearch disabled via VOICEASSIST_DISABLE_WEBSEARCH=1")

    if not query or not query.strip():
        raise ValueError("empty query")

    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    sys_prompt = (system_prompt or DEFAULT_SYSTEM_PROMPT).strip()

    resp = client.responses.create(
        model=WEBSEARCH_MODEL,
        tools=[{"type": "web_search"}],
        input=[
            {
                "role": "system",
                "content": [{"type": "input_text", "text": sys_prompt}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": query.strip()}],
            },
        ],
    )

    reply = _extract_output_text(resp)
    if not reply:
        raise RuntimeError("websearch returned empty text")
    return reply
