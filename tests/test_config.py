"""Tests for daemon.config behavior and migration logic."""

from __future__ import annotations

import json

from daemon import config as config_module


LEGACY_BROWSERS = [
    "firefox",
    "firefox-esr",
    "chromium",
    "google-chrome",
    "brave-browser",
    "microsoft-edge",
    "opera",
    "vivaldi-stable",
]


def test_load_config_creates_defaults_when_missing(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "get_config_path", lambda: str(config_path))

    cfg = config_module.load_config()

    assert config_path.exists()
    assert cfg.daemon.host == "127.0.0.1"
    assert cfg.security.browser_enforcement_enabled is True
    payload = json.loads(config_path.read_text())
    assert payload["browsers"] == config_module.DEFAULT_BROWSERS


def test_load_config_migrates_dev_mode_and_legacy_browsers(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "daemon": {"host": "0.0.0.0", "port": 1234},
                "security": {"dev_mode": False},
                "browsers": LEGACY_BROWSERS,
            }
        )
    )
    monkeypatch.setattr(config_module, "get_config_path", lambda: str(config_path))

    cfg = config_module.load_config()

    assert cfg.daemon.host == "0.0.0.0"
    assert cfg.daemon.port == 1234
    assert cfg.security.browser_enforcement_enabled is True
    assert cfg.browsers == config_module.DEFAULT_BROWSERS


def test_load_config_drops_legacy_dev_mode_when_new_field_present(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "security": {
                    "dev_mode": False,
                    "browser_enforcement_enabled": False,
                }
            }
        )
    )
    monkeypatch.setattr(config_module, "get_config_path", lambda: str(config_path))

    cfg = config_module.load_config()

    assert cfg.security.browser_enforcement_enabled is False


def test_load_config_falls_back_to_defaults_for_invalid_json(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text("{invalid")
    monkeypatch.setattr(config_module, "get_config_path", lambda: str(config_path))

    cfg = config_module.load_config()

    assert isinstance(cfg, config_module.Config)
    assert cfg.daemon.port == 8765


def test_save_config_persists_all_sections(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(config_module, "get_config_path", lambda: str(config_path))

    cfg = config_module.Config(
        daemon=config_module.DaemonConfig(host="0.0.0.0", port=9999, log_level="DEBUG"),
        monitoring=config_module.MonitoringConfig(
            check_interval_seconds=3,
            heartbeat_timeout_seconds=4,
            schedule_check_interval_seconds=5,
        ),
        security=config_module.SecurityConfig(
            ntp_servers=["one"],
            max_time_diff_seconds=1,
            verify_time_on_transitions=False,
            browser_enforcement_enabled=False,
            safe_search_enabled=True,
            shutdown_prevention_enabled=True,
            watchdog_enabled=True,
            watchdog_count=4,
            settings_lock_until="2030-01-01T00:00:00",
        ),
        ai=config_module.AIConfig(
            provider="custom",
            model="model-x",
            base_url="https://example.com",
            api_key="secret",
        ),
        browsers=["firefox"],
    )

    config_module.save_config(cfg)
    data = json.loads(config_path.read_text())

    assert data["daemon"] == {"host": "0.0.0.0", "port": 9999, "log_level": "DEBUG"}
    assert data["monitoring"]["check_interval_seconds"] == 3
    assert data["security"]["watchdog_count"] == 4
    assert data["ai"]["model"] == "model-x"
    assert data["browsers"] == ["firefox"]


def test_get_config_caches_singleton_and_reload_reloads(monkeypatch):
    config_module._config = None
    calls = {"count": 0}

    def fake_load():
        calls["count"] += 1
        return config_module.Config(
            daemon=config_module.DaemonConfig(port=8000 + calls["count"])
        )

    monkeypatch.setattr(config_module, "load_config", fake_load)

    first = config_module.get_config()
    second = config_module.get_config()
    reloaded = config_module.reload_config()

    assert first is second
    assert first.daemon.port == 8001
    assert reloaded.daemon.port == 8002
    assert calls["count"] == 2

    config_module._config = None
