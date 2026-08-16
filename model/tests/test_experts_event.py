"""experts 事件构建单测：专家名单 + 发言提取、失败发言过滤、空输出兜底。"""
from app.agents.orchestrators.learning_agent import LearningAgent


def test_build_experts_event_extracts_roles_and_advices():
    output = {
        "active_experts": ["需求分析智能体", "文档撰写智能体"],
        "需求分析智能体_advice": "建议先梳理知识盲区。",
        "文档撰写智能体_advice": "可生成一份基础讲义。",
        "debate_history": [{"round": 1}],
        "arbitration_result": "以需求分析为主，文档撰写为辅。",
    }
    event = LearningAgent._build_experts_event(output)

    assert event is not None
    assert event["type"] == "experts"
    assert event["active_experts"] == ["需求分析智能体", "文档撰写智能体"]
    assert len(event["advices"]) == 2
    assert event["advices"][0]["role"] == "需求分析智能体"
    assert event["advices"][0]["content"] == "建议先梳理知识盲区。"
    assert event["debate_rounds"] == 1
    assert event["arbitration"] == "以需求分析为主，文档撰写为辅。"


def test_build_experts_event_skips_failed_advices():
    output = {
        "active_experts": ["画像对话智能体", "特征抽取智能体"],
        "画像对话智能体_advice": "未能获取有效建议",
        "特征抽取智能体_advice": "已抽取专业与年级信息。",
    }
    event = LearningAgent._build_experts_event(output)

    assert [a["role"] for a in event["advices"]] == ["特征抽取智能体"]
    assert len(event["active_experts"]) == 2


def test_build_experts_event_returns_none_for_empty_output():
    assert LearningAgent._build_experts_event({}) is None
    assert LearningAgent._build_experts_event(None) is None
    assert LearningAgent._build_experts_event(
        {"active_experts": [], "debate_history": [], "arbitration_result": ""}
    ) is None
