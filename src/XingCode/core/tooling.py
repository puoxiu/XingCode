from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Callable

# 数据类：后台任务结果（仅占位，未来扩展异步/后台任务用）
@dataclass(slots=True)
class BackgroundTaskResult:
    """Placeholder for future background task support."""

    taskId: str
    type: str
    command: str
    pid: int
    status: str
    startedAt: int


@dataclass(slots=True)
class ToolResult:
    """Normalized result returned by every tool."""

    ok: bool
    output: str
    backgroundTask: BackgroundTaskResult | None = None
    awaitUser: bool = False


@dataclass(slots=True)
class ToolContext:
    """Shared runtime context passed into tools."""

    cwd: str            # Current Working Directory
    permissions: Any | None = None
    _runtime: dict[str, Any] | None = None

# 类型别名：输入验证函数
# 作用：接收原始输入 → 校验/解析 → 返回合法数据，失败抛异常
Validator = Callable[[Any], Any]
# 类型别名：工具执行函数
# 作用：接收合法输入 + 上下文 → 执行逻辑 → 返回标准化 ToolResult
Runner = Callable[[Any, ToolContext], ToolResult]

# 声明式工具定义，描述一个工具的完整信息：名称、功能、输入格式、校验、执行逻辑
@dataclass(slots=True)
class ToolDefinition:
    """Declarative description of one tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    validator: Validator
    run: Runner

# 核心类：工具注册表（统一管理、查找、安全执行所有工具）
# 作用：提供工具列表、查找工具、执行工具、资源释放
class ToolRegistry:
    """O(1) tool lookup and execution wrapper with safety nets."""

    def __init__(
        self,
        tools: list[ToolDefinition],
        skills: list[dict[str, Any]] | None = None,
        mcp_servers: list[dict[str, Any]] | None = None,
        disposer: Callable[[], Any] | None = None,
    ) -> None:
        # 统一复制一份 metadata，避免调用方拿到内部可变对象后直接改坏注册表状态。
        self._tools = list(tools)
        self._skills = [dict(skill) for skill in (skills or [])]
        self._mcp_servers = [dict(server) for server in (mcp_servers or [])]
        self._disposer = disposer
        self._tool_index: dict[str, ToolDefinition] = {tool.name: tool for tool in tools}

    def list(self) -> list[ToolDefinition]:
        return list(self._tools)

    def find(self, name: str) -> ToolDefinition | None:
        return self._tool_index.get(name)

    def get_skills(self) -> list[dict[str, Any]]:
        """返回当前注册表携带的 skills 摘要副本。"""

        return [dict(skill) for skill in self._skills]

    def get_mcp_servers(self) -> list[dict[str, Any]]:
        """返回当前注册表携带的 MCP server 摘要副本。"""

        return [dict(server) for server in self._mcp_servers]

    def build_prompt_extras(self) -> dict[str, Any]:
        """把 registry metadata 转成 prompt builder 可直接消费的 extras。"""

        extras: dict[str, Any] = {}
        if self._skills:
            extras["skills"] = self.get_skills()
        if self._mcp_servers:
            extras["mcpServers"] = self.get_mcp_servers()
        return extras

    def execute(self, tool_name: str, input_data: Any, context: ToolContext) -> ToolResult:
        tool = self.find(tool_name)
        if tool is None:
            return ToolResult(ok=False, output=f"Unknown tool: {tool_name}")

        try:
            parsed_input = tool.validator(input_data)
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                output=f"Input validation error in {tool_name}: {exc}\nInput was: {str(input_data)[:200]}",
            )

        try:
            result = tool.run(parsed_input, context)
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            excerpt = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)[-3:]
            ).strip()
            return ToolResult(
                ok=False,
                output=f"Tool execution error in {tool_name}: {exc}\nTraceback:\n{excerpt}",
            )

        if not isinstance(result, ToolResult):
            return ToolResult(
                ok=False,
                output=(
                    f"Tool {tool_name} returned invalid result type: "
                    f"{type(result).__name__}. Expected ToolResult."
                ),
            )

        return result

    def dispose(self) -> None:
        if self._disposer is not None:
            self._disposer()
