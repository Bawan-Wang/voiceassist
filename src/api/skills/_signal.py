"""Shared IPC signal file at /tmp/voiceassist_signal.json.

Contract (see exec-plan 007):
    {
      "bunny_should_exit": bool,
      "photoframe_should_exit": bool,
      "ts": int (unix seconds)
    }

Writers (voiceassist skills) use atomic write via tempfile + os.replace.
Readers (assistant_ui.py for 007, photoframe main.py for 008) tolerate
missing/partial files.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

SIGNAL_PATH = Path("/tmp/voiceassist_signal.json")


def read() -> dict[str, Any]:
    try:
        with SIGNAL_PATH.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return {}


def write(**kwargs: Any) -> None:
    """Merge `kwargs` into the existing signal file and persist atomically."""
    current = read()
    current.update(kwargs)
    current["ts"] = int(time.time())

    fd, tmp = tempfile.mkstemp(prefix=".voiceassist_signal.", dir="/tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(current, fh, ensure_ascii=False)
        os.replace(tmp, SIGNAL_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def request_bunny_exit() -> None:
    write(bunny_should_exit=True)


def clear_bunny_exit() -> None:
    write(bunny_should_exit=False)


def request_photoframe_exit() -> None:
    write(photoframe_should_exit=True)


def clear_photoframe_exit() -> None:
    write(photoframe_should_exit=False)
