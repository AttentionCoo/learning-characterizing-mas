"""Python 代码执行沙箱。

赛题「代码辅助开发」模块的执行后端：在受限子进程中运行学生提交的
Python 代码，支撑医学数据分析练习的运行与调试。

进程内隔离手段：
- ``python -I`` 隔离模式：忽略 PYTHONPATH、用户 site-packages 与当前目录注入
- POSIX 资源上限：CPU 时间、地址空间、输出文件大小、进程数
- 独立临时工作目录，运行结束即整体销毁
- 墙钟超时强制终止进程

进程级隔离只是第一道防线，生产部署依赖 Docker 容器边界（见 model/Dockerfile）。
"""
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Optional

MAX_CODE_CHARS = 50_000
MAX_OUTPUT_CHARS = 64_000
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60
DEFAULT_TIMEOUT_SECONDS = 30

_CPU_LIMIT_SECONDS = 60
_MEMORY_LIMIT_BYTES = 1 << 30  # 1 GB，需容纳 numpy/pandas 等数据分析库
_FILE_SIZE_LIMIT_BYTES = 8 << 20  # 8 MB
_NPROC_LIMIT = 512

SUPPORTED_LANGUAGES = {"python"}


@dataclass
class ExecutionResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    execution_time: float = 0.0
    truncated: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exitCode": self.exit_code,
            "executionTime": round(self.execution_time, 3),
            "truncated": self.truncated,
            "error": self.error,
        }


def _apply_resource_limits():
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (_CPU_LIMIT_SECONDS, _CPU_LIMIT_SECONDS))
    resource.setrlimit(resource.RLIMIT_FSIZE, (_FILE_SIZE_LIMIT_BYTES, _FILE_SIZE_LIMIT_BYTES))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (_MEMORY_LIMIT_BYTES, _MEMORY_LIMIT_BYTES))
        resource.setrlimit(resource.RLIMIT_NPROC, (_NPROC_LIMIT, _NPROC_LIMIT))
    except (ValueError, OSError):
        # macOS 对 RLIMIT_AS/NPROC 的支持不完整，失败时降级为仅 CPU/文件限制
        pass


def _truncate(text: str) -> tuple:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n... [输出过长，已截断]", True
    return text, False


def run_python(code: str, input_data: Optional[str] = None,
               timeout: int = DEFAULT_TIMEOUT_SECONDS) -> ExecutionResult:
    """在受限子进程中执行一段 Python 代码并返回运行结果。"""
    if not code or not code.strip():
        return ExecutionResult(success=False, error="代码内容为空")
    if len(code) > MAX_CODE_CHARS:
        return ExecutionResult(success=False, error=f"代码长度超过上限（{MAX_CODE_CHARS} 字符）")

    timeout = max(MIN_TIMEOUT_SECONDS, min(int(timeout), MAX_TIMEOUT_SECONDS))
    preexec = _apply_resource_limits if os.name == "posix" else None

    with tempfile.TemporaryDirectory(prefix="code_sandbox_") as workdir:
        script_path = os.path.join(workdir, "main.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(code)

        start = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-I", script_path],
                input=input_data,
                capture_output=True,
                text=True,
                cwd=workdir,
                timeout=timeout,
                preexec_fn=preexec,
                env={"PATH": os.environ.get("PATH", ""), "LANG": "en_US.UTF-8"},
            )
        except subprocess.TimeoutExpired as exc:
            elapsed = time.monotonic() - start
            partial = exc.stdout if isinstance(exc.stdout, str) else ""
            stdout, truncated = _truncate(partial or "")
            return ExecutionResult(
                success=False,
                stdout=stdout,
                execution_time=elapsed,
                truncated=truncated,
                error=f"执行超时（超过 {timeout} 秒），进程已终止",
            )
        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(success=False, error=f"沙箱启动失败: {exc}")

        elapsed = time.monotonic() - start
        stdout, out_trunc = _truncate(proc.stdout or "")
        stderr, err_trunc = _truncate(proc.stderr or "")
        return ExecutionResult(
            success=proc.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            execution_time=elapsed,
            truncated=out_trunc or err_trunc,
            error=None if proc.returncode == 0 else "代码运行出错，请查看 stderr",
        )
