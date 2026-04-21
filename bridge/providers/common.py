from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Iterable


class DownloadError(RuntimeError):
    pass


def ensure_files(downloads: Iterable[tuple[str, Path]]) -> None:
    for url, target_path in downloads:
        if target_path.exists():
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")
        try:
            print(f"[provider] Downloading {url} -> {target_path}")
            urllib.request.urlretrieve(url, tmp_path)
            tmp_path.replace(target_path)
        except Exception as exc:  # pylint: disable=broad-except
            tmp_path.unlink(missing_ok=True)
            raise DownloadError(f"Failed downloading {url}: {exc}") from exc
