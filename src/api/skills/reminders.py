from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Optional

from .time_query import LOCAL_TIMEZONE
from .reminder_store import add_reminder, read_pending, write_pending


@dataclass(frozen=True)
class ReminderParseResult:
    mode: str  # 'create' | 'need_time_detail' | 'confirm_candidate' | 'reject'
    task: Optional[str] = None
    when_iso: Optional[str] = None
    human_readable_time: Optional[str] = None
    candidate: Optional[dict] = None


# Patterns
_RELATIVE_MIN_RE = re.compile(r"(\d+)\s*分鐘後|(\d+)\s*分後")
_RELATIVE_HOUR_RE = re.compile(r"(\d+)\s*小時後|(\d+)\s*時後")
_ABSOLUTE_HM_RE = re.compile(r"(?:在)?(\d{1,2})(?:[:點:：\.](\d{1,2}))?\s*(?:am|pm|上午|下午)?")


def _now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def _parse_relative(text: str) -> Optional[tuple[datetime, str]]:
    m = _RELATIVE_MIN_RE.search(text)
    if m:
        minutes = int(m.group(1) or m.group(2))
        due = _now() + timedelta(minutes=minutes)
        return due, f"{minutes}分鐘後"
    m = _RELATIVE_HOUR_RE.search(text)
    if m:
        hours = int(m.group(1) or m.group(2))
        due = _now() + timedelta(hours=hours)
        return due, f"{hours}小時後"
    return None


def _parse_absolute(text: str) -> Optional[tuple[datetime, str]]:
    # simple hour[:minute] parser — interpret as local timezone
    m = _ABSOLUTE_HM_RE.search(text)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    # naive today at hour:minute in local tz
    now = _now()
    # create naive local datetime by replacing
    try:
        due = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except Exception:
        # invalid hour/minute
        return None
    if due <= now:
        # assume next day
        due = due + timedelta(days=1)
    return due, f"{hour}點{minute}分"


def parse_reminder(text: str) -> Optional[ReminderParseResult]:
    """Parse reminder-like utterances.

    Returns ReminderParseResult describing action to take or None when the
    utterance is not a reminder.
    """
    if not text:
        return None
    normalized = text.strip()
    lower = normalized.lower()

    # simple triggers
    if not ("提醒" in normalized or "提醒我" in normalized or "叫我" in normalized or "提醒一下" in normalized):
        return None

    # strip leading fillers
    task = normalized
    for prefix in ("兔兔助理", "請", "請幫我", "幫我", "麻煩我"):
        if task.startswith(prefix):
            task = task[len(prefix):].lstrip()

    # If there's an explicit relative time
    rel = _parse_relative(task)
    if rel:
        due, hr = rel
        # extract short task text after the time phrase, naive
        # e.g., "提醒我 10 分鐘後 吃藥"
        after = re.split(_RELATIVE_MIN_RE, task, maxsplit=1)
        # best-effort task extraction: take trailing part
        m = re.search(r"(?:後|後，|後，?)(.*)$", task)
        todo = m.group(1).strip() if m else "提醒事項"
        iso = due.astimezone().isoformat()
        return ReminderParseResult(mode="create", task=todo or "提醒事項", when_iso=iso, human_readable_time=hr)

    # absolute time like 在 14:30 / 在 14 點
    abs_ = _parse_absolute(task)
    if abs_:
        due, hr = abs_
        # extract task before or after?
        # e.g., "提醒我在14點吃藥" -> task after the time
        m = re.search(r"(?:在\s*\d{1,2}.?\d{0,2}.*?)(.*)$", task)
        todo = m.group(1).strip() if m else "提醒事項"
        iso = due.astimezone().isoformat()
        if todo:
            return ReminderParseResult(mode="create", task=todo or "提醒事項", when_iso=iso, human_readable_time=hr)
        # if no task, ask for what to remind
        return ReminderParseResult(mode="need_time_detail")

    # If contains '明天' + hour? naive
    m = re.search(r"明天.*?(\d{1,2})\s*(?:點|時)", task)
    if m:
        hour = int(m.group(1))
        now = _now()
        due = now + timedelta(days=1)
        due = due.replace(hour=hour, minute=0, second=0, microsecond=0)
        iso = due.astimezone().isoformat()
        todo = re.sub(r"明天.*?\d{1,2}\s*(?:點|時)", "", task).strip() or "提醒事項"
        return ReminderParseResult(mode="create", task=todo, when_iso=iso, human_readable_time=f"明天{hour}點")

    # If sentence is of form "提醒我做 X" with no time -> need_time_detail
    m = re.search(r"提醒我(.*)$", task)
    if m:
        content = m.group(1).strip()
        if content:
            # Ask for when
            candidate = {"task": content}
            return ReminderParseResult(mode="confirm_candidate", candidate=candidate)

    return ReminderParseResult(mode="reject")


def create_reminder_from_result(res: ReminderParseResult) -> dict | None:
    if res.mode != "create" or not res.when_iso:
        return None
    return add_reminder(res.task or "提醒事項", res.when_iso)


# pending follow-up handling helpers
def start_pending_confirmation(candidate: dict, ttl_sec: int = 60) -> dict:
    pending = {
        "candidate": candidate,
        "expires_at": (datetime.now().astimezone() + timedelta(seconds=ttl_sec)).isoformat(),
    }
    write_pending(pending)
    return pending


def accept_pending_confirmation() -> dict | None:
    p = read_pending()
    if not p:
        return None
    candidate = p.get("candidate")
    if not candidate:
        return None
    # candidate may contain task and optional when_iso
    when = candidate.get("when_iso")
    task = candidate.get("task") or "提醒事項"
    if when:
        entry = add_reminder(task, when)
        write_pending(None)
        return entry
    # if no when, cannot create
    return None


def cancel_pending() -> None:
    write_pending(None)
