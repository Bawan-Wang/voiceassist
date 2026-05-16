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

    # Route classification is now shared with the voice bridge, but the API
    # keeps its own executors and response metadata contract.
    from .skills.policy import RouteKind, classify_request

    decision = classify_request(text)

    if decision.kind is RouteKind.LOCAL_SKILL and decision.skill is not None:
        reply = decision.skill.run()
        return AssistResponse(
            reply_text=reply,
            meta={"source": "local-skill", "action": decision.skill.NAME},
        )

    if decision.kind is RouteKind.TIME_QUERY and decision.time_query is not None:
        from .skills.time_query import render_time_query_reply

        reply = render_time_query_reply(decision.time_query)
        return AssistResponse(
            reply_text=reply,
            meta={
                "source": "local-skill",
                "action": "time_query",
                "time_kind": decision.time_query.kind,
                "timezone": decision.time_query.timezone,
            },
        )

    # Exec-plan 006: for search/weather, prefer fast OpenAI Responses + web_search tool.
    # On failure, fall through to the plain OpenAI fallback below.
    if decision.kind is RouteKind.TOOL_NEEDED and os.environ.get("VOICEASSIST_DISABLE_WEBSEARCH", "").strip() != "1":
        try:
            from .websearch import run_websearch
            print("[api] using websearch path", flush=True)
            reply = run_websearch(decision.routed_text)
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
            {"role": "user", "content": [{"type": "input_text", "text": decision.routed_text}]},
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
            meta={"model": OPENAI_MODEL, "source": "fallback-openai", "search": decision.is_search},
        )
    except Exception as exc:
        return AssistResponse(reply_text="抱歉，我剛剛出現錯誤。", meta={"error": str(exc)})
