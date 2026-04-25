"""Skill: bring the bunny assistant UI back to the foreground."""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from . import _signal
from .tokens import matches_bunny

NAME = "open_bunny"

VOICE_DIR = Path("/home/jh-pi/.openclaw/workspace/voiceassist")
BUNNY_PID = "/tmp/voiceassist_bunny.pid"
PHOTO_PID = "/tmp/voiceassist_photo.pid"
BUNNY_CMD = (
    f"cd {VOICE_DIR} && DISPLAY=:0 nohup .venv/bin/python src/ui/assistant_ui.py "
    f">/tmp/bunny_ui.log 2>&1 & echo $! > {BUNNY_PID}"
)

_LAST = {"ts": 0.0}


def match(text: str) -> bool:
    return matches_bunny(text)


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


def run() -> str:
    try:
        now = time.time()
        if now - _LAST["ts"] < 2.5:
            return "已收到，正在切回兔兔。"
        _LAST["ts"] = now

        if _alive_from_pidfile(BUNNY_PID):
            return "兔兔畫面已經開啟。"

        # Ask photoframe to exit (008 will honour this; 007 falls back to kill).
        try:
            _signal.request_photoframe_exit()
        except Exception:
            pass
        time.sleep(0.3)

        _kill_pidfile(PHOTO_PID)
        _kill_pidfile(BUNNY_PID)
        _kill_all("run_photoframe.sh")
        _kill_all("/home/jh-pi/workspace/photoframe/main.py")
        _kill_all("python src/ui/assistant_ui.py")
        time.sleep(0.2)

        # Reset bunny exit flag so the freshly launched UI doesn't immediately quit.
        try:
            _signal.clear_bunny_exit()
        except Exception:
            pass

        subprocess.run(["bash", "-lc", BUNNY_CMD], check=False)
        time.sleep(0.6)

        if _count("python src/ui/assistant_ui.py") > 1:
            _kill_all("python src/ui/assistant_ui.py")
            subprocess.run(["bash", "-lc", BUNNY_CMD], check=False)

        return "好的，已切回兔兔助理畫面。"
    except Exception as exc:  # pylint: disable=broad-except
        return f"切回兔兔畫面失敗：{exc}"
