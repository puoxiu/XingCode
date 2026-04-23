from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from XingCode.app.headless import run_headless
from XingCode.storage import config as config_module
from XingCode.storage import history as history_module
from XingCode.storage import session as session_module


class FakePipe(io.StringIO):
    """最小假 stdin：用于模拟管道输入。"""

    def isatty(self) -> bool:
        """告诉 headless 当前输入不是交互式终端。"""

        return False


def _clear_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """清理可能影响配置推断的环境变量，保证测试隔离。"""

    for name in [
        "XINGCODE_MODEL",
        "XINGCODE_PROVIDER",
        "XINGCODE_BASE_URL",
        "XINGCODE_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_run_headless_returns_mock_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """headless 在 mock 配置下应能完整跑通一轮 agent。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", tmp_path / "home-settings.json")
    monkeypatch.setattr(history_module, "XINGCODE_HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_module, "SESSIONS_INDEX_PATH", tmp_path / "sessions-index.json")
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("XINGCODE_MODEL", "mock")

    response = run_headless("hello", cwd=str(tmp_path))

    assert "XingCode mock model" in response


def test_run_headless_reads_prompt_from_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有显式 prompt 时，headless 应该从 stdin 读取输入。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", tmp_path / "home-settings.json")
    monkeypatch.setattr(history_module, "XINGCODE_HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_module, "SESSIONS_INDEX_PATH", tmp_path / "sessions-index.json")
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("XINGCODE_MODEL", "mock")
    monkeypatch.setattr(sys, "stdin", FakePipe("hello from stdin"))

    response = run_headless(None, cwd=str(tmp_path))

    assert "XingCode mock model" in response


def test_run_headless_handles_help_without_runtime_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本地 `/help` 命令不应该依赖 runtime 配置。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", tmp_path / "home-settings.json")
    monkeypatch.setattr(history_module, "XINGCODE_HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_module, "SESSIONS_INDEX_PATH", tmp_path / "sessions-index.json")
    _clear_runtime_env(monkeypatch)

    response = run_headless("/help", cwd=str(tmp_path))

    assert "/help" in response
    assert "/cmd [cwd::]<command>" in response


def test_run_headless_executes_read_shortcut_without_runtime_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """本地 `/read` 快捷命令也应该在无模型配置时可用。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", tmp_path / "home-settings.json")
    monkeypatch.setattr(history_module, "XINGCODE_HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_module, "SESSIONS_INDEX_PATH", tmp_path / "sessions-index.json")
    _clear_runtime_env(monkeypatch)
    (tmp_path / "README.md").write_text("hello headless shortcut", encoding="utf-8")

    response = run_headless("/read README.md", cwd=str(tmp_path))

    assert "FILE: README.md" in response
    assert "hello headless shortcut" in response


def test_run_headless_can_save_and_resume_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """headless 绑定 session 时，应能落盘并在后续继续使用同一会话。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", tmp_path / "home-settings.json")
    monkeypatch.setattr(history_module, "XINGCODE_HISTORY_PATH", tmp_path / "history.json")
    monkeypatch.setattr(session_module, "SESSIONS_DIR", tmp_path / "sessions")
    monkeypatch.setattr(session_module, "SESSIONS_INDEX_PATH", tmp_path / "sessions-index.json")
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("XINGCODE_MODEL", "mock")

    session = session_module.create_new_session(workspace=str(tmp_path))

    first_response = run_headless("hello", cwd=str(tmp_path), session=session)
    saved_once = session_module.load_session(session.session_id)

    assert "XingCode mock model" in first_response
    assert saved_once is not None
    assert any(message.get("role") == "user" and message.get("content") == "hello" for message in saved_once.messages)

    second_response = run_headless("hello again", cwd=str(tmp_path), session=saved_once)
    saved_twice = session_module.load_session(session.session_id)
    delta_dir = tmp_path / "sessions" / session_module.DELTA_DIR_NAME / session.session_id

    assert "XingCode mock model" in second_response
    assert saved_twice is not None
    assert len(saved_twice.messages) >= len(saved_once.messages)
    assert any(message.get("content") == "hello again" for message in saved_twice.messages)
    assert delta_dir.exists()
