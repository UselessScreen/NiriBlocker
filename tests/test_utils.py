"""Tests for daemon.utils helpers."""

from __future__ import annotations

import subprocess

import pytest

from daemon import utils


def test_show_notification_success(monkeypatch):
    calls = []

    def fake_run(cmd, capture_output, timeout):
        calls.append((cmd, capture_output, timeout))

    monkeypatch.setattr(utils.subprocess, "run", fake_run)

    assert utils.show_notification("Title", "Body", urgency="critical") is True
    assert calls == [(["notify-send", "-u", "critical", "Title", "Body"], True, 5)]


def test_show_notification_returns_false_on_subprocess_error(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise subprocess.SubprocessError("boom")

    monkeypatch.setattr(utils.subprocess, "run", fake_run)
    assert utils.show_notification("T", "M") is False


def test_show_notification_returns_false_when_binary_missing(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(utils.subprocess, "run", fake_run)
    assert utils.show_notification("T", "M") is False


def test_get_xdg_config_dir_uses_env(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-config")
    assert utils.get_xdg_config_dir() == "/tmp/xdg-config/hyprblocker"


def test_get_xdg_config_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(utils.os.path, "expanduser", lambda _: "/home/test/.config/hyprblocker")
    assert utils.get_xdg_config_dir() == "/home/test/.config/hyprblocker"


def test_get_xdg_data_dir_uses_env(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "/tmp/xdg-data")
    assert utils.get_xdg_data_dir() == "/tmp/xdg-data/hyprblocker"


def test_get_xdg_data_dir_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setattr(utils.os.path, "expanduser", lambda _: "/home/test/.local/share/hyprblocker")
    assert utils.get_xdg_data_dir() == "/home/test/.local/share/hyprblocker"


def test_ensure_directories_creates_config_and_data_dirs(monkeypatch):
    monkeypatch.setattr(utils, "get_xdg_config_dir", lambda: "/cfg")
    monkeypatch.setattr(utils, "get_xdg_data_dir", lambda: "/data")
    calls = []

    def fake_makedirs(path, exist_ok):
        calls.append((path, exist_ok))

    monkeypatch.setattr(utils.os, "makedirs", fake_makedirs)

    utils.ensure_directories()

    assert calls == [("/cfg", True), ("/data", True)]


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (5, "5s"),
        (60, "1m"),
        (61, "1m 1s"),
        (3599, "59m 59s"),
        (3600, "1h"),
        (3660, "1h 1m"),
        (86400, "1d"),
        (90000, "1d 1h"),
    ],
)
def test_format_duration(seconds, expected):
    assert utils.format_duration(seconds) == expected
