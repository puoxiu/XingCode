from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 全局配置目录：用户主目录下的 .xingcode 文件夹（存储全局生效的配置）
XINGCODE_DIR = Path.home() / ".xingcode"
# 全局配置文件路径：全局目录下的 settings.json 配置文件
XINGCODE_SETTINGS_PATH = XINGCODE_DIR / "settings.json"


def project_settings_path(cwd: str | Path | None = None) -> Path:
    """Return the project-level settings path for the given working directory."""

    # 若未传入工作目录，则使用当前工作目录；拼接项目专属配置文件路径
    return Path(cwd or Path.cwd()) / ".xingcode" / "settings.json"

#【私有工具函数】读取JSON格式的配置文件，返回空字典（若文件不存在）或解析后的字典
def _read_json_file(file_path: Path) -> dict[str, Any]:
    """Read one JSON file, returning an empty dict when the file is absent."""

    if not file_path.exists():
        return {}

    parsed = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Settings file must contain a JSON object: {file_path}")
    return parsed

#【核心函数】递归合并两个配置字典，override 配置优先级 > base 配置
# 支持嵌套字典的深度合并（而非简单覆盖），是配置优先级的核心实现
def merge_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two settings dictionaries with override precedence."""

    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_settings(current, value)
        else:
            merged[key] = value
    return merged

#【私有工具函数】加载并合并【全局配置】+【项目配置】
# 优先级：项目配置 > 全局配置（冲突时项目配置覆盖全局）
def load_effective_settings(cwd: str | Path | None = None) -> dict[str, Any]:
    """Load global and project settings, letting project settings win on conflicts."""

    global_settings = _read_json_file(XINGCODE_SETTINGS_PATH)
    project_settings = _read_json_file(project_settings_path(cwd))
    return merge_settings(global_settings, project_settings)

#【私有工具函数】从多个值中返回【第一个非空、去空格】的字符串
# 用于配置项的优先级取值（环境变量 > 配置文件）
def _first_non_empty(*values: Any) -> str:
    """Return the first non-empty string-like value after trimming whitespace."""

    for value in values:
        text = str(value).strip() if value is not None else ""
        if text:
            return text
    return ""


def _infer_provider_hint(model: str, provider_hint: str | None = None) -> str:
    """
    【私有工具函数】根据模型名称/手动指定的提供商，自动推断AI服务提供商
    支持：mock(测试)、openai、anthropic 三种类型
    Args:
        model: AI模型名称（必填）
        provider_hint: 手动指定的提供商（可选）
    Returns:
        str: 推断后的提供商名称（小写：mock/openai/anthropic）
    """
    # 处理手动指定的提供商：转为小写并去空格
    explicit = str(provider_hint or "").strip().lower()
    # 如果手动指定了合法提供商，直接返回
    if explicit in {"mock", "anthropic", "openai"}:
        return explicit

    # 无手动指定时，根据模型名称推断
    normalized = model.lower()
    # 模型为mock，返回测试提供商
    if normalized in {"mock", "mock-model"}:
        return "mock"
    # 模型以gpt-/chatgpt-/o1/o3/openai/开头，判定为OpenAI
    if normalized.startswith(("gpt-", "chatgpt-", "o1", "o3", "openai/")):
        return "openai"
    # 其余情况默认判定为Anthropic
    return "anthropic"


def _default_base_url(provider_hint: str) -> str:
    """
    【私有工具函数】根据推断的提供商，返回【默认的API基础地址】
    用于用户未配置baseUrl时的兜底值

    Args:
        provider_hint: 推断后的提供商名称
    Returns:
        str: 对应提供商的官方API地址，mock返回空字符串
    """
    if provider_hint == "openai":
        return "https://api.openai.com"
    if provider_hint == "mock":
        return ""
    # 默认返回Anthropic官方API地址
    return "https://api.anthropic.com"


def load_runtime_config(cwd: str | Path | None = None) -> dict[str, Any]:
    """
    【终极核心函数】整合所有配置源，生成【最终运行时配置】
    配置优先级：系统环境变量 > 配置文件(env) > 项目配置 > 全局配置
    功能：校验模型/API密钥、推断提供商、统一配置格式、返回稳定的运行参数

    Args:
        cwd: 工作目录，用于定位项目配置
    Returns:
        dict[str, Any]: 完整的运行时配置（模型、提供商、API地址、密钥、配置来源）
    Raises:
        RuntimeError: 未配置模型 或 非mock模式下未配置API密钥时抛出
    """
    # 1. 加载合并后的全局+项目配置
    effective = load_effective_settings(cwd)
    # 2. 提取配置文件中的env配置（兼容配置文件内的环境变量定义）
    env_from_settings = effective.get("env", {})
    # 3. 合并环境变量：配置文件env < 系统环境变量（系统变量优先级更高）
    env = {
        **(env_from_settings if isinstance(env_from_settings, dict) else {}),
        **os.environ,
    }

    # ======================== 解析核心配置项 ========================
    # 解析提供商：环境变量 > 配置文件
    provider_hint = _first_non_empty(
        env.get("XINGCODE_PROVIDER"),
        effective.get("provider"),
    ).lower() or None

    # 解析AI模型：环境变量(XINGCODE_MODEL) > 配置文件 > 环境变量(ANTHROPIC_MODEL)
    model = _first_non_empty(
        env.get("XINGCODE_MODEL"),
        effective.get("model"),
        env.get("ANTHROPIC_MODEL"),
    )
    # 强制校验：必须配置模型，否则抛出错误
    if not model:
        raise RuntimeError(
            "No model configured. Set ~/.xingcode/settings.json or XINGCODE_MODEL."
        )

    # 根据模型+手动指定，推断最终的AI提供商
    resolved_provider = _infer_provider_hint(model, provider_hint)

    # 解析API基础地址：优先级逐级降低
    base_url = _first_non_empty(
        env.get("XINGCODE_BASE_URL"),
        effective.get("baseUrl"),       # 驼峰命名兼容
        effective.get("base_url"),      # 下划线命名兼容
        env.get("OPENAI_BASE_URL") if resolved_provider == "openai" else "",
        env.get("ANTHROPIC_BASE_URL") if resolved_provider == "anthropic" else "",
        _default_base_url(resolved_provider),  # 兜底默认地址
    )

    # 解析API密钥：优先级逐级降低（兼容多提供商密钥）
    api_key = _first_non_empty(
        env.get("XINGCODE_API_KEY"),
        effective.get("apiKey"),        # 驼峰命名兼容
        effective.get("api_key"),       # 下划线命名兼容
        env.get("OPENAI_API_KEY") if resolved_provider == "openai" else "",
        env.get("ANTHROPIC_API_KEY") if resolved_provider == "anthropic" else "",
    )

    # ======================== 安全校验 ========================
    # 设计：mock测试模式不需要API密钥，真实模式必须配置密钥
    if resolved_provider != "mock" and not api_key:
        raise RuntimeError(
            "No API key configured. Set ~/.xingcode/settings.json or XINGCODE_API_KEY."
        )

    # 返回标准化的运行时配置字典（统一键名，方便后续使用）
    return {
        "model": model,                # 最终使用的AI模型
        "provider": resolved_provider, # 最终推断的AI提供商
        "baseUrl": base_url,           # API请求基础地址
        "apiKey": api_key or None,     # API密钥（mock为None）
        "sourceSummary": (             # 配置来源说明（调试用）
            f"settings: {XINGCODE_SETTINGS_PATH} + {project_settings_path(cwd)} > process.env"
        ),
    }

def save_settings(
    updates: dict[str, Any],
    cwd: str | Path | None = None,
    *,
    project: bool = False,
) -> None:
    """
    【核心函数】持久化保存配置更新到文件
    支持保存到【全局配置】或【项目配置】，自动合并原有配置（不覆盖）
    Args:
        updates: 要更新的配置字典（键值对）
        cwd: 工作目录（仅保存项目配置时需要）
        project: 关键字参数，True=保存到项目配置，False=保存到全局配置
    """
    # 确定保存目标：项目配置 / 全局配置
    target = project_settings_path(cwd) if project else XINGCODE_SETTINGS_PATH
    # 自动创建配置文件的父目录（递归创建，已存在则不报错）
    target.parent.mkdir(parents=True, exist_ok=True)
    # 读取目标文件的原有配置
    existing = _read_json_file(target)
    # 合并原有配置 + 新配置（新配置优先级更高）
    next_settings = merge_settings(existing, updates)
    # 将配置写入文件：格式化JSON（缩进2格），UTF-8编码，末尾加换行
    target.write_text(json.dumps(next_settings, indent=2) + "\n", encoding="utf-8")