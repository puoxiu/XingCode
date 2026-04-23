from __future__ import annotations

import json
from pathlib import Path

import pytest

from XingCode.storage import config as config_module


def _write_json(path: Path, payload: dict) -> None:
    """Write one JSON file used by config tests."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def test_merge_settings_recursively_merges_nested_dicts() -> None:
    """Nested dict settings should merge instead of being overwritten wholesale."""

    merged = config_module.merge_settings(
        {"env": {"A": "1"}, "extra": {"left": True}},
        {"env": {"B": "2"}, "extra": {"right": True}},
    )

    assert merged["env"] == {"A": "1", "B": "2"}
    assert merged["extra"] == {"left": True, "right": True}


def test_load_effective_settings_merges_global_and_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Project settings should override global settings in the effective result."""

    global_settings = tmp_path / "home-settings.json"
    project_root = tmp_path / "workspace"
    project_settings = project_root / ".xingcode" / "settings.json"
    _write_json(global_settings, {"model": "claude-3-5-sonnet", "apiKey": "global-key"})
    _write_json(project_settings, {"model": "gpt-4o"})

    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", global_settings)

    effective = config_module.load_effective_settings(project_root)

    assert effective["model"] == "gpt-4o"
    assert effective["apiKey"] == "global-key"


def test_load_runtime_config_reads_minimal_runtime_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runtime config should normalize model, provider, baseUrl, and apiKey."""

    global_settings = tmp_path / "home-settings.json"
    _write_json(global_settings, {"model": "gpt-4o", "apiKey": "file-key"})
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", global_settings)

    runtime = config_module.load_runtime_config(tmp_path / "workspace")

    assert runtime["model"] == "gpt-4o"
    assert runtime["provider"] == "openai"
    assert runtime["baseUrl"] == "https://api.openai.com"
    assert runtime["apiKey"] == "file-key"


def test_load_runtime_config_prefers_environment_over_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Environment variables should override file settings when both are present."""

    global_settings = tmp_path / "home-settings.json"
    _write_json(global_settings, {"model": "claude-sonnet", "apiKey": "file-key"})
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", global_settings)
    monkeypatch.setenv("XINGCODE_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("XINGCODE_API_KEY", "env-key")
    monkeypatch.setenv("XINGCODE_BASE_URL", "https://example.test/openai")

    runtime = config_module.load_runtime_config(tmp_path / "workspace")

    assert runtime["model"] == "gpt-4o-mini"
    assert runtime["apiKey"] == "env-key"
    assert runtime["baseUrl"] == "https://example.test/openai"
    assert runtime["provider"] == "openai"


def test_load_runtime_config_allows_mock_without_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock mode should not require a real API key."""

    global_settings = tmp_path / "home-settings.json"
    _write_json(global_settings, {"model": "mock"})
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", global_settings)

    runtime = config_module.load_runtime_config(tmp_path / "workspace")

    assert runtime["model"] == "mock"
    assert runtime["provider"] == "mock"
    assert runtime["apiKey"] is None


def test_load_runtime_config_raises_when_model_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing model configuration should fail fast with a readable error."""

    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", tmp_path / "missing.json")

    with pytest.raises(RuntimeError, match="No model configured"):
        config_module.load_runtime_config(tmp_path / "workspace")


def test_load_runtime_config_raises_when_api_key_is_missing_for_real_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real providers should still require one API key in this phase."""

    global_settings = tmp_path / "home-settings.json"
    _write_json(global_settings, {"model": "claude-sonnet-4"})
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", global_settings)

    with pytest.raises(RuntimeError, match="No API key configured"):
        config_module.load_runtime_config(tmp_path / "workspace")


def test_save_settings_creates_and_merges_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Saving settings should preserve previous keys while applying updates."""

    global_settings = tmp_path / "home-settings.json"
    _write_json(global_settings, {"model": "claude-sonnet", "env": {"A": "1"}})
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", global_settings)

    config_module.save_settings({"apiKey": "saved-key", "env": {"B": "2"}})
    saved = json.loads(global_settings.read_text(encoding="utf-8"))

    assert saved["model"] == "claude-sonnet"
    assert saved["apiKey"] == "saved-key"
    assert saved["env"] == {"A": "1", "B": "2"}


def test_load_runtime_config_includes_mcp_servers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """runtime 配置应把静态 mcpServers 规范化后带出来。"""

    global_settings = tmp_path / "home-settings.json"
    _write_json(
        global_settings,
        {
            "model": "mock",
            "mcpServers": {
                "fake": {
                    "command": "python3",
                    "args": ["server.py"],
                    "protocol": "newline-json",
                }
            },
        },
    )
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", global_settings)

    runtime = config_module.load_runtime_config(tmp_path / "workspace")

    assert runtime["mcpServers"] == {
        "fake": {
            "command": "python3",
            "args": ["server.py"],
            "env": {},
            "protocol": "newline-json",
            "enabled": True,
            "cwd": None,
        }
    }
