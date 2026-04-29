from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import re
from pathlib import Path

app = FastAPI(title="Zero Assistant Bridge")


class AssistRequest(BaseModel):
    text: str
    language: Optional[str] = None
    source: Optional[str] = None


class AssistResponse(BaseModel):
    reply_text: str
    meta: Optional[Dict[str, Any]] = None


OPENAI_MODEL = os.environ.get("ZERO_OPENAI_MODEL", "gpt-4o-mini")


def resolve_openai_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    bashrc = Path.home() / ".bashrc"
    if bashrc.exists():
        text = bashrc.read_text(errors="ignore")
        m = re.search(r'OPENAI_API_KEY\s*=\s*"([^"]+)"', text)
        if m:
            return m.group(1).strip()
    return ""


@app.post("/zero-assistant", response_model=AssistResponse)
def zero_assistant(req: AssistRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")

    # ── Local skills (exec-plan 007) ────────────────────────────────────────
    # The skills package is the canonical (and only) local-skill dispatcher.
    # The legacy hard-coded 相框/兔兔 fallback routes were removed in
    # exec-plan 012 once 007 had been live-verified.
    try:
        from .skills import match_skill
        hit = match_skill(text)
        if hit is not None:
            reply = hit.run()
            return AssistResponse(
                reply_text=reply,
                meta={"source": "local-skill", "action": hit.NAME},
            )
    except Exception as exc:  # pylint: disable=broad-except
        # Skill dispatcher must never break the API. Fall through to the
        # LLM path below.
        print(f"[api] skill dispatcher error: {exc}", flush=True)

    # LLM path: two-step routing.
    #   1. Search/browse/weather intents → OpenAI Responses + web_search tool
    #      (`src/api/websearch.py`). This is the fast primary route (~3–8s).
    #   2. Everything else, plus websearch failures → plain OpenAI gpt-4o-mini
    #      Responses fallback at the bottom of this function.
    from .skills.tokens import is_search_intent
    is_search = is_search_intent(text)

    # Exec-plan 006: for search/weather, prefer fast OpenAI Responses + web_search tool.
    # On failure, fall through to the plain OpenAI fallback below.
    if is_search and os.environ.get("VOICEASSIST_DISABLE_WEBSEARCH", "").strip() != "1":
        try:
            from .websearch import run_websearch
            print("[api] using websearch path", flush=True)
            reply = run_websearch(text)
            if reply:
                return AssistResponse(
                    reply_text=reply,
                    meta={"source": "openai-websearch", "search": True},
                )
        except Exception as exc:
            print(f"[api] websearch failed: {exc}; falling back to openai", flush=True)

    try:
        from openai import OpenAI

        api_key = resolve_openai_key()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not found")
        client = OpenAI(api_key=api_key)
        prompt = [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": "你是一個自然、親切的語音助理。\n\n回答規則：\n1. 用口語回答，不要像寫文章。\n2. 句子要短。\n3. 不要用條列式。\n4. 偶爾加入「嗯」、「好」、「我看看」這種口語。\n5. 回答控制在1~2句。"}],
            },
            {"role": "user", "content": [{"type": "input_text", "text": text}]},
        ]
        resp = client.responses.create(model=OPENAI_MODEL, input=prompt)

        reply = ""
        for item in getattr(resp, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", None) in ("output_text", "text"):
                    reply = content.text
                    break
            if reply:
                break

        if not reply:
            reply = "抱歉，我暫時無法產生回覆。"
        return AssistResponse(
            reply_text=reply,
            meta={"model": OPENAI_MODEL, "source": "fallback-openai", "search": is_search},
        )
    except Exception as exc:
        return AssistResponse(reply_text="抱歉，我剛剛出現錯誤。", meta={"error": str(exc)})
