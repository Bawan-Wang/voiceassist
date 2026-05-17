"""Pure string-token helpers for local skill matching.

This module MUST stay free of FastAPI / OpenAI / subprocess imports so that
voice_bridge.py can import it cheaply at startup without dragging in the
whole API stack.
"""
from __future__ import annotations

import re

PHOTOFRAME_TOKENS = {
    "相框", "相簿", "照片",
    "photoframe", "album", "photos", "photo frame",
}
BUNNY_TOKENS = {"兔兔", "bunny"}
VERB_TOKENS = {
    "打開", "開啟", "切到", "切去", "切回", "回到", "顯示", "看",
    "open", "show", "switch",
}

SEARCH_TOKENS = (
    "查", "搜尋", "搜索", "找", "查詢", "查一下", "幫我查", "最新", "新聞",
    "網路上", "網頁", "資料", "天氣",
    "weather", "search", "look up", "find", "browse",
)

_WAKE_PREFIX_RE = re.compile(r"^[^，,。.!！？?\s]{1,8}助理[，,、。.!！？?\s]*")
_LEADING_FILLERS = (
    "兔兔助理",
    "兔助理",
    "幫我",
    "请帮我",
    "請幫我",
    "幫我把",
    "請",
    "请",
    "麻煩",
    "麻烦",
)
_TRAILING_PUNCT = "呢嗎呀啊了?？!！,，.。:： "
_ENGLISH_COMMAND_PREFIXES = (
    "open ",
    "show ",
    "show me ",
    "switch ",
    "switch to ",
)


def is_search_intent(text: str) -> bool:
    """Return True if the command looks like a search/browse request.

    Pure substring match — kept identical to the legacy implementations
    in ``src/api/app.py`` and ``src/bridge/voice_bridge.py`` to avoid
    behaviour drift during the refactor.
    """
    if not text:
        return False
    return any(tok in text for tok in SEARCH_TOKENS)


def _has_any(text: str, tokens: set[str]) -> bool:
    if not text:
        return False
    lower = text.lower()
    for tok in tokens:
        if tok in text or tok.lower() in lower:
            return True
    return False


def _normalize_command_text(text: str) -> tuple[str, str]:
    normalized = (text or "").strip()
    if not normalized:
        return "", ""

    normalized = _WAKE_PREFIX_RE.sub("", normalized).strip(_TRAILING_PUNCT)
    lowered = normalized.lower()
    for prefix in _LEADING_FILLERS:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):].lstrip(_TRAILING_PUNCT)
            lowered = normalized.lower()
            break
    return normalized, lowered


def _looks_like_command(text: str, lower: str) -> bool:
    if not text:
        return False
    if any(lower.startswith(prefix) for prefix in _ENGLISH_COMMAND_PREFIXES):
        return True
    return any(text.startswith(verb) for verb in VERB_TOKENS if not verb.isascii())


def matches_photoframe(text: str) -> bool:
    """Return True only for command-like photoframe requests."""
    normalized, lower = _normalize_command_text(text)
    if not _looks_like_command(normalized, lower):
        return False
    return _has_any(normalized, PHOTOFRAME_TOKENS)


def matches_bunny(text: str) -> bool:
    """Return True only for command-like bunny UI requests."""
    normalized, lower = _normalize_command_text(text)
    if not _looks_like_command(normalized, lower):
        return False
    return _has_any(normalized, BUNNY_TOKENS)


def is_local_skill(text: str) -> bool:
    """Cheap pre-check used by voice_bridge to decide whether to POST
    the utterance to /zero-assistant instead of streaming via GPT."""
    return matches_photoframe(text) or matches_bunny(text)
