"""Local skill registry — see exec-plan 007.

A "skill" here is a small Python module exposing:
    NAME : str                  — short identifier ("open_photoframe", ...)
    match(text: str) -> bool    — cheap classifier
    run() -> str                — performs the action and returns the
                                  reply text to be spoken to the user.

The registry is a manual list (option A in 007) so import errors in any
single skill cannot silently disable the others. When the local LLM
tool-calling work lands, this same registry can be exposed as the
tool-call surface.
"""
from __future__ import annotations

from . import open_bunny, open_photoframe, tokens
from ._signal import SIGNAL_PATH  # noqa: F401  (re-export)

SKILLS = [open_photoframe, open_bunny]


def match_skill(text: str):
    """Return the first skill whose match(text) is True, else None."""
    if not text:
        return None
    for skill in SKILLS:
        try:
            if skill.match(text):
                return skill
        except Exception:  # pylint: disable=broad-except
            continue
    return None


def is_local_skill(text: str) -> bool:
    """Pure-string fast path used by voice_bridge before the heavy import."""
    return tokens.is_local_skill(text)


__all__ = ["SKILLS", "match_skill", "is_local_skill", "tokens", "SIGNAL_PATH"]
