from __future__ import annotations

import sys

from XingCode.storage import load_effective_settings, save_settings


def _read_input(prompt: str, default: str | None = None) -> str:
    """读取一项用户输入，并在需要时显示默认值。"""

    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
        return value or (default or "")
    except (EOFError, KeyboardInterrupt):
        print("\n\n安装已取消。")
        raise SystemExit(0) from None


def _require_input(prompt: str, default: str | None = None) -> str:
    """读取必填项；如果为空则持续提示。"""

    while True:
        value = _read_input(prompt, default)
        if value:
            return value
        print("该项不能为空，请重新输入。")


def _mask_secret(secret: str | None) -> str:
    """把已保存的密钥显示成简短状态，而不是明文。"""

    if not secret:
        return "[未设置]"
    return "[已保存]"


def _infer_provider(model: str) -> str:
    """根据模型名推断 provider，保持和配置层的最小规则一致。"""

    normalized = model.lower().strip()
    if normalized in {"mock", "mock-model"}:
        return "mock"
    if normalized.startswith(("gpt-", "chatgpt-", "o1", "o3", "openai/")):
        return "openai"
    return "anthropic"


def _default_base_url(provider: str) -> str:
    """为当前 provider 给出最小默认 base URL。"""

    if provider == "openai":
        return "https://api.openai.com"
    if provider == "mock":
        return ""
    return "https://api.anthropic.com"


def main() -> None:
    """运行最小安装向导：写入 model、provider、baseUrl、apiKey。"""

    print("=" * 50)
    print("  XingCode 安装向导")
    print("=" * 50)
    print()

    try:
        settings = load_effective_settings()
    except Exception:  # noqa: BLE001
        settings = {}

    print(f"当前配置：{settings}")

    current_model = str(settings.get("model", "")).strip() or "mock"
    model = _require_input("Model name", current_model)
    provider = _infer_provider(model)

    # mock 模式不需要真实 API，因此 baseUrl 和 apiKey 都允许为空。
    base_url_default = str(settings.get("baseUrl", "")).strip() or _default_base_url(provider)
    base_url = _read_input("Base URL", base_url_default) if provider != "mock" else ""

    saved_api_key = str(settings.get("apiKey", "")).strip()
    api_key_input = _read_input(f"API Key {_mask_secret(saved_api_key)}", None)
    api_key = api_key_input or saved_api_key
    if provider != "mock" and not api_key:
        print("\n真实 provider 需要 API Key，安装未保存。", file=sys.stderr)
        raise SystemExit(1)

    save_settings(
        {
            "model": model,
            "provider": provider,
            "baseUrl": base_url,
            "apiKey": api_key if provider != "mock" else None,
        }
    )

    print()
    print("配置已保存。")
    print(f"  model: {model}")
    print(f"  provider: {provider}")
    print(f"  baseUrl: {base_url or '(mock mode)'}")
    print()
    print("现在可以运行：")
    print("  python -m XingCode.app.main")
    print("  python -m XingCode.app.headless \"你的问题\"")



if __name__ == "__main__":
    main()