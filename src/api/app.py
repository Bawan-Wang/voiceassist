from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import os
import re
import subprocess
import time
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
VOICE_DIR = Path("/home/jh-pi/.openclaw/workspace/voiceassist")
PHOTOFRAME_SCRIPT = str(VOICE_DIR / "run_photoframe.sh")
BUNNY_PID = "/tmp/voiceassist_bunny.pid"
PHOTO_PID = "/tmp/voiceassist_photo.pid"
BUNNY_CMD = f"cd {VOICE_DIR} && DISPLAY=:0 nohup .venv/bin/python src/ui/assistant_ui.py >/tmp/bunny_ui.log 2>&1 & echo $! > {BUNNY_PID}"
PHOTO_CMD = f"DISPLAY=:0 nohup /home/jh-pi/.openclaw/workspace/voiceassist/run_photoframe.sh >/tmp/photoframe.log 2>&1 & echo $! > {PHOTO_PID}"

_LAST_ACTION = {"name": "", "ts": 0.0}
USE_OPENCLAW_AGENT = os.environ.get("ZERO_USE_OPENCLAW_AGENT", "1") == "1"


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


def _debounce(action: str, seconds: float = 2.5) -> bool:
    now = time.time()
    if _LAST_ACTION["name"] == action and now - _LAST_ACTION["ts"] < seconds:
        return True
    _LAST_ACTION["name"] = action
    _LAST_ACTION["ts"] = now
    return False


def _pids(pattern: str) -> list[int]:
    r = subprocess.run(["bash", "-lc", f"pgrep -f '{pattern}'"], capture_output=True, text=True)
    pids: list[int] = []
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.append(int(line))
        except ValueError:
            pass
    return pids


def _count(pattern: str) -> int:
    return len(_pids(pattern))


def _kill_all(pattern: str) -> None:
    for pid in _pids(pattern):
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def _kill_pidfile(path: str) -> None:
    p = Path(path)
    if not p.exists():
        return
    try:
        pid = int(p.read_text().strip())
        os.kill(pid, 9)
    except Exception:
        pass
    try:
        p.unlink(missing_ok=True)
    except Exception:
        pass


def _alive_from_pidfile(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        return False
    try:
        pid = int(p.read_text().strip())
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def open_photoframe() -> str:
    try:
        if _debounce("open_photoframe"):
            return "已收到，正在切換到相框。"

        # already in desired state
        if _alive_from_pidfile(PHOTO_PID):
            return "相框已經是開啟狀態。"

        _kill_pidfile(BUNNY_PID)
        _kill_pidfile(PHOTO_PID)
        _kill_all("python src/ui/assistant_ui.py")
        _kill_all("run_photoframe.sh")
        _kill_all("/home/jh-pi/workspace/photoframe/main.py")
        time.sleep(0.2)
        subprocess.run(["bash", "-lc", PHOTO_CMD], check=False)
        time.sleep(0.6)

        # enforce singleton
        if _count("run_photoframe.sh") > 1:
            _kill_all("run_photoframe.sh")
            _kill_all("/home/jh-pi/workspace/photoframe/main.py")
            subprocess.run(["bash", "-lc", PHOTO_CMD], check=False)

        return "好的，已幫你打開相框。"
    except Exception as exc:
        return f"打開相框失敗：{exc}"


def open_bunny_ui() -> str:
    try:
        if _debounce("open_bunny"):
            return "已收到，正在切回兔兔。"

        # already in desired state
        if _alive_from_pidfile(BUNNY_PID):
            return "兔兔畫面已經開啟。"

        _kill_pidfile(PHOTO_PID)
        _kill_pidfile(BUNNY_PID)
        _kill_all("run_photoframe.sh")
        _kill_all("/home/jh-pi/workspace/photoframe/main.py")
        _kill_all("python src/ui/assistant_ui.py")
        time.sleep(0.2)
        subprocess.run(["bash", "-lc", BUNNY_CMD], check=False)
        time.sleep(0.6)

        # enforce singleton
        if _count("python src/ui/assistant_ui.py") > 1:
            _kill_all("python src/ui/assistant_ui.py")
            subprocess.run(["bash", "-lc", BUNNY_CMD], check=False)

        return "好的，已切回兔兔助理畫面。"
    except Exception as exc:
        return f"切回兔兔畫面失敗：{exc}"


@app.post("/zero-assistant", response_model=AssistResponse)
def zero_assistant(req: AssistRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")

    # ── Local skills (exec-plan 007) ────────────────────────────────────────
    # The skills package is the canonical dispatcher. The legacy
    # `open_photoframe()` / `open_bunny_ui()` helpers below are kept so
    # external callers (and 005-era tests that patch them) still work,
    # but the skill modules are the source of truth for new behavior.
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
        # Skill dispatcher must never break the API. Fall back to the
        # deprecated hard-coded routes below.
        print(f"[api] skill dispatcher error: {exc}", flush=True)

    # ── Deprecated hard-coded routes (TODO(007): remove after live verify) ──
    tl = text.lower()
    if ("打開" in text or "開啟" in text) and ("相框" in text or "photoframe" in tl):
        msg = open_photoframe()
        return AssistResponse(reply_text=msg, meta={"source": "local-command", "action": "open_photoframe"})

    if ("打開" in text or "開啟" in text or "切回" in text) and ("兔兔" in text or "bunny" in tl):
        msg = open_bunny_ui()
        return AssistResponse(reply_text=msg, meta={"source": "local-command", "action": "open_bunny"})

    # LLM path: default to fast local OpenAI; optionally route via OpenClaw agent when enabled
    # Detect search/browse/weather intent to allow a longer timeout
    SEARCH_TOKENS = (
        "查", "搜尋", "搜索", "找", "查詢", "查一下", "幫我查", "最新", "新聞",
        "網路上", "網頁", "資料", "天氣", "weather", "search", "look up", "find", "browse",
    )
    is_search = any(tok in text for tok in SEARCH_TOKENS)
    agent_timeout = 90 if is_search else 35
    # For openclaw CLI --timeout, give 5s less than subprocess timeout so it can clean up
    cli_timeout = agent_timeout - 5

    # Exec-plan 006: for search/weather, prefer fast OpenAI Responses + web_search tool.
    # OpenClaw remains as fallback below if this raises.
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
            print(f"[api] websearch failed: {exc}; falling back to openclaw", flush=True)

    if USE_OPENCLAW_AGENT:
        try:
            import json as _json

            def _extract_text(node):
                # Only trust payloads[].text — do NOT recurse into arbitrary keys,
                # otherwise upstream error strings (e.g. {"error": "400 ..."}) get
                # spoken back to the user as a valid reply. See exec-plan 005.
                if isinstance(node, dict):
                    payloads = (
                        node.get("result", {}).get("payloads")
                        if isinstance(node.get("result"), dict)
                        else node.get("payloads")
                    )
                    if isinstance(payloads, list):
                        for p in payloads:
                            if isinstance(p, dict) and isinstance(p.get("text"), str) and p.get("text").strip():
                                return p.get("text").strip()
                return ""

            cmd = [
                "openclaw", "agent", "--channel", "telegram",
                "--to", "8765443076", "--message", text,
                "--timeout", str(cli_timeout), "--json",
            ]
            # stderr must be separated from stdout; openclaw prints gateway
            # warning/fallback messages to stderr which corrupt the JSON on stdout.
            proc = subprocess.run(
                cmd, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=agent_timeout,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"openclaw non-zero exit {proc.returncode}; stderr={proc.stderr[:200]}"
                )
            out = proc.stdout.strip()
            if not out:
                raise RuntimeError(f"openclaw empty stdout; stderr={proc.stderr[:200]}")
            data = _json.loads(out)
            # OpenClaw may return status:"ok" but meta.stopReason:"error" when
            # the underlying agent failed (e.g. upstream LLM 400). In that case
            # payloads[].text contains the raw error string — must NOT be spoken.
            stop_reason = ""
            try:
                stop_reason = (
                    data.get("result", {}).get("meta", {}).get("stopReason", "")
                    if isinstance(data.get("result"), dict)
                    else data.get("meta", {}).get("stopReason", "")
                )
            except Exception:
                stop_reason = ""
            if isinstance(stop_reason, str) and stop_reason.lower() == "error":
                raise RuntimeError(f"openclaw stopReason=error; raw={out[:200]}")
            reply = _extract_text(data)
            if reply:
                return AssistResponse(reply_text=reply, meta={"source": "openclaw-agent", "search": is_search})
            # No usable text in payloads — likely an error JSON. Fall through to OpenAI.
            raise RuntimeError(f"openclaw returned no payload text; raw={out[:200]}")
        except subprocess.TimeoutExpired:
            if is_search:
                return AssistResponse(
                    reply_text="抱歉，這個問題我查比較久，請你等一下再問我一次。",
                    meta={"source": "openclaw-agent-timeout", "search": True},
                )
            # Non-search timeout: fall through to OpenAI fallback
        except Exception:
            pass

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
        return AssistResponse(reply_text=reply, meta={"model": OPENAI_MODEL, "source": "fallback-openai"})
    except Exception as exc:
        return AssistResponse(reply_text="抱歉，我剛剛出現錯誤。", meta={"error": str(exc)})
