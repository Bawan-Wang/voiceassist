"""Skill: open the photoframe (a.k.a. album) Kivy app and fade the bunny away."""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

from . import _signal
from ._paths import BUNNY_PID, PHOTO_PID, VOICE_DIR
from ._process_utils import (
    _alive_from_pidfile,
    _count,
    _kill_all,
    _kill_pidfile,
)
from .tokens import matches_photoframe

NAME = "open_photoframe"

PHOTOFRAME_SCRIPT = str(VOICE_DIR / "run_photoframe.sh")
PHOTO_LOG = "/tmp/photoframe.log"
PHOTO_READY = Path("/tmp/photoframe.ready")
PHOTO_CMD = (
    "DISPLAY=:0 nohup /home/jh-pi/.openclaw/workspace/voiceassist/run_photoframe.sh "
    f">{PHOTO_LOG} 2>&1 & echo $! > {PHOTO_PID}"
)

_LAST = {"ts": 0.0}


def match(text: str) -> bool:
    return matches_photoframe(text)


# --- public entry point -----------------------------------------------------

def run() -> str:
    try:
        now = time.time()
        if now - _LAST["ts"] < 2.5:
            return "已收到，正在切換到相框。"
        _LAST["ts"] = now

        if _alive_from_pidfile(PHOTO_PID):
            return "相框已經是開啟狀態。"

        # 1) Tell bunny UI to fade out gracefully (007 step 5).
        try:
            _signal.request_bunny_exit()
        except Exception:
            pass
        time.sleep(0.5)

        # 2) Hard-kill anything left over (fallback for older bunny without poller).
        _kill_pidfile(BUNNY_PID)
        _kill_pidfile(PHOTO_PID)
        _kill_all("python src/ui/assistant_ui.py")
        _kill_all("run_photoframe.sh")
        _kill_all("/home/jh-pi/workspace/photoframe/main.py")
        time.sleep(0.2)

        # 3) Clear stale ready marker before launching.
        try:
            PHOTO_READY.unlink(missing_ok=True)
        except Exception:
            pass

        # 4) Launch.
        subprocess.run(["bash", "-lc", PHOTO_CMD], check=False)
        time.sleep(0.6)

        if _count("run_photoframe.sh") > 1:
            _kill_all("run_photoframe.sh")
            _kill_all("/home/jh-pi/workspace/photoframe/main.py")
            subprocess.run(["bash", "-lc", PHOTO_CMD], check=False)

        # 5) Wait for the photoframe to declare itself ready (008 writes the
        # real ready file). If it never appears AND no process is alive,
        # report a truthful failure.
        deadline = time.time() + 1.5
        while time.time() < deadline:
            if PHOTO_READY.exists():
                break
            time.sleep(0.1)
        else:
            if not _alive_from_pidfile(PHOTO_PID) and _count("run_photoframe.sh") == 0:
                return f"相框打不開，可能少裝套件，請看 {PHOTO_LOG}。"

        return "好的，已幫你打開相框。"
    except Exception as exc:  # pylint: disable=broad-except
        return f"打開相框失敗：{exc}"
