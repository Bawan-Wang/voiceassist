"""Shared filesystem paths for skill modules.

Tiny dependency-free module so any skill (or test) can import these
constants without dragging in subprocess / signal logic.
"""
from __future__ import annotations

from pathlib import Path

VOICE_DIR = Path("/home/jh-pi/.openclaw/workspace/voiceassist")
PHOTO_PID = "/tmp/voiceassist_photo.pid"
BUNNY_PID = "/tmp/voiceassist_bunny.pid"
