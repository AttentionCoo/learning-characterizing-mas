import json

import pytest
from langchain_core.runnables import RunnableLambda

from app.agents.orchestrators.nodes.intent_node import IntentNode, _MODE_INPUT_RULES
from app.agents.orchestrators.learning_agent import (
    LearningAgent,
    _REPORT_MODE_TO_INTENT,
)
from app.routers.code import CodeAssistRequest, _build_code_assist_question


def _node_with_result(result):
    return IntentNode(RunnableLambda(lambda _: json.dumps(result, ensure_ascii=False)))


def _state(report_mode, intent_type, case_text="测试输入", images=None):
    return {
        "case_text": case_text,
        "report_mode": report_mode,
        "intent_type": intent_type,
        "images": images or [],
    }


@pytest.mark.asyncio
async def test_preset_function_rejects_unrelated_input():
    node = _node_with_result({
        "type": "tutor",
        "difficulty_score": 0.2,
        "is_stroke_related": True,
        "is_function_related": False,
        "reason": "输入是在咨询知识，不是在提供学习画像信息",
    })

    result = await node.run(_state("profile_build", "profile", "脑卒中有哪些症状？"))

    assert result["intent_type"] == "non_stroke"
    assert "学习画像构建" in result["input_rejection_message"]


@pytest.mark.asyncio
async def test_preset_function_allows_matching_input():
    node = _node_with_result({
        "type": "profile",
        "difficulty_score": 0.3,
        "is_stroke_related": False,
        "is_function_related": True,
        "reason": "用户正在描述学习基础和目标",
    })

    result = await node.run(_state(
        "profile_build",
        "profile",
        "我是临床医学大三学生，偏好视频课程，每周能学习六小时。",
    ))

    assert result["intent_type"] == "profile"
    assert "difficulty_score" not in result


@pytest.mark.asyncio
async def test_stroke_content_function_rejects_other_domain_input():
    node = _node_with_result({
        "type": "tutor",
        "difficulty_score": 0.2,
        "is_stroke_related": False,
        "is_function_related": True,
        "reason": "输入是在咨询高血压知识，与脑卒中学习无关",
    })

    result = await node.run(_state("tutor", "tutor", "请讲解原发性高血压"))

    assert result["intent_type"] == "non_stroke"
    assert "脑卒中学习无关" in result["input_rejection_message"]


@pytest.mark.asyncio
async def test_code_assist_allows_code_input_outside_stroke_domain():
    node = _node_with_result({
        "type": "irrelevant",
        "difficulty_score": 0.4,
        "is_stroke_related": False,
        "is_function_related": True,
        "reason": "输入是明确的代码错误诊断请求",
    })

    result = await node.run(_state(
        "code_assist",
        "code_assist",
        "辅助类型：错误诊断\n现有代码：print(1/0)",
    ))

    assert result["intent_type"] == "code_assist"


@pytest.mark.parametrize("case_text", [
    "【辅助功能代码】complete\n诉求：补全这个函数\n现有代码：\n```python\ndef add(a, b):\n    \n```",
    "【辅助功能代码】complete\n诉求：请实现冒泡排序算法",
])
@pytest.mark.asyncio
async def test_code_assist_uses_structural_evidence_before_llm_guard(case_text):
    node = _node_with_result({
        "type": "irrelevant",
        "difficulty_score": 0.2,
        "is_stroke_related": False,
        "is_function_related": False,
        "reason": "无法确认输入是否属于代码辅助",
    })

    result = await node.run(_state("code_assist", "code_assist", case_text))

    assert result["intent_type"] == "code_assist"
    assert result["input_rejection_message"] == ""


@pytest.mark.parametrize(("prompt", "existing_code"), [
    ("帮我看看", "def add(a, b):\n    return a + b"),
    ("冒泡排序算法", ""),
])
@pytest.mark.asyncio
async def test_code_assist_route_payload_accepts_selected_mode_and_programming_evidence(
    prompt,
    existing_code,
):
    node = _node_with_result({
        "type": "irrelevant",
        "difficulty_score": 0.2,
        "is_stroke_related": False,
        "is_function_related": False,
        "reason": "无法确认输入是否属于代码辅助",
    })
    question = _build_code_assist_question(CodeAssistRequest(
        assistType="complete",
        prompt=prompt,
        existingCode=existing_code,
    ))

    result = await node.run(_state("code_assist", "code_assist", question))

    assert result["intent_type"] == "code_assist"
    assert result["input_rejection_message"] == ""


@pytest.mark.asyncio
async def test_code_assist_still_rejects_non_programming_request():
    node = _node_with_result({
        "type": "code_assist",
        "difficulty_score": 0.2,
        "is_stroke_related": False,
        "is_function_related": True,
        "reason": "用户选择了代码讲解",
    })

    question = _build_code_assist_question(CodeAssistRequest(
        assistType="explain",
        prompt="解释一下今天的天气",
    ))
    result = await node.run(_state("code_assist", "code_assist", question))

    assert result["intent_type"] == "non_stroke"
    assert "代码辅助" in result["input_rejection_message"]


@pytest.mark.asyncio
async def test_image_input_defers_domain_check_to_vision_analysis():
    node = _node_with_result({
        "type": "tutor",
        "is_stroke_related": False,
        "is_function_related": True,
        "reason": "文字诉求属于图片辅导，图片内容需要视觉分析",
    })

    result = await node.run(_state(
        "tutor",
        "tutor",
        "请分析这张图片",
        images=["data:image/png;base64,abc"],
    ))

    assert result["intent_type"] == "tutor"


@pytest.mark.asyncio
async def test_invalid_guard_result_is_rejected_by_default():
    node = IntentNode(RunnableLambda(lambda _: "无法判断"))

    result = await node.run(_state("tutor", "tutor", "请讲解脑卒中溶栓时间窗"))

    assert result["intent_type"] == "non_stroke"
    assert "无法确认" in result["input_rejection_message"]


@pytest.mark.asyncio
async def test_guard_call_failure_is_rejected_by_default():
    def raise_guard_error(_):
        raise RuntimeError("guard unavailable")

    node = IntentNode(RunnableLambda(raise_guard_error))

    result = await node.run(_state("tutor", "tutor", "请讲解脑卒中溶栓时间窗"))

    assert result["intent_type"] == "non_stroke"
    assert "无法确认" in result["input_rejection_message"]


@pytest.mark.asyncio
async def test_assessment_wrapper_cannot_hide_unrelated_user_input():
    node = _node_with_result({
        "type": "assessment",
        "difficulty_score": 0.2,
        "is_stroke_related": True,
        "is_function_related": True,
        "reason": "固定包装中包含评估任务说明",
    })
    wrapped_input = """请为我生成学习效果评估报告：
=== 学生真实学习数据 ===
【学习进度】已完成 3/10
=== 数据结束 ===
补充说明：今天天气怎么样
评估类型：comprehensive
请严格基于以上真实学习数据进行分析评估。"""

    result = await node.run(_state(
        "assessment_comprehensive",
        "assessment",
        wrapped_input,
    ))

    assert result["intent_type"] == "non_stroke"
    assert "综合学习评估" in result["input_rejection_message"]


@pytest.mark.asyncio
async def test_tutor_metadata_cannot_hide_unrelated_user_input():
    node = _node_with_result({
        "type": "tutor",
        "difficulty_score": 0.2,
        "is_stroke_related": True,
        "is_function_related": True,
        "reason": "元数据中包含脑卒中课程",
    })

    result = await node.run(_state(
        "tutor",
        "tutor",
        "帮我写一首诗\n辅导模式：详细讲解\n课程：脑卒中诊疗",
    ))

    assert result["intent_type"] == "non_stroke"


@pytest.mark.asyncio
async def test_valid_wrapped_assessment_input_is_allowed():
    node = _node_with_result({
        "type": "assessment",
        "difficulty_score": 0.4,
        "is_stroke_related": True,
        "is_function_related": True,
        "reason": "用户明确要求评估学习效果",
    })
    wrapped_input = """请为我生成学习效果评估报告：
=== 学生真实学习数据 ===
【学习进度】已完成 3/10
=== 数据结束 ===
补充说明：重点评估我的脑卒中诊疗知识掌握情况
评估类型：comprehensive"""

    result = await node.run(_state(
        "assessment_comprehensive",
        "assessment",
        wrapped_input,
    ))

    assert result["intent_type"] == "assessment"


@pytest.mark.parametrize(
    ("report_mode", "intent_type"),
    _REPORT_MODE_TO_INTENT.items(),
)
@pytest.mark.asyncio
async def test_every_preset_function_rejects_plain_unrelated_input(
    report_mode,
    intent_type,
):
    node = _node_with_result({
        "type": intent_type,
        "difficulty_score": 0.2,
        "is_stroke_related": True,
        "is_function_related": True,
        "reason": "错误地认为输入相关",
    })

    result = await node.run(_state(report_mode, intent_type, "今天天气怎么样"))

    assert result["intent_type"] == "non_stroke"


_VALID_MODE_INPUTS = {
    "profile_build": "我是临床医学大三学生，每周学习六小时，偏好病例视频。",
    "resource_generate": "请生成脑卒中静脉溶栓学习资料。",
    "document_generate": "请生成脑卒中静脉溶栓课程讲解文档。",
    "mindmap_generate": "请生成脑卒中诊疗知识思维导图。",
    "quiz_generate": "请生成脑卒中二级预防练习题。",
    "reading_generate": "请整理脑卒中诊疗指南阅读材料。",
    "case_study_generate": "请生成脑卒中急诊病例分析。",
    "plan_generate": "请生成脑卒中复习阶段方案。",
    "code_generate": "请生成脑卒中数据分析 Python 代码案例。",
    "assessment_generate": "请评估我的脑卒中知识掌握情况。",
    "assessment": "请评估我的学习效果和知识掌握情况。",
    "assessment_comprehensive": "请综合评估我的学习能力和知识掌握情况。",
    "assessment_knowledge": "请评估我的脑卒中知识掌握程度。",
    "assessment_skill": "请评估我的脑卒中临床技能水平。",
    "assessment_progress": "请评估我的脑卒中学习进度和完成率。",
    "tutor": "请讲解脑卒中静脉溶栓时间窗。",
    "learning_path_generate": "请规划我的脑卒中课程学习路径。",
    "learning_path": "请规划我的脑卒中课程学习路径。",
    "emergency": "请分析我的脑卒中学习需求。",
    "code_assist": "现有代码：print(1/0)",
}


@pytest.mark.parametrize(
    ("report_mode", "case_text"),
    _VALID_MODE_INPUTS.items(),
)
@pytest.mark.asyncio
async def test_every_preset_function_keeps_valid_input(report_mode, case_text):
    intent_type = _REPORT_MODE_TO_INTENT[report_mode]
    node = _node_with_result({
        "type": intent_type,
        "difficulty_score": 0.3,
        "is_stroke_related": True,
        "is_function_related": True,
        "reason": "输入属于当前功能",
    })

    result = await node.run(_state(report_mode, intent_type, case_text))

    assert result["intent_type"] == intent_type


@pytest.mark.parametrize("report_mode", [
    "document_generate", "mindmap_generate", "quiz_generate",
    "reading_generate", "case_study_generate", "plan_generate",
    "code_generate",
])
@pytest.mark.asyncio
async def test_resource_modes_allow_frontend_default_request(report_mode):
    intent_type = _REPORT_MODE_TO_INTENT[report_mode]
    node = _node_with_result({
        "type": intent_type,
        "difficulty_score": 0.2,
        "is_stroke_related": True,
        "is_function_related": True,
        "reason": "用户已在页面选择资源类型",
    })

    result = await node.run(_state(
        report_mode,
        intent_type,
        "请为我生成脑卒中相关的学习资料",
    ))

    assert result["intent_type"] == intent_type


@pytest.mark.parametrize("report_mode", [
    "assessment_comprehensive", "assessment_knowledge",
    "assessment_skill", "assessment_progress",
])
@pytest.mark.asyncio
async def test_assessment_modes_allow_frontend_default_request(report_mode):
    node = _node_with_result({
        "type": "assessment",
        "difficulty_score": 0.2,
        "is_stroke_related": True,
        "is_function_related": True,
        "reason": "用户已在页面选择评估类型",
    })

    result = await node.run(_state(
        report_mode,
        "assessment",
        "请为我进行学习评估",
    ))

    assert result["intent_type"] == "assessment"


def test_every_preset_function_has_an_input_rule():
    assert set(_REPORT_MODE_TO_INTENT) == set(_MODE_INPUT_RULES)


@pytest.mark.asyncio
async def test_unknown_function_mode_is_rejected_before_graph_execution():
    agent = object.__new__(LearningAgent)

    events = [
        event
        async for event in agent.run_learning_reasoning(
            case_text="测试输入",
            report_mode="unknown_mode",
        )
    ]

    assert events == [{
        "type": "token",
        "content": "不支持的功能类型「unknown_mode」，请求已被拦截。",
    }]
