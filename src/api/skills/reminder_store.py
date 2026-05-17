from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from .time_query import LOCAL_TIMEZONE

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
LEGACY_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

REMINDERS_PATH = DATA_DIR / "reminders.json"
PENDING_PATH = DATA_DIR / "reminder_pending.json"
LEGACY_REMINDERS_PATH = LEGACY_DATA_DIR / "reminders.json"
LEGACY_PENDING_PATH = LEGACY_DATA_DIR / "reminder_pending.json"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _atomic_write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _to_utc_iso(iso_text: str, *, fallback_now: bool = False) -> str:
    try:
        dt = datetime.fromisoformat(iso_text)
    except ValueError:
        if not fallback_now:
            raise
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _normalize_entry(raw: dict[str, Any]) -> dict[str, Any]:
    task_text = str(raw.get("task_text") or raw.get("task") or "提醒事項")
    timezone_name = str(raw.get("timezone") or LOCAL_TIMEZONE)
    timezone_label = str(raw.get("timezone_label") or "台灣")
    due_source = raw.get("due_at") or raw.get("due") or datetime.now(timezone.utc).isoformat()
    created_source = raw.get("created_at") or raw.get("created") or datetime.now(timezone.utc).isoformat()
    delivered_at = raw.get("delivered_at")
    status = raw.get("status")
    if not status:
        status = "delivered" if raw.get("delivered") else "pending"

    return {
        "id": str(raw.get("id") or f"rmd_{uuid.uuid4().hex[:12]}").strip(),
        "task_text": task_text,
        "source_text": str(raw.get("source_text") or task_text),
        "timezone": timezone_name,
        "timezone_label": timezone_label,
        "due_at": _to_utc_iso(str(due_source), fallback_now=True),
        "created_at": _to_utc_iso(str(created_source), fallback_now=True),
        "status": "delivered" if status == "delivered" else "pending",
        "delivered_at": _to_utc_iso(str(delivered_at), fallback_now=True) if delivered_at else None,
    }


def _load_reminder_entries(path: Path) -> list[dict[str, Any]]:
    payload = _load_json(path, None)
    if payload is None:
        return []
    if isinstance(payload, list):
        return [_normalize_entry(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        reminders = payload.get("reminders", [])
        if isinstance(reminders, list):
            return [_normalize_entry(item) for item in reminders if isinstance(item, dict)]
    return []


def _write_reminder_entries(reminders: list[dict[str, Any]]) -> None:
    _atomic_write(
        REMINDERS_PATH,
        {
            "version": 1,
            "reminders": reminders,
        },
    )


def list_reminders() -> list[dict[str, Any]]:
    reminders = _load_reminder_entries(REMINDERS_PATH)
    if reminders:
        return reminders
    if REMINDERS_PATH != LEGACY_REMINDERS_PATH:
        return _load_reminder_entries(LEGACY_REMINDERS_PATH)
    return []


def add_reminder(
    task: str,
    due_iso: str,
    *,
    source_text: str | None = None,
    timezone_name: str = LOCAL_TIMEZONE,
    timezone_label: str = "台灣",
    created_at: str | None = None,
) -> dict[str, Any]:
    reminders = list_reminders()
    created_iso = _to_utc_iso(created_at, fallback_now=True) if created_at else datetime.now(timezone.utc).isoformat()
    entry = {
        "id": f"rmd_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}",
        "task_text": task,
        "source_text": source_text or task,
        "timezone": timezone_name,
        "timezone_label": timezone_label,
        "due_at": _to_utc_iso(due_iso),
        "created_at": created_iso,
        "status": "pending",
        "delivered_at": None,
    }
    reminders.append(entry)
    _write_reminder_entries(reminders)
    return entry


def write_pending(pending: dict[str, Any] | None) -> None:
    if pending is None:
        PENDING_PATH.unlink(missing_ok=True)
        return
    _atomic_write(PENDING_PATH, pending)


def read_pending() -> dict[str, Any] | None:
    payload = _load_json(PENDING_PATH, None)
    if isinstance(payload, dict):
        return payload
    if PENDING_PATH != LEGACY_PENDING_PATH:
        legacy = _load_json(LEGACY_PENDING_PATH, None)
        if isinstance(legacy, dict):
            return legacy
    return None


def clear_pending() -> None:
    write_pending(None)


def mark_delivered(reminder_id: str, *, delivered_at: str | None = None) -> None:
    reminders = list_reminders()
    changed = False
    delivered_iso = _to_utc_iso(delivered_at, fallback_now=True) if delivered_at else datetime.now(timezone.utc).isoformat()
    for reminder in reminders:
        if reminder.get("id") != reminder_id:
            continue
        reminder["status"] = "delivered"
        reminder["delivered_at"] = delivered_iso
        changed = True
        break
    if changed:
        _write_reminder_entries(reminders)
