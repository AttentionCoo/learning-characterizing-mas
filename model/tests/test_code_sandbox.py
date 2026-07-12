"""代码执行沙箱测试：正常执行、stdin、报错、超时、输入校验、输出截断。"""
import pytest

from app.services.code_sandbox import (
    MAX_CODE_CHARS,
    MAX_OUTPUT_CHARS,
    run_python,
)


def test_simple_print():
    result = run_python('print("hello, stroke")')
    assert result.success
    assert result.stdout.strip() == "hello, stroke"
    assert result.exit_code == 0
    assert not result.truncated


def test_stdin_input():
    result = run_python("name = input()\nprint(f'hi {name}')", input_data="LearnAgent\n")
    assert result.success
    assert "hi LearnAgent" in result.stdout


def test_runtime_error_captured():
    result = run_python("1 / 0")
    assert not result.success
    assert result.exit_code != 0
    assert "ZeroDivisionError" in result.stderr


def test_timeout_kills_process():
    result = run_python("while True:\n    pass", timeout=1)
    assert not result.success
    assert "超时" in result.error
    assert result.execution_time < 10


def test_empty_code_rejected():
    result = run_python("   ")
    assert not result.success
    assert "为空" in result.error


def test_oversized_code_rejected():
    result = run_python("x = 1\n" * (MAX_CODE_CHARS // 6 + 1))
    assert not result.success
    assert "上限" in result.error


def test_output_truncated():
    result = run_python(f'print("A" * {MAX_OUTPUT_CHARS + 1000})')
    assert result.success
    assert result.truncated
    assert "已截断" in result.stdout


def test_isolated_mode_no_cwd_injection():
    # -I 模式下临时工作目录不会注入 sys.path[0]，防止同目录文件劫持导入
    result = run_python("import sys; print(sys.flags.isolated)")
    assert result.success
    assert result.stdout.strip() == "1"


def test_result_dict_shape():
    data = run_python("print(1)").to_dict()
    assert set(data) == {"success", "stdout", "stderr", "exitCode",
                         "executionTime", "truncated", "error"}
