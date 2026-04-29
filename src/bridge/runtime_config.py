from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.yaml"


def load_app_config(config_path: str | Path | None = None) -> tuple[Path, dict[str, Any]]:
    """Strictly load ``config.yaml``.

    Plan 016 made yaml the single source of truth: no dict-layer
    defaults, no deep-merge. The file must exist and contain a
    top-level ``voiceBridge`` key.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_absolute():
        path = PROJECT_DIR / path

    if not path.exists():
        raise FileNotFoundError(f"config.yaml not found at {path}")

    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}

    if "voiceBridge" not in loaded:
        raise ValueError(f"{path} is missing the top-level 'voiceBridge' key")

    return path, loaded


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def get_selected_provider(config: dict[str, Any], section_name: str) -> tuple[str, dict[str, Any]]:
    section = config.get(section_name, {})
    active_name = section.get("active")
    providers = section.get("providers", {})
    if not active_name:
        raise ValueError(f"voiceBridge.{section_name}.active is required")
    if active_name not in providers:
        raise ValueError(
            f"voiceBridge.{section_name}.active={active_name!r} not found in providers"
        )
    provider_config = dict(providers[active_name])
    provider_config.setdefault("name", active_name)
    return active_name, provider_config
