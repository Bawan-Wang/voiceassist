"""Pure string-token helpers for local skill matching.

This module MUST stay free of FastAPI / OpenAI / subprocess imports so that
voice_bridge.py can import it cheaply at startup without dragging in the
whole API stack.
"""
from __future__ import annotations

PHOTOFRAME_TOKENS = {
    "相框", "相簿", "照片",
    "photoframe", "album", "photos", "photo frame",
}
BUNNY_TOKENS = {"兔兔", "bunny"}
VERB_TOKENS = {
    "打開", "開啟", "切到", "切去", "切回", "回到", "顯示", "看",
    "open", "show", "switch",
}


def _has_any(text: str, tokens: set[str]) -> bool:
    if not text:
        return False
    lower = text.lower()
    for tok in tokens:
        if tok in text or tok.lower() in lower:
            return True
    return False


def matches_photoframe(text: str) -> bool:
    """A command counts as 'open photoframe' when it mentions any
    photoframe noun. Verb is optional — '相框' alone is enough."""
    return _has_any(text, PHOTOFRAME_TOKENS)


def matches_bunny(text: str) -> bool:
    """'兔兔' / 'bunny' alone is enough to switch back to bunny UI."""
    return _has_any(text, BUNNY_TOKENS)


def is_local_skill(text: str) -> bool:
    """Cheap pre-check used by voice_bridge to decide whether to POST
    the utterance to /zero-assistant instead of streaming via GPT."""
    return matches_photoframe(text) or matches_bunny(text)
