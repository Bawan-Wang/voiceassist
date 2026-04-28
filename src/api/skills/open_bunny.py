"""Skill: bring the bunny assistant UI back to the foreground."""
from __future__ import annotations

import subprocess
import time

from . import _signal
from ._paths import BUNNY_PID, PHOTO_PID, VOICE_DIR
from ._process_utils import (
    _alive_from_pidfile,
    _count,
    _kill_all,
    _kill_pidfile,
)
from .tokens import matches_bunny

NAME = "open_bunny"

BUNNY_CMD = (
    f"cd {VOICE_DIR} && DISPLAY=:0 nohup .venv/bin/python src/ui/assistant_ui.py "
    f">/tmp/bunny_ui.log 2>&1 & echo $! > {BUNNY_PID}"
)

_LAST = {"ts": 0.0}


def match(text: str) -> bool:
    return matches_bunny(text)


def run() -> str:
    try:
        now = time.time()
        if now - _LAST["ts"] < 2.5:
            return "已收到，正在切回兔兔。"
        _LAST["ts"] = now

        if _alive_from_pidfile(BUNNY_PID):
            return "兔兔畫面已經開啟。"

        # Ask photoframe to exit gracefully (008 honours this; older builds
        # ignore the signal and rely on the kill -9 fallback below).
        try:
            _signal.request_photoframe_exit()
        except Exception:
            pass
        # Give photoframe time to run its own fade-out (0.4s) + cleanup.
        time.sleep(0.6)

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
