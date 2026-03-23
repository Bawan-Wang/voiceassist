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


OPENAI_MODEL = os.environ.get("ZERO_OPENAI_MODEL", "gpt-5.3-codex")
WEATHER_SCRIPT = os.environ.get("ZERO_WEATHER_SCRIPT", "/home/jh-pi/workspace/weather/weather.py")
VOICE_DIR = Path("/home/jh-pi/.openclaw/workspace/voiceassist")
PHOTOFRAME_SCRIPT = str(VOICE_DIR / "run_photoframe.sh")
BUNNY_PID = "/tmp/voiceassist_bunny.pid"
PHOTO_PID = "/tmp/voiceassist_photo.pid"
BUNNY_CMD = f"cd {VOICE_DIR} && DISPLAY=:0 nohup .venv/bin/python main.py >/tmp/bunny_ui.log 2>&1 & echo $! > {BUNNY_PID}"
PHOTO_CMD = f"DISPLAY=:0 nohup /home/jh-pi/.openclaw/workspace/voiceassist/run_photoframe.sh >/tmp/photoframe.log 2>&1 & echo $! > {PHOTO_PID}"

_LAST_ACTION = {"name": "", "ts": 0.0}


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


def run_weather(location: str = "Taipei") -> str:
    try:
        out = subprocess.check_output([
            WEATHER_SCRIPT,
            location,
        ], text=True, stderr=subprocess.STDOUT, timeout=20)
        return out.strip()
    except Exception as exc:
        return f"天氣腳本執行失敗：{exc}"


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
        _kill_all("python main.py")
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
        _kill_all("python main.py")
        time.sleep(0.2)
        subprocess.run(["bash", "-lc", BUNNY_CMD], check=False)
        time.sleep(0.6)

        # enforce singleton
        if _count("python main.py") > 1:
            _kill_all("python main.py")
            subprocess.run(["bash", "-lc", BUNNY_CMD], check=False)

        return "好的，已切回兔兔助理畫面。"
    except Exception as exc:
        return f"切回兔兔畫面失敗：{exc}"


@app.post("/zero-assistant", response_model=AssistResponse)
def zero_assistant(req: AssistRequest):
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")

    # Local command intents first
    tl = text.lower()
    if "天氣" in text or "weather" in tl:
        weather = run_weather("Taipei")
        return AssistResponse(reply_text=weather, meta={"source": "local-weather"})

    if ("打開" in text or "開啟" in text) and ("相框" in text or "photoframe" in tl):
        msg = open_photoframe()
        return AssistResponse(reply_text=msg, meta={"source": "local-command", "action": "open_photoframe"})

    if ("打開" in text or "開啟" in text or "切回" in text) and ("兔兔" in text or "bunny" in tl):
        msg = open_bunny_ui()
        return AssistResponse(reply_text=msg, meta={"source": "local-command", "action": "open_bunny"})

    # LLM path: Copilot/OpenAI model
    try:
        from openai import OpenAI

        api_key = resolve_openai_key()
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not found")
        client = OpenAI(api_key=api_key)
        prompt = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": "你是 Rabbit Bunny，簡短、自然、親切回答，優先使用使用者語言。",
                    }
                ],
            },
            {"role": "user", "content": [{"type": "input_text", "text": text}]},
        ]
        resp = client.responses.create(model=OPENAI_MODEL, input=prompt)

        reply = ""
        if getattr(resp, "output", None):
            for item in resp.output:
                for content in getattr(item, "content", []):
                    if getattr(content, "type", None) in ("output_text", "text"):
                        reply = content.text
                        break
                if reply:
                    break

        if not reply:
            reply = "抱歉，我暫時無法產生回覆。"
        return AssistResponse(reply_text=reply, meta={"model": OPENAI_MODEL})
    except Exception as exc:
        return AssistResponse(reply_text="抱歉，我剛剛出現錯誤。", meta={"error": str(exc)})
