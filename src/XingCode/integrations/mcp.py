from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from XingCode.core.tooling import ToolDefinition, ToolResult

# 安全常量：MCP 参数里不允许出现常见 shell 元字符，避免把 stdio server
# 退化成“拼接字符串跑 shell”这种高风险路径。
DANGEROUS_SHELL_CHARS = set('|&;`$(){}<>\n\r')

# payload 上限：避免异常服务端返回超大包导致内存被撑爆。
MAX_MCP_PAYLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

# 允许的 MCP 命令白名单：先对齐参考项目的常见启动命令。
ALLOWED_COMMANDS = {
    "node",
    "npm",
    "npx",
    "python",
    "python3",
    "pip",
    "pip3",
    "uv",
    "deno",
    "bun",
    "cargo",
    "go",
    "java",
    "javac",
    "ruby",
    "gem",
    "dotnet",
    "curl",
    "wget",
}

JsonRpcProtocol = str


@dataclass(slots=True)
class McpServerSummary:
    """MCP server 的轻量摘要，用于 prompt/session/UI 展示。"""

    name: str
    command: str
    status: str
    toolCount: int
    error: str | None = None
    protocol: str | None = None
    resourceCount: int | None = None
    promptCount: int | None = None


def _sanitize_tool_segment(value: str) -> str:
    """把 server/tool 名称转换成安全稳定的工具名片段。"""

    normalized = "".join(char.lower() if char.isalnum() or char in {"_", "-"} else "_" for char in value)
    normalized = normalized.strip("_")
    return normalized or "tool"


def _validate_mcp_command(command: str) -> None:
    """校验 MCP server 启动命令是否合法。"""

    normalized = Path(command).resolve().as_posix()
    if ".." in normalized or "~" in normalized:
        raise RuntimeError("Invalid MCP command: contains path traversal characters")

    base_command = Path(command).name.lower()
    if base_command.endswith(".exe"):
        base_command = base_command[:-4]

    if Path(command).is_absolute():
        home_posix = str(Path.home().as_posix())
        allowed_system_dirs = [
            "/usr/bin",
            "/usr/local/bin",
            "/usr/local/sbin",
            "/usr/sbin",
            "/opt",
            "/opt/homebrew/bin",
            "/opt/homebrew/sbin",
            "/usr/local/Cellar",
            "/snap/bin",
            "/home/linuxbrew/.linuxbrew/bin",
            f"{home_posix}/.local/bin",
            f"{home_posix}/.cargo/bin",
            f"{home_posix}/.nvm",
        ]
        if os.name == "nt":
            allowed_system_dirs.extend(
                [
                    "C:\\Program Files",
                    "C:\\Program Files (x86)",
                    "C:\\Windows\\System32",
                ]
            )

        is_in_allowed_dir = any(normalized.lower().startswith(item.lower()) for item in allowed_system_dirs)
        if not is_in_allowed_dir and base_command not in ALLOWED_COMMANDS:
            raise RuntimeError(
                f'MCP command "{command}" is not in the allowed list. '
                "Use a whitelisted command or place the executable in a standard system directory."
            )

        dangerous_shells = ["cmd.exe", "command.com", "powershell.exe", "pwsh.exe"]
        if any(normalized.lower().endswith(item) for item in dangerous_shells):
            raise RuntimeError(
                f'MCP command "{command}" is a dangerous system shell. '
                "Direct execution of shells is not allowed for security reasons."
            )
        return

    if base_command not in ALLOWED_COMMANDS:
        raise RuntimeError(
            f'MCP command "{command}" is not in the allowed list. '
            f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}. "
            "Use absolute paths for custom commands."
        )


def _validate_mcp_args(args: list[str]) -> None:
    """校验 MCP 启动参数不包含危险 shell 字符。"""

    for arg in args:
        for char in arg:
            if char in DANGEROUS_SHELL_CHARS:
                raise RuntimeError(
                    f"Invalid MCP argument: contains dangerous shell character '{char}'. "
                    "MCP server arguments cannot contain shell metacharacters for security reasons."
                )


def _normalize_input_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """MCP tool 没提供 schema 时，回退到最宽松 object schema。"""

    if not isinstance(schema, dict):
        return {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }

    normalized = dict(schema)
    if normalized.get("type") == "object":
        # OpenAI-compatible tools 对 object schema 更严格：即使允许任意字段，
        # 也要求 parameters 里带一个 properties 对象。
        properties = normalized.get("properties")
        normalized["properties"] = properties if isinstance(properties, dict) else {}
        normalized.setdefault("additionalProperties", True)
    return normalized


def _format_content_block(block: Any) -> str:
    """把 MCP content block 格式化成人类可读文本。"""

    if not isinstance(block, dict):
        return json.dumps(block, indent=2, ensure_ascii=False)
    if block.get("type") == "text" and "text" in block:
        return str(block["text"])
    return json.dumps(block, indent=2, ensure_ascii=False)


def _format_tool_call_result(result: Any) -> ToolResult:
    """把 MCP tools/call 的结果统一转成 ToolResult。"""

    if not isinstance(result, dict):
        return ToolResult(ok=True, output=json.dumps(result, indent=2, ensure_ascii=False))

    parts: list[str] = []
    content = result.get("content")
    if isinstance(content, list) and content:
        parts.append("\n\n".join(_format_content_block(block) for block in content))
    if "structuredContent" in result:
        parts.append("STRUCTURED_CONTENT:\n" + json.dumps(result["structuredContent"], indent=2, ensure_ascii=False))
    if not parts:
        parts.append(json.dumps(result, indent=2, ensure_ascii=False))
    return ToolResult(ok=not bool(result.get("isError")), output="\n\n".join(parts).strip())


def _format_read_resource_result(result: Any) -> ToolResult:
    """把 MCP resources/read 的返回渲染成可读文本。"""

    if not isinstance(result, dict):
        return ToolResult(ok=False, output=json.dumps(result, indent=2, ensure_ascii=False))

    contents = result.get("contents", [])
    if not contents:
        return ToolResult(ok=True, output="No resource contents returned.")

    rendered: list[str] = []
    for item in contents:
        header_lines = [f"URI: {item.get('uri', '(unknown)')}"]
        if item.get("mimeType"):
            header_lines.append(f"MIME: {item['mimeType']}")
        header = "\n".join(header_lines) + "\n\n"
        if isinstance(item.get("text"), str):
            rendered.append(header + item["text"])
        elif isinstance(item.get("blob"), str):
            rendered.append(header + "BLOB:\n" + item["blob"])
        else:
            rendered.append(header + json.dumps(item, indent=2, ensure_ascii=False))
    return ToolResult(ok=True, output="\n\n".join(rendered))


def _format_prompt_result(result: Any) -> ToolResult:
    """把 MCP prompts/get 的返回渲染成统一文本。"""

    if not isinstance(result, dict):
        return ToolResult(ok=False, output=json.dumps(result, indent=2, ensure_ascii=False))

    header = f"DESCRIPTION: {result['description']}\n\n" if result.get("description") else ""
    body_parts: list[str] = []
    for message in result.get("messages", []):
        role = message.get("role", "unknown")
        content = message.get("content")
        if isinstance(content, str):
            rendered = content
        elif isinstance(content, list):
            rendered = "\n".join(
                str(part["text"]) if isinstance(part, dict) and "text" in part else json.dumps(part, indent=2, ensure_ascii=False)
                for part in content
            )
        else:
            rendered = json.dumps(content, indent=2, ensure_ascii=False)
        body_parts.append(f"[{role}]\n{rendered}")

    output = (header + "\n\n".join(body_parts)).strip()
    return ToolResult(ok=True, output=output or json.dumps(result, indent=2, ensure_ascii=False))


class StdioMcpClient:
    """基于 stdio 的 MCP client。

    这版保持和参考项目一致的设计：
    - 启动一个子进程作为 MCP server
    - 通过 JSON-RPC over stdio 通信
    - 支持 `newline-json` 和 `content-length` 两种协议
    - 首次请求时再真正启动，尽量减少无用开销
    """

    def __init__(self, server_name: str, config: dict[str, Any], cwd: str) -> None:
        self.server_name = server_name
        self.config = config
        self.cwd = cwd
        self.process: subprocess.Popen[bytes] | None = None
        self.protocol: JsonRpcProtocol | None = None
        self.next_id = 1
        self._pending: dict[int, Queue[Any]] = {}
        self._lock = threading.Lock()
        self.stderr_lines: list[str] = []
        self._stderr_thread: threading.Thread | None = None
        self._stdout_thread: threading.Thread | None = None
        self._started = False
        self._start_error: str | None = None
        self._tools_cache: list[dict[str, Any]] | None = None
        self._resources_cache: list[dict[str, Any]] | None = None
        self._prompts_cache: list[dict[str, Any]] | None = None

    @property
    def is_started(self) -> bool:
        """当前 server 是否已经成功启动。"""

        return self._started

    @property
    def start_error(self) -> str | None:
        """最近一次启动错误，用于 server 摘要展示。"""

        return self._start_error

    def _protocol_candidates(self) -> list[JsonRpcProtocol]:
        """根据配置决定尝试哪些协议。"""

        configured = self.config.get("protocol")
        if configured == "content-length":
            return ["content-length"]
        if configured == "newline-json":
            return ["newline-json"]
        return ["content-length", "newline-json"]

    def start(self) -> None:
        """启动 MCP server，并完成 initialize 握手。"""

        if self._started:
            return

        if self._start_error is not None and self.process is None:
            self._start_error = None

        last_error: Exception | None = None
        for protocol in self._protocol_candidates():
            try:
                self._spawn_process()
                self.protocol = protocol
                self.request(
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "xingcode", "version": "0.1.0"},
                    },
                    timeout_seconds=2.0,
                )
                self.notify("notifications/initialized", {})
                self._started = True
                self._start_error = None
                return
            except Exception as error:  # noqa: BLE001
                last_error = error
                self.close()

        self._start_error = str(last_error or f'Failed to connect MCP server "{self.server_name}".')
        raise RuntimeError(self._start_error)

    def _ensure_started(self) -> None:
        """保证请求前 server 已经启动。"""

        if not self._started:
            self.start()

    def _spawn_process(self) -> None:
        """按照配置启动 MCP server 子进程。"""

        command = str(self.config.get("command", "")).strip()
        if not command:
            raise RuntimeError(f'MCP server "{self.server_name}" has no command configured.')

        _validate_mcp_command(command)
        _validate_mcp_args(list(self.config.get("args", []) or []))

        process_cwd = Path(self.cwd)
        if self.config.get("cwd"):
            process_cwd = (process_cwd / str(self.config["cwd"])).resolve()

        env = os.environ.copy()
        for key, value in dict(self.config.get("env", {}) or {}).items():
            env[str(key)] = str(value)

        popen_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = 0x08000000

        try:
            self.process = subprocess.Popen(  # noqa: S603
                [command, *list(self.config.get("args", []) or [])],
                cwd=str(process_cwd),
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                **popen_kwargs,
            )
        except FileNotFoundError:
            raise RuntimeError(f"Command not found: {command}. Install it first and ensure it is available in PATH.") from None

        self.stderr_lines = []
        with self._lock:
            self._pending = {}
        self._stderr_thread = threading.Thread(target=self._consume_stderr, daemon=True)
        self._stderr_thread.start()

    def _consume_stderr(self) -> None:
        """后台收集 server stderr，超时或错误时拼到提示里。"""

        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            try:
                text = line.decode("utf-8", errors="replace").strip()
                if text:
                    self.stderr_lines.append(text)
                    self.stderr_lines = self.stderr_lines[-8:]
            except Exception:
                continue

    def _ensure_stdout_thread(self) -> None:
        """确保 stdout 解析线程只启动一次。"""

        if self._stdout_thread is not None:
            return
        self._stdout_thread = threading.Thread(target=self._consume_stdout, daemon=True)
        self._stdout_thread.start()

    def _consume_stdout(self) -> None:
        """后台解析 server stdout 中的 JSON-RPC 消息。"""

        assert self.process is not None and self.process.stdout is not None
        try:
            while True:
                line_bytes = self.process.stdout.readline()
                if not line_bytes:
                    break

                try:
                    line = line_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    continue

                stripped = line.strip()
                if not stripped:
                    continue

                if self.protocol is None:
                    if line.lower().startswith("content-length:"):
                        self.protocol = "content-length"
                    else:
                        self.protocol = "newline-json"

                if self.protocol == "newline-json":
                    try:
                        self._handle_message(json.loads(stripped))
                    except json.JSONDecodeError:
                        continue
                    continue

                header_lines = [line.rstrip("\r\n")]
                while True:
                    next_line_bytes = self.process.stdout.readline()
                    if not next_line_bytes:
                        return
                    try:
                        next_line = next_line_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        return
                    header_line = next_line.rstrip("\r\n")
                    if header_line == "":
                        break
                    header_lines.append(header_line)

                content_length = 0
                for header in header_lines:
                    if header.lower().startswith("content-length:"):
                        try:
                            content_length = int(header.split(":", 1)[1].strip())
                        except ValueError:
                            pass
                        break

                if content_length > MAX_MCP_PAYLOAD_BYTES:
                    self.stderr_lines.append(
                        f"MCP payload too large: {content_length} bytes (limit {MAX_MCP_PAYLOAD_BYTES})"
                    )
                    continue

                if content_length <= 0:
                    continue

                body_bytes = self.process.stdout.read(content_length)
                if len(body_bytes) < content_length:
                    return
                try:
                    self._handle_message(json.loads(body_bytes.decode("utf-8")))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
        finally:
            if self.process:
                exit_code = self.process.poll()
                error_msg = {"error": {"code": -1, "message": f"MCP server process exited (code={exit_code})"}}
                with self._lock:
                    for _, queue in list(self._pending.items()):
                        queue.put(error_msg)
                    self._pending.clear()

    def _handle_message(self, message: dict[str, Any]) -> None:
        """把响应分发给对应 request 的等待队列。"""

        message_id = message.get("id")
        if not isinstance(message_id, int):
            return

        with self._lock:
            queue = self._pending.pop(message_id, None)
            if queue is not None:
                queue.put(message)

    def send(self, message: dict[str, Any]) -> None:
        """向 MCP server 发送一条 JSON-RPC 消息。"""

        if self.process is None or self.process.stdin is None:
            raise RuntimeError(f'MCP server "{self.server_name}" is not running.')

        payload_bytes = json.dumps(message, ensure_ascii=False).encode("utf-8")
        if self.protocol == "newline-json":
            self.process.stdin.write(payload_bytes + b"\n")
            self.process.stdin.flush()
            self._ensure_stdout_thread()
            return

        header = f"Content-Length: {len(payload_bytes)}\r\n\r\n".encode("utf-8")
        self.process.stdin.write(header + payload_bytes)
        self.process.stdin.flush()
        self._ensure_stdout_thread()

    def notify(self, method: str, params: Any) -> None:
        """发送 notification，不等待返回。"""

        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: Any, timeout_seconds: float = 5.0) -> Any:
        """发送 request，并等待 result/error。"""

        message_id = self.next_id
        self.next_id += 1
        response_queue: Queue[Any] = Queue(maxsize=1)
        with self._lock:
            self._pending[message_id] = response_queue

        self.send({"jsonrpc": "2.0", "id": message_id, "method": method, "params": params})

        try:
            message = response_queue.get(timeout=timeout_seconds)
        except Empty as error:
            with self._lock:
                self._pending.pop(message_id, None)
            stderr = "\n".join(self.stderr_lines)
            raise RuntimeError(
                f"MCP {self.server_name}: request timed out for {method}" + (f"\n{stderr}" if stderr else "")
            ) from error

        if message.get("error"):
            details = message["error"].get("data")
            suffix = f"\n{json.dumps(details, indent=2, ensure_ascii=False)}" if details else ""
            raise RuntimeError(f"MCP {self.server_name}: {message['error']['message']}{suffix}")

        return message.get("result")

    def list_tools(self) -> list[dict[str, Any]]:
        """获取 tool 列表，并做一次缓存。"""

        if self._tools_cache is not None:
            return self._tools_cache
        self._ensure_started()
        result = self.request("tools/list", {})
        self._tools_cache = list(result.get("tools", []) if isinstance(result, dict) else [])
        return self._tools_cache

    def list_resources(self) -> list[dict[str, Any]]:
        """获取 resource 列表，并做一次缓存。"""

        if self._resources_cache is not None:
            return self._resources_cache
        self._ensure_started()
        result = self.request("resources/list", {}, timeout_seconds=3.0)
        self._resources_cache = list(result.get("resources", []) if isinstance(result, dict) else [])
        return self._resources_cache

    def read_resource(self, uri: str) -> ToolResult:
        """读取一个具体 resource。"""

        self._ensure_started()
        return _format_read_resource_result(self.request("resources/read", {"uri": uri}, timeout_seconds=5.0))

    def list_prompts(self) -> list[dict[str, Any]]:
        """获取 prompt 列表，并做一次缓存。"""

        if self._prompts_cache is not None:
            return self._prompts_cache
        self._ensure_started()
        result = self.request("prompts/list", {}, timeout_seconds=3.0)
        self._prompts_cache = list(result.get("prompts", []) if isinstance(result, dict) else [])
        return self._prompts_cache

    def get_prompt(self, name: str, args: dict[str, str] | None = None) -> ToolResult:
        """读取一个渲染后的 prompt。"""

        self._ensure_started()
        return _format_prompt_result(
            self.request("prompts/get", {"name": name, "arguments": args or {}}, timeout_seconds=5.0)
        )

    def call_tool(self, name: str, input_data: Any) -> ToolResult:
        """执行一个 MCP tool。"""

        self._ensure_started()
        return _format_tool_call_result(self.request("tools/call", {"name": name, "arguments": input_data or {}}))

    def close(self) -> None:
        """关闭 client 和底层 server 进程，并通知所有等待中的请求。"""

        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
            for queue in pending:
                queue.put({"error": {"message": f'MCP server "{self.server_name}" closed before completing the request.'}})

        if self.process is not None:
            try:
                if os.name == "nt":
                    try:
                        subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.process.pid)], capture_output=True, timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            self.process.kill()
                        except OSError:
                            pass
                    except Exception:
                        try:
                            self.process.kill()
                        except OSError:
                            pass
                else:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        try:
                            self.process.kill()
                        except OSError:
                            pass

                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass
            finally:
                self.process = None

        self.protocol = None
        self._stdout_thread = None
        self._stderr_thread = None
        self._started = False
        self._start_error = None
        self._tools_cache = None
        self._resources_cache = None
        self._prompts_cache = None


def create_mcp_backed_tools(*, cwd: str, mcp_servers: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """根据静态 MCP server 配置，创建动态工具与 server 摘要。把配置文件里的 MCP 服务器，自动变成 AI 可以调用的工具。

    返回结构：
    - `tools`: 注册进 ToolRegistry 的 ToolDefinition 列表
    - `servers`: prompt/session/UI 可见的 server 摘要
    - `dispose`: 关闭所有 client 的回调
    """

    clients: list[StdioMcpClient] = []
    tools: list[ToolDefinition] = []    # mcp tools列表
    servers: list[dict[str, Any]] = []    # 对应mcp服务器的摘要信息
    resource_index: dict[str, dict[str, Any]] = {}
    prompt_index: dict[str, dict[str, Any]] = {}

    for server_name, config in mcp_servers.items():
        if config.get("enabled") is False:
            servers.append(
                asdict(
                    McpServerSummary(
                        name=server_name,
                        command=str(config.get("command", "")),
                        status="disabled",
                        toolCount=0,
                        protocol=str(config.get("protocol", "")) or None,
                    )
                )
            )
            continue

        client = StdioMcpClient(server_name, config, cwd)
        clients.append(client)
        servers.append(
            asdict(
                McpServerSummary(
                    name=server_name,
                    command=str(config.get("command", "")),
                    status="pending",
                    toolCount=0,
                    protocol=str(config.get("protocol", "")) or None,
                )
            )
        )

        try:
            descriptors = client.list_tools()
            try:
                resources = client.list_resources()
            except Exception:  # noqa: BLE001
                resources = []
            try:
                prompts = client.list_prompts()
            except Exception:  # noqa: BLE001
                prompts = []

            for resource in resources:
                resource_index[f"{server_name}:{resource.get('uri')}"] = {
                    "serverName": server_name,
                    "resource": resource,
                }
            for prompt in prompts:
                prompt_index[f"{server_name}:{prompt.get('name')}"] = {
                    "serverName": server_name,
                    "prompt": prompt,
                }

            for descriptor in descriptors:
                wrapped_name = (
                    f"mcp__{_sanitize_tool_segment(server_name)}__"
                    f"{_sanitize_tool_segment(str(descriptor.get('name', 'tool')))}"
                )
                descriptor_name = str(descriptor.get("name", "tool"))
                input_schema = _normalize_input_schema(descriptor.get("inputSchema"))

                def _validator(value: Any) -> Any:
                    return value

                def _run(input_data: Any, _context, *, _client=client, _descriptor_name=descriptor_name):
                    return _client.call_tool(_descriptor_name, input_data)

                tools.append(
                    ToolDefinition(
                        name=wrapped_name,
                        description=str(
                            descriptor.get("description")
                            or f"Call MCP tool {descriptor_name} from server {server_name}."
                        ),
                        input_schema=input_schema,
                        validator=_validator,
                        run=_run,
                    )
                )

            for index, summary in enumerate(servers):
                if summary["name"] == server_name:
                    servers[index] = asdict(
                        McpServerSummary(
                            name=server_name,
                            command=str(config.get("command", "")),
                            status="connected",
                            toolCount=len(descriptors),
                            protocol=client.protocol,
                            resourceCount=len(resources),
                            promptCount=len(prompts),
                        )
                    )
                    break
        except Exception as error:  # noqa: BLE001
            for index, summary in enumerate(servers):
                if summary["name"] == server_name:
                    servers[index] = asdict(
                        McpServerSummary(
                            name=server_name,
                            command=str(config.get("command", "")),
                            status="error",
                            toolCount=0,
                            error=str(error)[:200],
                            protocol=str(config.get("protocol", "")) or None,
                        )
                    )
                    break

    if resource_index:
        tools.append(
            ToolDefinition(
                name="list_mcp_resources",
                description="List available MCP resources exposed by connected MCP servers.",
                input_schema={"type": "object", "properties": {"server": {"type": "string"}}},
                validator=lambda value: {"server": value.get("server")} if isinstance(value, dict) else {"server": None},
                run=lambda input_data, _context: ToolResult(
                    ok=True,
                    output="\n".join(
                        f"{entry['serverName']}: {entry['resource'].get('uri')}"
                        + (f" ({entry['resource'].get('name')})" if entry["resource"].get("name") else "")
                        + (f" - {entry['resource'].get('description')}" if entry["resource"].get("description") else "")
                        for entry in resource_index.values()
                        if not input_data.get("server") or entry["serverName"] == input_data["server"]
                    )
                    or "No MCP resources available.",
                ),
            )
        )

        def _read_resource(input_data: dict, _context) -> ToolResult:
            client = next((item for item in clients if item.server_name == input_data["server"]), None)
            if client is None:
                return ToolResult(ok=False, output=f"Unknown MCP server: {input_data['server']}")
            return client.read_resource(input_data["uri"])

        tools.append(
            ToolDefinition(
                name="read_mcp_resource",
                description="Read a specific MCP resource by server and URI.",
                input_schema={
                    "type": "object",
                    "properties": {"server": {"type": "string"}, "uri": {"type": "string"}},
                    "required": ["server", "uri"],
                },
                validator=lambda value: value,
                run=_read_resource,
            )
        )

    if prompt_index:
        tools.append(
            ToolDefinition(
                name="list_mcp_prompts",
                description="List available MCP prompts exposed by connected MCP servers.",
                input_schema={"type": "object", "properties": {"server": {"type": "string"}}},
                validator=lambda value: {"server": value.get("server")} if isinstance(value, dict) else {"server": None},
                run=lambda input_data, _context: ToolResult(
                    ok=True,
                    output="\n".join(
                        f"{entry['serverName']}: {entry['prompt'].get('name')}"
                        + (
                            " args=["
                            + ", ".join(
                                f"{arg.get('name')}{'*' if arg.get('required') else ''}"
                                for arg in entry["prompt"].get("arguments", [])
                            )
                            + "]"
                            if entry["prompt"].get("arguments")
                            else ""
                        )
                        + (f" - {entry['prompt'].get('description')}" if entry["prompt"].get("description") else "")
                        for entry in prompt_index.values()
                        if not input_data.get("server") or entry["serverName"] == input_data["server"]
                    )
                    or "No MCP prompts available.",
                ),
            )
        )

        def _get_prompt(input_data: dict, _context) -> ToolResult:
            client = next((item for item in clients if item.server_name == input_data["server"]), None)
            if client is None:
                return ToolResult(ok=False, output=f"Unknown MCP server: {input_data['server']}")
            return client.get_prompt(input_data["name"], input_data.get("arguments"))

        tools.append(
            ToolDefinition(
                name="get_mcp_prompt",
                description="Fetch a rendered MCP prompt by server, prompt name, and optional arguments.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "server": {"type": "string"},
                        "name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["server", "name"],
                },
                validator=lambda value: value,
                run=_get_prompt,
            )
        )

    return {
        "tools": tools,
        "servers": servers,
        "dispose": lambda: [client.close() for client in clients],
    }


__all__ = [
    "McpServerSummary",
    "StdioMcpClient",
    "create_mcp_backed_tools",
]
