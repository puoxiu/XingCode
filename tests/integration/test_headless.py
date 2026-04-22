from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from XingCode.app.headless import run_headless
from XingCode.storage import config as config_module


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
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("XINGCODE_MODEL", "mock")

    response = run_headless("hello", cwd=str(tmp_path))

    assert "XingCode mock model" in response


def test_run_headless_reads_prompt_from_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """没有显式 prompt 时，headless 应该从 stdin 读取输入。"""

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_module, "XINGCODE_SETTINGS_PATH", tmp_path / "home-settings.json")
    _clear_runtime_env(monkeypatch)
    monkeypatch.setenv("XINGCODE_MODEL", "mock")
    monkeypatch.setattr(sys, "stdin", FakePipe("hello from stdin"))

    response = run_headless(None, cwd=str(tmp_path))

    assert "XingCode mock model" in response
