from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Callable


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

    cwd: str
    permissions: Any | None = None
    _runtime: dict[str, Any] | None = None


Validator = Callable[[Any], Any]
Runner = Callable[[Any, ToolContext], ToolResult]


@dataclass(slots=True)
class ToolDefinition:
    """Declarative description of one tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    validator: Validator
    run: Runner


class ToolRegistry:
    """O(1) tool lookup and execution wrapper with safety nets."""

    def __init__(
        self,
        tools: list[ToolDefinition],
        disposer: Callable[[], Any] | None = None,
    ) -> None:
        self._tools = list(tools)
        self._disposer = disposer
        self._tool_index: dict[str, ToolDefinition] = {tool.name: tool for tool in tools}

    def list(self) -> list[ToolDefinition]:
        return list(self._tools)

    def find(self, name: str) -> ToolDefinition | None:
        return self._tool_index.get(name)

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
