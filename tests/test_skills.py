"""Tests for the local skill registry (exec-plan 007)."""
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from src.api.skills import (
    SKILLS,
    is_local_skill,
    match_skill,
    open_bunny,
    open_photoframe,
)
from src.api.skills import _signal
from src.api.skills.tokens import (
    matches_bunny,
    matches_photoframe,
)


# ── Token matching ─────────────────────────────────────────────────────────

class TestTokens:
    @pytest.mark.parametrize("text,expected", [
        ("打開相框", True),
        ("幫我打開相簿", True),
        ("切到照片", True),
        ("open photoframe", True),
        ("show me the album", True),
        ("打開 photos", True),
        ("你好", False),
        ("今天天氣如何", False),
    ])
    def test_photoframe_tokens(self, text, expected):
        assert matches_photoframe(text) is expected

    @pytest.mark.parametrize("text,expected", [
        ("切回兔兔", True),
        ("打開兔兔", True),
        ("switch to bunny", True),
        ("hello bunny", True),
        ("打開相框", False),
        ("你好", False),
    ])
    def test_bunny_tokens(self, text, expected):
        assert matches_bunny(text) is expected

    def test_is_local_skill(self):
        assert is_local_skill("打開相框")
        assert is_local_skill("切回兔兔")
        assert not is_local_skill("今天天氣如何")
        assert not is_local_skill("")


# ── Dispatcher ─────────────────────────────────────────────────────────────

class TestDispatcher:
    def test_match_returns_photoframe(self):
        assert match_skill("打開相簿") is open_photoframe

    def test_match_returns_bunny(self):
        assert match_skill("切回兔兔") is open_bunny

    def test_match_none_for_chitchat(self):
        assert match_skill("你好") is None

    def test_match_none_for_empty(self):
        assert match_skill("") is None

    def test_skills_have_required_attrs(self):
        for skill in SKILLS:
            assert hasattr(skill, "NAME")
            assert callable(getattr(skill, "match", None))
            assert callable(getattr(skill, "run", None))


# ── Signal file IPC ────────────────────────────────────────────────────────

class TestSignalFile:
    def test_atomic_write_and_read(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_signal, "SIGNAL_PATH", tmp_path / "sig.json")
        _signal.write(bunny_should_exit=True)
        data = _signal.read()
        assert data["bunny_should_exit"] is True
        assert "ts" in data

    def test_clear_bunny_exit(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_signal, "SIGNAL_PATH", tmp_path / "sig.json")
        _signal.request_bunny_exit()
        assert _signal.read()["bunny_should_exit"] is True
        _signal.clear_bunny_exit()
        assert _signal.read()["bunny_should_exit"] is False

    def test_read_missing_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_signal, "SIGNAL_PATH", tmp_path / "missing.json")
        assert _signal.read() == {}


# ── Skill execution (mock subprocess + signal IO) ──────────────────────────

@pytest.fixture
def mock_subprocess():
    """Mock all subprocess calls inside the skills."""
    pgrep_proc = MagicMock(stdout="", stderr="", returncode=0)
    with patch("src.api.skills.open_photoframe.subprocess.run", return_value=pgrep_proc) as m1, \
         patch("src.api.skills.open_bunny.subprocess.run", return_value=pgrep_proc) as m2:
        yield m1, m2


@pytest.fixture(autouse=True)
def reset_skill_debounce():
    """Each test starts with a clean debounce window."""
    open_photoframe._LAST["ts"] = 0.0
    open_bunny._LAST["ts"] = 0.0
    yield


@pytest.fixture
def isolate_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(_signal, "SIGNAL_PATH", tmp_path / "sig.json")


class TestOpenPhotoframeRun:
    def test_run_launches_when_not_alive(self, mock_subprocess, isolate_signal, tmp_path, monkeypatch):
        monkeypatch.setattr(open_photoframe, "PHOTO_PID", str(tmp_path / "photo.pid"))
        monkeypatch.setattr(open_photoframe, "BUNNY_PID", str(tmp_path / "bunny.pid"))
        monkeypatch.setattr(open_photoframe, "PHOTO_READY", tmp_path / "ready")
        # Skip the 1.0s wait by writing the ready file immediately.
        (tmp_path / "ready").touch()
        msg = open_photoframe.run()
        assert "好的" in msg or "相框" in msg

    def test_run_already_open_short_circuits(self, mock_subprocess, isolate_signal, tmp_path, monkeypatch):
        pid_file = tmp_path / "photo.pid"
        pid_file.write_text(str(os.getpid()))  # current process is alive
        monkeypatch.setattr(open_photoframe, "PHOTO_PID", str(pid_file))
        msg = open_photoframe.run()
        assert msg == "相框已經是開啟狀態。"

    def test_run_writes_bunny_exit_signal(self, mock_subprocess, isolate_signal, tmp_path, monkeypatch):
        monkeypatch.setattr(open_photoframe, "PHOTO_PID", str(tmp_path / "photo.pid"))
        monkeypatch.setattr(open_photoframe, "BUNNY_PID", str(tmp_path / "bunny.pid"))
        monkeypatch.setattr(open_photoframe, "PHOTO_READY", tmp_path / "ready")
        (tmp_path / "ready").touch()
        open_photoframe.run()
        assert _signal.read().get("bunny_should_exit") is True


class TestOpenBunnyRun:
    def test_run_launches_when_not_alive(self, mock_subprocess, isolate_signal, tmp_path, monkeypatch):
        monkeypatch.setattr(open_bunny, "BUNNY_PID", str(tmp_path / "bunny.pid"))
        monkeypatch.setattr(open_bunny, "PHOTO_PID", str(tmp_path / "photo.pid"))
        msg = open_bunny.run()
        assert "兔兔" in msg

    def test_run_already_open_short_circuits(self, mock_subprocess, isolate_signal, tmp_path, monkeypatch):
        pid_file = tmp_path / "bunny.pid"
        pid_file.write_text(str(os.getpid()))
        monkeypatch.setattr(open_bunny, "BUNNY_PID", str(pid_file))
        msg = open_bunny.run()
        assert msg == "兔兔畫面已經開啟。"

    def test_run_clears_bunny_exit_signal(self, mock_subprocess, isolate_signal, tmp_path, monkeypatch):
        monkeypatch.setattr(open_bunny, "BUNNY_PID", str(tmp_path / "bunny.pid"))
        monkeypatch.setattr(open_bunny, "PHOTO_PID", str(tmp_path / "photo.pid"))
        _signal.request_bunny_exit()  # pre-set
        open_bunny.run()
        assert _signal.read().get("bunny_should_exit") is False

    def test_run_requests_photoframe_exit_before_killing(
        self, mock_subprocess, isolate_signal, tmp_path, monkeypatch
    ):
        """008: open_bunny must signal photoframe to exit gracefully before kill -9."""
        monkeypatch.setattr(open_bunny, "BUNNY_PID", str(tmp_path / "bunny.pid"))
        monkeypatch.setattr(open_bunny, "PHOTO_PID", str(tmp_path / "photo.pid"))
        # speed up: skip the 0.6s graceful-exit wait
        monkeypatch.setattr(open_bunny.time, "sleep", lambda *_: None)
        open_bunny.run()
        assert _signal.read().get("photoframe_should_exit") is True
