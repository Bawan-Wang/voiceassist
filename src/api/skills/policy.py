"""Shared request-classification policy for API and voice entrypoints."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .tokens import is_search_intent
from .time_query import TimeQueryIntent, parse_time_query


class RouteKind(str, Enum):
    LOCAL_SKILL = "local_skill"
    TIME_QUERY = "time_query"
    TOOL_NEEDED = "tool_needed"
    CHAT = "chat"


@dataclass(frozen=True)
class RouteDecision:
    kind: RouteKind
    routed_text: str
    skill: Any | None = None
    time_query: TimeQueryIntent | None = None
    is_search: bool = False
    used_raw_transcript: bool = False


def _normalize_text(text: str | None) -> str:
    return (text or "").strip()


def _match_local_skill(text: str) -> Any | None:
    if not text:
        return None
    try:
        # Lazy import keeps module import cheap for voice_bridge startup.
        from . import match_skill

        return match_skill(text)
    except Exception:  # pylint: disable=broad-except
        return None


def classify_request(text: str, *, raw_transcript: str | None = None) -> RouteDecision:
    """Classify a text request with pre-020 precedence rules.

    Route order is intentionally explicit:
      1. local skill
      2. tool-needed/search
      3. chat

    Only local-skill detection is allowed to fall back to ``raw_transcript``.
    This preserves the voice bridge behavior where wake stripping can eat the
    noun in phrases like ``兔兔助理切回兔兔``.
    """

    normalized_text = _normalize_text(text)
    normalized_raw = _normalize_text(raw_transcript)

    skill = _match_local_skill(normalized_text)
    if skill is not None:
        return RouteDecision(
            kind=RouteKind.LOCAL_SKILL,
            routed_text=normalized_text,
            skill=skill,
        )

    if normalized_raw and normalized_raw != normalized_text:
        raw_skill = _match_local_skill(normalized_raw)
        if raw_skill is not None:
            return RouteDecision(
                kind=RouteKind.LOCAL_SKILL,
                routed_text=normalized_raw,
                skill=raw_skill,
                used_raw_transcript=True,
            )

    time_query = parse_time_query(normalized_text)
    if time_query is not None:
        return RouteDecision(
            kind=RouteKind.TIME_QUERY,
            routed_text=normalized_text,
            time_query=time_query,
        )

    if is_search_intent(normalized_text):
        return RouteDecision(
            kind=RouteKind.TOOL_NEEDED,
            routed_text=normalized_text,
            is_search=True,
        )

    return RouteDecision(kind=RouteKind.CHAT, routed_text=normalized_text)
