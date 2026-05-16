"""Deterministic parser/formatter for time-query intents."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

LOCAL_TIMEZONE = "Asia/Taipei"

_ALIASES = {
    "台灣": ("Asia/Taipei", "台灣"),
    "台湾": ("Asia/Taipei", "台灣"),
    "台北": ("Asia/Taipei", "台北"),
    "taiwan": ("Asia/Taipei", "台灣"),
    "taipei": ("Asia/Taipei", "台北"),
    "日本": ("Asia/Tokyo", "日本"),
    "東京": ("Asia/Tokyo", "東京"),
    "东京": ("Asia/Tokyo", "東京"),
    "japan": ("Asia/Tokyo", "日本"),
    "tokyo": ("Asia/Tokyo", "東京"),
    "紐約": ("America/New_York", "紐約"),
    "纽约": ("America/New_York", "紐約"),
    "new york": ("America/New_York", "紐約"),
    "london": ("Europe/London", "倫敦"),
    "倫敦": ("Europe/London", "倫敦"),
    "伦敦": ("Europe/London", "倫敦"),
}

_TIME_TOKENS = ("幾點", "几点", "時間", "时间", "time", "what time")
_DATE_TOKENS = ("幾號", "几号", "日期", "date")
_WEEKDAY_TOKENS = ("星期幾", "星期几", "禮拜幾", "礼拜几", "週幾", "周几", "weekday")
_LOCAL_ALIASES = ("台灣", "台湾", "台北", "taiwan", "taipei")
_FILLER_PREFIXES = (
    "兔兔助理",
    "幫我看一下",
    "幫我看",
    "幫我查一下",
    "幫我查",
    "請問",
    "请问",
    "帮我看一下",
    "帮我看",
    "帮我查一下",
    "帮我查",
    "可以告訴我",
    "可以告诉我",
    "告訴我",
    "告诉我",
    "我想知道",
)
_GENERIC_PREFIXES = ("現在", "现在", "今天", "目前", "now", "today")
_TRAILING_FILLERS = "呢嗎呀啊了?？!！,，.。:： "


@dataclass(frozen=True)
class TimeQueryIntent:
    kind: str
    timezone: str | None
    label: str
    needs_clarification: bool = False


def _resolve_timezone_label(text: str) -> tuple[str, str]:
    lower = text.lower()
    for alias, (timezone_name, label) in _ALIASES.items():
        if alias in text or alias in lower:
            return timezone_name, label
    return "", ""


def _trim_candidate(text: str) -> str:
    candidate = text.strip(_TRAILING_FILLERS)
    candidate = re.sub(r"^[^，,。.!！？?\s]{1,8}助理[，,、。.!！？?\s]*", "", candidate)
    for prefix in _FILLER_PREFIXES:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):].lstrip(_TRAILING_FILLERS)
    return candidate.strip(_TRAILING_FILLERS)


def _extract_unknown_place(text: str, kind: str) -> str | None:
    patterns: tuple[str, ...]
    if kind == "time":
        patterns = (
            r"(?P<place>.+?)現在幾點(?:了)?",
            r"(?P<place>.+?)现在几点(?:了)?",
            r"(?P<place>.+?)時間(?:呢|嗎|呀|啊|了)?$",
            r"(?P<place>.+?)时间(?:呢|吗|呀|啊|了)?$",
            r"what time(?: is it)? in (?P<place>[a-z ]+)$",
        )
    elif kind == "date":
        patterns = (
            r"(?P<place>.+?)今天幾號",
            r"(?P<place>.+?)今天几号",
            r"date in (?P<place>[a-z ]+)$",
        )
    else:
        patterns = (
            r"(?P<place>.+?)(?:今天)?(?:星期幾|禮拜幾|週幾)",
            r"(?P<place>.+?)(?:今天)?(?:星期几|礼拜几|周几)",
            r"weekday in (?P<place>[a-z ]+)$",
        )

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is None:
            continue
        candidate = _trim_candidate(match.group("place"))
        if not candidate:
            continue
        lower = candidate.lower()
        if any(prefix == candidate or prefix == lower for prefix in _GENERIC_PREFIXES):
            continue
        if candidate in _LOCAL_ALIASES or lower in _LOCAL_ALIASES:
            continue
        return candidate

    return None


def parse_time_query(text: str) -> TimeQueryIntent | None:
    if not text:
        return None
    normalized = text.strip()
    lower = normalized.lower()
    has_now = any(tok in normalized or tok in lower for tok in ("現在", "现在", "目前", "now", "today"))

    kind: str | None = None
    if any(tok in normalized or tok in lower for tok in _WEEKDAY_TOKENS):
        kind = "weekday"
    elif any(tok in normalized or tok in lower for tok in _DATE_TOKENS):
        kind = "date"
    elif any(tok in normalized or tok in lower for tok in _TIME_TOKENS):
        kind = "time"

    if kind is None:
        return None

    timezone_name, label = _resolve_timezone_label(normalized)
    has_alias = bool(timezone_name)
    unknown_place = None if has_alias else _extract_unknown_place(normalized, kind)

    if kind == "time" and not has_alias and unknown_place is None and not has_now and "幾點" not in normalized and "what time" not in lower:
        return None

    if unknown_place is not None:
        return TimeQueryIntent(
            kind=kind,
            timezone=None,
            label=unknown_place,
            needs_clarification=True,
        )

    if not timezone_name:
        timezone_name, label = LOCAL_TIMEZONE, "台灣"

    return TimeQueryIntent(kind=kind, timezone=timezone_name, label=label)


def _format_period(hour_24: int) -> tuple[str, int]:
    if hour_24 == 0:
        return "凌晨", 12
    if 1 <= hour_24 <= 5:
        return "凌晨", hour_24
    if 6 <= hour_24 <= 11:
        return "上午", hour_24
    if hour_24 == 12:
        return "中午", 12
    if 13 <= hour_24 <= 17:
        return "下午", hour_24 - 12
    return "晚上", hour_24 - 12


def _weekday_name(weekday: int) -> str:
    return ("一", "二", "三", "四", "五", "六", "日")[weekday]


def render_time_query_reply(intent: TimeQueryIntent, *, now: datetime | None = None) -> str:
    if intent.needs_clarification or not intent.timezone:
        if intent.label:
            return f"抱歉，{intent.label}的時區我還不確定，你可以換個地名說法嗎？"
        return "抱歉，這個時區我還不確定，你可以換個地名說法嗎？"

    try:
        tz = ZoneInfo(intent.timezone)
    except ZoneInfoNotFoundError:
        return "抱歉，這個時區我還不確定，你可以換個地名說法嗎？"

    dt = (now or datetime.now(tz)).astimezone(tz)
    is_local = intent.timezone == LOCAL_TIMEZONE
    place = "" if is_local else f"{intent.label}"

    if intent.kind == "weekday":
        base = f"今天是星期{_weekday_name(dt.weekday())}"
        return f"{place}現在{base}。" if place else f"{base}。"

    if intent.kind == "date":
        base = f"{dt.year}年{dt.month}月{dt.day}日"
        return f"{place}今天是{base}。" if place else f"今天是{base}。"

    period, hour12 = _format_period(dt.hour)
    minute_part = "整" if dt.minute == 0 else f"{dt.minute}分"
    if place:
        return f"{place}現在時間是{period}{hour12}點{minute_part}。"
    return f"現在時間是{period}{hour12}點{minute_part}。"
