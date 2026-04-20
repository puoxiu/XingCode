# 从XingCode核心工具模块导入核心类
# ToolContext: 工具执行上下文（包含工作目录等环境信息）
# ToolDefinition: 工具定义类（封装工具的名称、描述、校验、执行逻辑）
# ToolRegistry: 工具注册器（负责注册、管理、执行所有工具）
# ToolResult: 工具执行结果类（统一返回执行成功/失败、输出信息）
from XingCode.core.tooling import ToolContext, ToolDefinition, ToolRegistry, ToolResult

#  pytest ./tests/unit/test_tooling.py -v

def test_tool_registry_executes_registered_tool() -> None:
    """
    测试用例1：验证工具注册器可以正常执行【已注册的工具】
    核心目标：确保注册的工具能被正确调用，并返回预期结果
    """
    # 定义echo工具的执行函数：接收输入参数和上下文，返回工具执行结果
    def run_echo(input_data: dict, _context: ToolContext) -> ToolResult:
        # 逻辑：拼接字符串，返回成功结果，输出为 echo:输入的文本
        return ToolResult(ok=True, output=f"echo:{input_data['text']}")

    # 初始化工具注册器，传入注册的工具列表
    registry = ToolRegistry(
        [
            # 定义一个名为echo的工具
            ToolDefinition(
                name="echo",                # 工具名称
                description="Echo text.",   # 工具描述
                input_schema={"type": "object"},  # 输入参数格式（JSON Schema）
                validator=lambda value: value,    # 参数校验器：直接返回原值（无严格校验）
                run=run_echo,                     # 绑定工具的执行函数
            )
        ]
    )

    # 执行注册的echo工具，传入参数{"text": "hello"}，上下文为当前目录
    result = registry.execute("echo", {"text": "hello"}, ToolContext(cwd="."))

    # 断言：执行结果成功
    assert result.ok is True
    # 断言：输出内容符合预期
    assert result.output == "echo:hello"


def test_tool_registry_returns_error_for_unknown_tool() -> None:
    """
    测试用例2：验证调用【未注册/不存在的工具】时，返回错误结果
    核心目标：确保工具注册器对未知工具做容错处理，返回明确错误
    """
    # 初始化空的工具注册器（无任何注册工具）
    registry = ToolRegistry([])

    # 调用不存在的工具missing
    result = registry.execute("missing", {}, ToolContext(cwd="."))

    # 断言：执行结果失败
    assert result.ok is False
    # 断言：错误信息包含"Unknown tool"（未知工具）
    assert "Unknown tool" in result.output


def test_tool_registry_wraps_validation_errors() -> None:
    """
    测试用例3：验证【工具参数校验失败】时，注册器正确捕获并包装校验错误
    核心目标：确保参数校验异常不会崩溃，返回标准化的校验错误
    """
    # 初始化注册器，注册一个带严格校验的工具
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="strict",                # 工具名称
                description="Strict validator.",  # 工具描述
                input_schema={"type": "object"},  # 输入格式
                # 参数校验器：强制抛出ValueError异常，模拟校验失败
                validator=lambda _value: (_ for _ in ()).throw(ValueError("bad input")),
                # 执行函数：永远不会执行（因为校验提前失败）
                run=lambda input_data, context: ToolResult(ok=True, output="unreachable"),
            )
        ]
    )

    # 执行工具，传入参数触发校验失败
    result = registry.execute("strict", {"bad": True}, ToolContext(cwd="."))

    # 断言：执行结果失败
    assert result.ok is False
    # 断言：错误信息包含输入校验失败的标识
    assert "Input validation error" in result.output
    # 断言：错误信息包含自定义的异常描述
    assert "bad input" in result.output


def test_tool_registry_wraps_execution_errors() -> None:
    """
    测试用例4：验证【工具执行过程中抛出异常】时，注册器正确捕获并包装执行错误
    核心目标：确保工具运行时异常不会崩溃，返回标准化的执行错误
    """
    # 定义执行函数：主动抛出运行时异常，模拟执行失败
    def raise_error(_input_data: dict, _context: ToolContext) -> ToolResult:
        raise RuntimeError("boom")

    # 初始化注册器，注册会抛出异常的工具
    registry = ToolRegistry(
        [
            ToolDefinition(
                name="explode",             # 工具名称
                description="Raises an error.",  # 工具描述
                input_schema={"type": "object"},  # 输入格式
                validator=lambda value: value,    # 无严格校验
                run=raise_error,                  # 绑定会抛异常的执行函数
            )
        ]
    )

    # 执行工具，触发运行时异常
    result = registry.execute("explode", {}, ToolContext(cwd="."))

    # 断言：执行结果失败
    assert result.ok is False
    # 断言：错误信息包含工具执行失败的标识
    assert "Tool execution error" in result.output
    # 断言：错误信息包含异常信息
    assert "boom" in result.output


def test_tool_registry_dispose_calls_disposer() -> None:
    """
    测试用例5：验证调用注册器的dispose()方法时，会执行注册的清理函数（disposer）
    核心目标：确保资源清理逻辑正常触发，用于释放连接、关闭文件等场景
    """
    # 定义一个列表，用于标记清理函数是否被调用
    disposed: list[bool] = []
    # 初始化注册器，传入空工具列表 + 自定义清理函数（向列表添加True）
    registry = ToolRegistry([], disposer=lambda: disposed.append(True))

    # 调用销毁/清理方法
    registry.dispose()

    # 断言：清理函数被成功执行（列表中有True）
    assert disposed == [True]