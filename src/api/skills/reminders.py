from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .reminder_store import add_reminder, clear_pending, read_pending, write_pending
from .time_query import LOCAL_TIMEZONE, resolve_timezone_alias

LOCAL_TIMEZONE_LABEL = "台灣"
REMINDER_TTL_SEC = 60

YES_TOKENS = ("好", "是", "對", "对", "可以", "行", "ok", "yes")
NO_TOKENS = ("不是", "不對", "不对", "不用了", "取消", "算了", "不要", "不用", "no")

_REMINDER_INTENT_RE = re.compile(r"提醒(?:我|一下)?|叫我")
_RELATIVE_MIN_RE = re.compile(r"(\d+)\s*(?:分鐘後|分钟后|分後|分后)")
_RELATIVE_HOUR_RE = re.compile(r"(\d+)\s*(?:小時後|小时后|時後|时后)")
_CLOCK_RE = re.compile(
    r"(?P<hour>\d{1,2})\s*(?P<sep>[:：點点時时])\s*(?:(?P<minute>\d{1,2})|(?P<half>半))?",
    re.IGNORECASE,
)
_UNKNOWN_TIMEZONE_RE = re.compile(r"(?P<place>[\u4e00-\u9fffA-Za-z ]{1,24})\s*(?:時間|时间|time)", re.IGNORECASE)
_TIME_NUMBER_RE = re.compile(r"([零一二三四五六七八九十兩两〇]+)(?=\s*(?:點|点|時|时|分鐘|分钟|分|小時|小时))")
_TIME_STRIP_RE = re.compile(r"^(?:改成|改到|改為|那改成|改一下|改一下成|改一下到)")

_DAY_TOKENS = (
    ("後天", 2, "後天"),
    ("后天", 2, "後天"),
    ("明天", 1, "明天"),
    ("今天", 0, "今天"),
)
_PERIOD_TOKENS = ("凌晨", "早上", "上午", "中午", "下午", "晚上", "傍晚")
_LEADING_FILLERS = (
    "兔兔助理",
    "請幫我",
    "请帮我",
    "幫我",
    "帮我",
    "請",
    "请",
    "麻煩",
    "麻烦",
)
_STRIP_TOKENS = (
    "提醒我",
    "提醒一下",
    "提醒",
    "叫我",
    "兔兔助理",
    "請幫我",
    "请帮我",
    "幫我",
    "帮我",
    "請",
    "请",
    "麻煩",
    "麻烦",
    "在",
    "於",
    "于",
    "時間",
    "时间",
    "time",
)
_PERIOD_TO_24H = {
    "凌晨": lambda hour: 0 if hour == 12 else hour,
    "早上": lambda hour: 0 if hour == 12 else hour,
    "上午": lambda hour: 0 if hour == 12 else hour,
    "中午": lambda hour: 12 if hour == 12 else hour + 12,
    "下午": lambda hour: 12 if hour == 12 else hour + 12,
    "傍晚": lambda hour: 12 if hour == 12 else hour + 12,
    "晚上": lambda hour: 0 if hour == 12 else hour + 12,
}


@dataclass(frozen=True)
class ReminderParseResult:
    mode: str
    task_text: str | None = None
    due_at: str | None = None
    spoken_label: str | None = None
    timezone: str | None = None
    timezone_label: str | None = None
    reason: str | None = None
    pending: dict[str, Any] | None = None
    candidate_due_at: str | None = None


@dataclass(frozen=True)
class ReminderOutcome:
    reply_text: str
    meta: dict[str, Any]
    entry: dict[str, Any] | None = None


@dataclass(frozen=True)
class _ClockInfo:
    day_offset: int | None
    day_label: str | None
    period_token: str | None
    hour: int | None
    minute: int | None
    fragments: tuple[str, ...]


def _normalize_text(text: str) -> str:
    candidate = _TIME_NUMBER_RE.sub(lambda match: str(_chinese_number_to_int(match.group(1))), (text or "").strip())
    candidate = re.sub(r"^[^，,。.!！？?\s]{1,8}助理[，,、。.!！？?\s]*", "", candidate)
    for prefix in _LEADING_FILLERS:
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):].lstrip(" ，,。.!！？?")
    return re.sub(r"\s+", " ", candidate).strip()


def _chinese_number_to_int(text: str) -> int:
    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "兩": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = 1 if not left else digits.get(left, 0)
        ones = 0 if not right else digits.get(right, 0)
        return tens * 10 + ones
    return digits.get(text, 0)


def _now_in_timezone(timezone_name: str, now: datetime | None = None) -> datetime:
    try:
        tz = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo(LOCAL_TIMEZONE)
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base.astimezone(tz)


def _extract_unknown_timezone(text: str) -> str | None:
    match = _UNKNOWN_TIMEZONE_RE.search(text)
    if match is None:
        return None
    place = match.group("place").strip(" ，,。.!！？?")
    return place or None


def _parse_relative(text: str, *, now: datetime | None = None) -> tuple[datetime, str, str] | None:
    now_local = _now_in_timezone(LOCAL_TIMEZONE, now)
    minute_match = _RELATIVE_MIN_RE.search(text)
    if minute_match:
        minutes = int(minute_match.group(1))
        return now_local + timedelta(minutes=minutes), f"{minutes}分鐘後", minute_match.group(0)

    hour_match = _RELATIVE_HOUR_RE.search(text)
    if hour_match:
        hours = int(hour_match.group(1))
        return now_local + timedelta(hours=hours), f"{hours}小時後", hour_match.group(0)
    return None


def _extract_clock_info(text: str) -> _ClockInfo | None:
    fragments: list[str] = []
    day_offset: int | None = None
    day_label: str | None = None
    period_token: str | None = None

    for token, offset, label in _DAY_TOKENS:
        if token in text:
            day_offset = offset
            day_label = label
            fragments.append(token)
            break

    for token in _PERIOD_TOKENS:
        if token in text:
            period_token = token
            fragments.append(token)
            break

    clock_match = _CLOCK_RE.search(text)
    if clock_match is None and day_offset is None and period_token is None:
        return None

    hour: int | None = None
    minute: int | None = None
    if clock_match is not None:
        hour = int(clock_match.group("hour"))
        minute = 30 if clock_match.group("half") else int(clock_match.group("minute") or 0)
        fragments.append(clock_match.group(0))

    return _ClockInfo(
        day_offset=day_offset,
        day_label=day_label,
        period_token=period_token,
        hour=hour,
        minute=minute,
        fragments=tuple(fragments),
    )


def _hour_to_24h(hour: int, period_token: str | None) -> int | None:
    if hour < 0:
        return None
    if period_token is None:
        return hour if hour <= 23 else None
    if hour > 12 or hour == 0:
        return None
    return _PERIOD_TO_24H[period_token](hour)


def _build_due_datetime(clock: _ClockInfo, *, timezone_name: str, now: datetime | None = None) -> datetime | None:
    if clock.hour is None or clock.minute is None:
        return None
    hour_24 = _hour_to_24h(clock.hour, clock.period_token)
    if hour_24 is None or clock.minute > 59:
        return None
    now_in_tz = _now_in_timezone(timezone_name, now)
    due = now_in_tz.replace(hour=hour_24, minute=clock.minute, second=0, microsecond=0)
    if clock.day_offset is not None:
        due = due + timedelta(days=clock.day_offset)
    return due


def _extract_task_text(text: str, *, fragments: tuple[str, ...]) -> str:
    candidate = text
    for fragment in fragments:
        if fragment:
            candidate = candidate.replace(fragment, " ")
    candidate = re.sub(r"[\u4e00-\u9fffA-Za-z ]{1,24}\s*(?:時間|时间|time)", " ", candidate, flags=re.IGNORECASE)
    for token in _STRIP_TOKENS:
        candidate = candidate.replace(token, " ")
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate.strip(" ，,。.!！？?")


def _relative_label_to_due_iso(due: datetime) -> str:
    return due.astimezone(timezone.utc).isoformat()


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


def _format_spoken_due(due_at: str, *, timezone_name: str, timezone_label: str, now: datetime | None = None) -> str:
    due = datetime.fromisoformat(due_at)
    now_in_tz = _now_in_timezone(timezone_name, now)
    due_in_tz = due.astimezone(now_in_tz.tzinfo)
    day_delta = (due_in_tz.date() - now_in_tz.date()).days
    if day_delta == 0:
        day_text = "今天"
    elif day_delta == 1:
        day_text = "明天"
    elif day_delta == 2:
        day_text = "後天"
    else:
        day_text = f"{due_in_tz.month}月{due_in_tz.day}日"
    period, hour12 = _format_period(due_in_tz.hour)
    minute_text = "整" if due_in_tz.minute == 0 else f"{due_in_tz.minute}分"
    zone_text = "" if timezone_name == LOCAL_TIMEZONE else f"{timezone_label}時間"
    return f"{zone_text}{day_text}{period}{hour12}點{minute_text}"


def _matches_token(text: str, tokens: tuple[str, ...]) -> bool:
    candidate = text.strip().lower()
    return any(candidate == token or candidate.startswith(token) for token in tokens)


def _reject(reason: str) -> ReminderParseResult:
    return ReminderParseResult(mode="reject", reason=reason)


def parse_reminder(text: str, *, now: datetime | None = None) -> Optional[ReminderParseResult]:
    if not text:
        return None

    normalized = _normalize_text(text)
    if not normalized or _REMINDER_INTENT_RE.search(normalized) is None:
        return None

    timezone_name, timezone_label = resolve_timezone_alias(normalized)
    if timezone_name is None:
        unknown_place = _extract_unknown_timezone(normalized)
        if unknown_place is not None:
            return _reject("unknown_timezone")
        timezone_name = LOCAL_TIMEZONE
        timezone_label = LOCAL_TIMEZONE_LABEL

    relative = _parse_relative(normalized, now=now)
    if relative is not None:
        due, spoken_label, fragment = relative
        task_text = _extract_task_text(normalized, fragments=(fragment,))
        if not task_text:
            return _reject("missing_task")
        return ReminderParseResult(
            mode="create",
            task_text=task_text,
            due_at=_relative_label_to_due_iso(due),
            spoken_label=spoken_label,
            timezone=LOCAL_TIMEZONE,
            timezone_label=LOCAL_TIMEZONE_LABEL,
        )

    clock = _extract_clock_info(normalized)
    if clock is None:
        return _reject("invalid_time")

    task_text = _extract_task_text(normalized, fragments=clock.fragments)
    if not task_text:
        return _reject("missing_task")

    if clock.hour is None:
        if clock.day_offset is None:
            return _reject("invalid_time")
        prefix = f"{clock.day_label or ''}{clock.period_token or ''}"
        return ReminderParseResult(
            mode="need_time_detail",
            task_text=task_text,
            timezone=timezone_name,
            timezone_label=timezone_label,
            pending={
                "time_hint_prefix": prefix,
            },
        )

    due = _build_due_datetime(clock, timezone_name=timezone_name, now=now)
    if due is None:
        return _reject("invalid_time")

    now_in_tz = _now_in_timezone(timezone_name, now)
    due_at = due.astimezone(timezone.utc).isoformat()
    spoken_label = _format_spoken_due(due_at, timezone_name=timezone_name, timezone_label=timezone_label or LOCAL_TIMEZONE_LABEL, now=now)

    if clock.day_offset is not None and due <= now_in_tz:
        return _reject("past_time")

    if clock.day_offset is None and due <= now_in_tz:
        candidate_due = due + timedelta(days=1)
        candidate_due_at = candidate_due.astimezone(timezone.utc).isoformat()
        candidate_spoken = _format_spoken_due(candidate_due_at, timezone_name=timezone_name, timezone_label=timezone_label or LOCAL_TIMEZONE_LABEL, now=now)
        return ReminderParseResult(
            mode="confirm_candidate",
            task_text=task_text,
            due_at=candidate_due_at,
            spoken_label=candidate_spoken,
            timezone=timezone_name,
            timezone_label=timezone_label,
            candidate_due_at=candidate_due_at,
            pending={
                "candidate_due_at": candidate_due_at,
            },
        )

    return ReminderParseResult(
        mode="create",
        task_text=task_text,
        due_at=due_at,
        spoken_label=spoken_label,
        timezone=timezone_name,
        timezone_label=timezone_label,
    )


def create_reminder_from_result(result: ReminderParseResult, *, source_text: str | None = None) -> dict[str, Any]:
    if result.mode != "create" or not result.due_at:
        raise ValueError("result is not a creatable reminder")
    return add_reminder(
        result.task_text or "提醒事項",
        result.due_at,
        source_text=source_text or result.task_text,
        timezone_name=result.timezone or LOCAL_TIMEZONE,
        timezone_label=result.timezone_label or LOCAL_TIMEZONE_LABEL,
    )


def start_pending_confirmation(
    result: ReminderParseResult,
    *,
    original_text: str,
    ttl_sec: int = REMINDER_TTL_SEC,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _now_in_timezone(result.timezone or LOCAL_TIMEZONE, now)
    pending = {
        "mode": result.mode,
        "original_text": original_text,
        "task_text": result.task_text,
        "timezone": result.timezone or LOCAL_TIMEZONE,
        "timezone_label": result.timezone_label or LOCAL_TIMEZONE_LABEL,
        "created_at": current.astimezone(timezone.utc).isoformat(),
        "expires_at": (current + timedelta(seconds=ttl_sec)).astimezone(timezone.utc).isoformat(),
    }
    if result.pending:
        pending.update(result.pending)
    write_pending(pending)
    return pending


def get_active_pending(*, now: datetime | None = None) -> dict[str, Any] | None:
    pending = read_pending()
    if not pending:
        return None
    expires_at = pending.get("expires_at")
    try:
        exp_dt = datetime.fromisoformat(str(expires_at))
    except (TypeError, ValueError):
        clear_pending()
        return None
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if current > exp_dt:
        clear_pending()
        return None
    return pending


def has_pending_confirmation(*, now: datetime | None = None) -> bool:
    return get_active_pending(now=now) is not None


def accept_pending_confirmation(*, now: datetime | None = None) -> dict[str, Any] | None:
    pending = get_active_pending(now=now)
    if not pending or pending.get("mode") != "confirm_candidate":
        return None
    candidate_due_at = pending.get("candidate_due_at")
    if not candidate_due_at:
        clear_pending()
        return None
    entry = add_reminder(
        str(pending.get("task_text") or "提醒事項"),
        str(candidate_due_at),
        source_text=str(pending.get("original_text") or pending.get("task_text") or "提醒事項"),
        timezone_name=str(pending.get("timezone") or LOCAL_TIMEZONE),
        timezone_label=str(pending.get("timezone_label") or LOCAL_TIMEZONE_LABEL),
    )
    clear_pending()
    return entry


def cancel_pending() -> None:
    clear_pending()


def _build_reject_outcome(reason: str) -> ReminderOutcome:
    replies = {
        "missing_task": "請把提醒內容也一起告訴我。",
        "unknown_timezone": "這個時區我還不確定，請換個地名說法再說一次完整提醒。",
        "past_time": "現在這個時間已經過了，請再說一個新的提醒時間。",
        "invalid_time": "這個提醒時間我還沒辦法確定，請再說得完整一點。",
        "store_write_failed": "抱歉，提醒暫時沒有存成功，請再試一次。",
    }
    return ReminderOutcome(
        reply_text=replies.get(reason, replies["invalid_time"]),
        meta={
            "source": "local-skill",
            "action": "create_reminder",
            "reminder_status": "rejected",
            "reason": reason,
        },
    )


def execute_reminder_request(text: str, *, now: datetime | None = None) -> ReminderOutcome:
    result = parse_reminder(text, now=now)
    if result is None:
        return _build_reject_outcome("invalid_time")

    if result.mode == "reject":
        return _build_reject_outcome(result.reason or "invalid_time")

    if result.mode == "create":
        try:
            entry = create_reminder_from_result(result, source_text=text)
        except Exception:
            return _build_reject_outcome("store_write_failed")
        return ReminderOutcome(
            reply_text=f"好，我會在{result.spoken_label}提醒你{result.task_text}。",
            meta={
                "source": "local-skill",
                "action": "create_reminder",
                "reminder_id": entry["id"],
                "due_at": entry["due_at"],
                "timezone": entry["timezone"],
            },
            entry=entry,
        )

    pending = start_pending_confirmation(result, original_text=text, now=now)
    if result.mode == "need_time_detail":
        prefix = str(pending.get("time_hint_prefix") or "")
        return ReminderOutcome(
            reply_text=f"你想要{prefix}幾點提醒呢？",
            meta={
                "source": "local-skill",
                "action": "confirm_reminder",
                "confirmation_mode": "need_time_detail",
                "expires_at": pending["expires_at"],
                "candidate_due_at": None,
                "timezone": pending["timezone"],
            },
        )

    return ReminderOutcome(
        reply_text=f"現在已經過了這個時間，你是要我在{result.spoken_label}提醒你{result.task_text}嗎？",
        meta={
            "source": "local-skill",
            "action": "confirm_reminder",
            "confirmation_mode": "confirm_candidate",
            "expires_at": pending["expires_at"],
            "candidate_due_at": pending.get("candidate_due_at"),
            "timezone": pending["timezone"],
        },
    )


def handle_pending_follow_up(text: str, *, now: datetime | None = None) -> ReminderOutcome | None:
    pending = get_active_pending(now=now)
    if pending is None:
        return None

    normalized = _normalize_text(text)
    if not normalized:
        clear_pending()
        return None

    mode = str(pending.get("mode") or "")
    if mode == "confirm_candidate" and _matches_token(normalized, YES_TOKENS):
        try:
            entry = accept_pending_confirmation(now=now)
        except Exception:
            return _build_reject_outcome("store_write_failed")
        if entry is None:
            return _build_reject_outcome("invalid_time")
        return ReminderOutcome(
            reply_text=f"好，我會在{_format_spoken_due(entry['due_at'], timezone_name=entry['timezone'], timezone_label=entry['timezone_label'], now=now)}提醒你{entry['task_text']}。",
            meta={
                "source": "local-skill",
                "action": "create_reminder",
                "reminder_id": entry["id"],
                "due_at": entry["due_at"],
                "timezone": entry["timezone"],
            },
            entry=entry,
        )

    if mode == "confirm_candidate" and _matches_token(normalized, NO_TOKENS):
        clear_pending()
        return ReminderOutcome(
            reply_text="好，那我先不建立這個提醒。",
            meta={
                "source": "local-skill",
                "action": "cancel_reminder",
            },
        )

    if mode == "need_time_detail" and (_matches_token(normalized, YES_TOKENS) or _matches_token(normalized, NO_TOKENS)):
        clear_pending()
        return None

    if mode == "need_time_detail":
        synthetic_text = f"{pending.get('time_hint_prefix', '')}{normalized}提醒我{pending.get('task_text', '提醒事項')}"
    else:
        replacement = _TIME_STRIP_RE.sub("", normalized).strip()
        synthetic_text = f"{replacement}提醒我{pending.get('task_text', '提醒事項')}"

    result = parse_reminder(synthetic_text, now=now)
    clear_pending()
    if result is None:
        return None
    if result.mode == "create":
        try:
            entry = create_reminder_from_result(result, source_text=str(pending.get("original_text") or synthetic_text))
        except Exception:
            return _build_reject_outcome("store_write_failed")
        return ReminderOutcome(
            reply_text=f"好，我會在{result.spoken_label}提醒你{result.task_text}。",
            meta={
                "source": "local-skill",
                "action": "create_reminder",
                "reminder_id": entry["id"],
                "due_at": entry["due_at"],
                "timezone": entry["timezone"],
            },
            entry=entry,
        )
    if result.mode == "reject":
        return _build_reject_outcome(result.reason or "invalid_time")
    return None
