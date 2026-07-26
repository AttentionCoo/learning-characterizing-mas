from app.agents.orchestrators.nodes.report_node import ReportNode
from app.agents.orchestrators.xf_xinghuo_agent import _REPORT_MODE_TO_INTENT


def test_resolve_explicit_code_assist_type():
    assert ReportNode._resolve_code_assist_type("【辅助功能代码】diagnose") == "diagnose"
    assert ReportNode._resolve_code_assist_type("【辅助功能代码】explain") == "explain"


def test_missing_code_assist_type_does_not_default_to_complete():
    assert ReportNode._resolve_code_assist_type("请帮我处理这段代码") is None


def test_each_code_assist_type_has_exclusive_prompt():
    assert "唯一任务是代码补全" in ReportNode._CODE_ASSIST_SYSTEMS["complete"]
    assert "唯一任务是错误诊断" in ReportNode._CODE_ASSIST_SYSTEMS["diagnose"]
    assert "唯一任务是代码优化" in ReportNode._CODE_ASSIST_SYSTEMS["optimize"]
    assert "唯一任务是代码讲解" in ReportNode._CODE_ASSIST_SYSTEMS["explain"]
    assert "不改写代码" in ReportNode._CODE_ASSIST_SYSTEMS["explain"]


def test_code_practice_resource_mode_is_routed_as_resource():
    assert _REPORT_MODE_TO_INTENT["code_generate"] == "resource"
