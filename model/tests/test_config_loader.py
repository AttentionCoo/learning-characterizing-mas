"""YAML 配置加载冒烟测试：配置文件损坏应在 CI 阶段被发现，而非启动时。"""
from app.config.config_loader import (
    ExpertConfigManager,
    PromptManager,
    ReportTemplateManager,
)


def test_prompts_load():
    mgr = PromptManager()
    assert len(mgr._prompts) > 0


def test_experts_load():
    mgr = ExpertConfigManager()
    experts = mgr.get_experts()
    assert len(experts) == 8, f"预期 8 个专家智能体，实际 {len(experts)}"
    for expert in experts:
        assert expert.get("role"), f"专家缺少 role 字段: {expert}"
        assert expert.get("priority") is not None, f"专家缺少 priority 字段: {expert}"


def test_intent_expert_mapping_covers_all_intents():
    mgr = ExpertConfigManager()
    mapping = mgr.get_intent_expert_mapping()
    known_roles = {e.get("role") for e in mgr.get_experts()}
    for intent, roles in mapping.items():
        unknown = set(roles) - known_roles
        assert not unknown, f"意图 {intent} 引用了未定义的专家角色: {unknown}"


def test_report_modes_load():
    mgr = ReportTemplateManager()
    assert len(mgr.list_modes()) > 0
