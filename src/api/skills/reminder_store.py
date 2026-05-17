from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from datetime import datetime
import uuid

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

REMINDERS_PATH = DATA_DIR / "reminders.json"
PENDING_PATH = DATA_DIR / "reminder_pending.json"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _atomic_write(path: Path, obj: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_reminders() -> list[dict]:
    return _load_json(REMINDERS_PATH, [])


def add_reminder(task: str, due_iso: str) -> dict:
    reminders = list_reminders()
    entry = {
        "id": str(uuid.uuid4()),
        "task": task,
        "due": due_iso,
        "created": datetime.now().astimezone().isoformat(),
        "delivered": False,
    }
    reminders.append(entry)
    _atomic_write(REMINDERS_PATH, reminders)
    return entry


def write_pending(pending: dict | None) -> None:
    if pending is None:
        PENDING_PATH.unlink(missing_ok=True)
        return
    _atomic_write(PENDING_PATH, pending)


def read_pending() -> dict | None:
    return _load_json(PENDING_PATH, None)


def clear_pending() -> None:
    write_pending(None)
