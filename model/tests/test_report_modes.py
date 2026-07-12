"""校验 Java 后端使用的 report_mode 与 Python 侧 YAML 模板一一对应。

历史上 ISSUE-004 正是 report_mode 与模板不匹配导致三个模块返回错误内容，
此测试从 Java 源码中动态提取 report_mode 字面量，防止同类回归。
"""
import re
from pathlib import Path

import pytest

from app.config.config_loader import ReportTemplateManager

REPO_ROOT = Path(__file__).resolve().parents[2]
JAVA_SRC = REPO_ROOT / "backend" / "ai" / "MyServer" / "src" / "main" / "java"

# Java AIStreamingServiceImpl 的内部兜底模式
FALLBACK_MODES = {"emergency"}


def _java_report_modes() -> set:
    """从 Java 控制器源码提取 buildSSEStream/streamChat 的 report_mode 字面量。"""
    modes = set()
    pattern = re.compile(r'(?:buildSSEStream|streamChat)\([^)]*"([a-z_]+)"\s*\)')
    for java_file in JAVA_SRC.rglob("*.java"):
        text = java_file.read_text(encoding="utf-8", errors="ignore")
        modes.update(pattern.findall(text))
    return modes


@pytest.fixture(scope="module")
def report_manager():
    return ReportTemplateManager()


def test_java_sources_present():
    assert JAVA_SRC.is_dir(), "Java 源码目录不存在，无法校验 report_mode 一致性"


def test_all_java_modes_have_templates(report_manager):
    java_modes = _java_report_modes()
    assert java_modes, "未从 Java 源码中提取到任何 report_mode，正则或代码结构可能已变化"

    available = set(report_manager.list_modes())
    missing = (java_modes | FALLBACK_MODES) - available
    assert not missing, f"以下 report_mode 在 report_templates.yaml 中没有模板: {missing}"


def test_templates_not_empty(report_manager):
    for mode in report_manager.list_modes():
        template = report_manager.get_template(mode)
        assert template and template.strip(), f"模板 {mode} 内容为空"
        assert report_manager.get_template_name(mode), f"模板 {mode} 缺少 name"
