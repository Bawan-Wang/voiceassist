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
WEATHER_SCRIPT = os.environ.get("ZERO_WEATHER_SCRIPT", "/home/jh-pi/workspace/weather/weather.py")
VOICE_DIR = Path("/home/jh-pi/.openclaw/workspace/voiceassist")
PHOTOFRAME_SCRIPT = str(VOICE_DIR / "run_photoframe.sh")
BUNNY_PID = "/tmp/voiceassist_bunny.pid"
PHOTO_PID = "/tmp/voiceassist_photo.pid"
BUNNY_CMD = f"cd {VOICE_DIR} && DISPLAY=:0 nohup .venv/bin/python ui/assistant_ui.py >/tmp/bunny_ui.log 2>&1 & echo $! > {BUNNY_PID}"
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


def parse_weather_intent(text: str) -> tuple[str, int]:
    """Extract (location, day_offset) from user query.
    day_offset: 0=today, 1=tomorrow, 2=day after, ..."""
    # Time intent
    day = 0
    if "昨天" in text:
        day = -1  # sentinel: unsupported
    elif "大後天" in text:
        day = 3
    elif "後天" in text:
        day = 2
    elif "明天" in text or "明日" in text:
        day = 1
    elif "今天" in text or "今日" in text or "現在" in text:
        day = 0

    # Location intent (add more cities as needed)
    location = "Taipei"  # default
    city_map = {
        "台北": "Taipei", "臺北": "Taipei",
        "台中": "Taichung", "臺中": "Taichung",
        "台南": "Tainan", "臺南": "Tainan",
        "高雄": "Kaohsiung",
        "東京": "Tokyo", "大阪": "Osaka", "京都": "Kyoto",
        "首爾": "Seoul", "釜山": "Busan",
        "北京": "Beijing", "上海": "Shanghai", "香港": "Hong Kong",
        "新加坡": "Singapore", "曼谷": "Bangkok",
        "紐約": "New York", "洛杉磯": "Los Angeles", "倫敦": "London",
        "巴黎": "Paris", "柏林": "Berlin", "雪梨": "Sydney",
    }
    for zh, en in city_map.items():
        if zh in text:
            location = en
            break

    return location, day


def run_weather(location: str = "Taipei", day: int = 0) -> str:
    if day < 0:
        return "抱歉，我只能查今天和未來 6 天的天氣，沒辦法查昨天喔。"
    try:
        out = subprocess.check_output(
            [WEATHER_SCRIPT, location, "--day", str(day)],
            text=True, stderr=subprocess.STDOUT, timeout=20
        )
        return out.strip()
    except Exception as exc:
        return f"天氣腳本執行失敗：{exc}"


def rewrite_weather_natural(raw_weather: str, query: str) -> str:
    """Turn rigid weather output into short conversational Chinese (1-2 sentences)."""
    try:
        from openai import OpenAI
        api_key = resolve_openai_key()
        if not api_key:
            return raw_weather
        client = OpenAI(api_key=api_key)
        prompt = [
            {
                "role": "system",
                "content": [{
                    "type": "input_text",
                    "text": "你是自然親切的語音助理。把天氣原始資料改寫成口語中文、1~2句、不用條列。保留重點：天氣、溫度區間、是否下雨、穿搭建議。"
                }]
            },
            {
                "role": "user",
                "content": [{
                    "type": "input_text",
                    "text": f"使用者問題：{query}\n\n天氣原始資料：\n{raw_weather}"
                }]
            }
        ]
        resp = client.responses.create(model=OPENAI_MODEL, input=prompt)
        for item in getattr(resp, "output", []):
            for c in getattr(item, "content", []):
                if getattr(c, "type", None) in ("output_text", "text") and getattr(c, "text", "").strip():
                    return c.text.strip()
        return raw_weather
    except Exception:
        return raw_weather


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
        _kill_all("python ui/assistant_ui.py")
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
        _kill_all("python ui/assistant_ui.py")
        time.sleep(0.2)
        subprocess.run(["bash", "-lc", BUNNY_CMD], check=False)
        time.sleep(0.6)

        # enforce singleton
        if _count("python ui/assistant_ui.py") > 1:
            _kill_all("python ui/assistant_ui.py")
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

    if ("打開" in text or "開啟" in text) and ("相框" in text or "photoframe" in tl):
        msg = open_photoframe()
        return AssistResponse(reply_text=msg, meta={"source": "local-command", "action": "open_photoframe"})

    if ("打開" in text or "開啟" in text or "切回" in text) and ("兔兔" in text or "bunny" in tl):
        msg = open_bunny_ui()
        return AssistResponse(reply_text=msg, meta={"source": "local-command", "action": "open_bunny"})

    # Weather: fetch real data, then rewrite naturally
    if "天氣" in text or "weather" in tl:
        location, day = parse_weather_intent(text)
        raw = run_weather(location, day)
        if day < 0:  # 昨天 → 直接回傳提示
            return AssistResponse(reply_text=raw, meta={"source": "weather-unsupported"})
        natural = rewrite_weather_natural(raw, text)
        return AssistResponse(reply_text=natural, meta={"source": "weather+rewrite", "location": location, "day": day})

    # LLM path: default to fast local OpenAI; optionally route via OpenClaw agent when enabled
    # Detect search/browse intent to allow a longer timeout
    SEARCH_TOKENS = (
        "查", "搜尋", "搜索", "找", "查詢", "查一下", "幫我查", "最新", "新聞",
        "網路上", "網頁", "資料", "search", "look up", "find", "browse",
    )
    is_search = any(tok in text for tok in SEARCH_TOKENS)
    agent_timeout = 90 if is_search else 35
    # For openclaw CLI --timeout, give 5s less than subprocess timeout so it can clean up
    cli_timeout = agent_timeout - 5

    if USE_OPENCLAW_AGENT:
        try:
            import json as _json

            def _extract_text(node):
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
                if isinstance(node, str):
                    return node.strip()
                if isinstance(node, dict):
                    for v in node.values():
                        got = _extract_text(v)
                        if got:
                            return got
                if isinstance(node, list):
                    for it in node:
                        got = _extract_text(it)
                        if got:
                            return got
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
            out = proc.stdout.strip()
            if not out:
                raise RuntimeError(f"openclaw empty stdout; stderr={proc.stderr[:200]}")
            data = _json.loads(out)
            reply = _extract_text(data)
            if reply:
                return AssistResponse(reply_text=reply, meta={"source": "openclaw-agent", "search": is_search})
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
