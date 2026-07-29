import json

import pytest
from langchain_core.runnables import RunnableLambda

from app.agents.orchestrators.nodes.intent_node import IntentNode, _MODE_INPUT_RULES
from app.agents.orchestrators.xf_xinghuo_agent import (
    LearningAgent,
    _REPORT_MODE_TO_INTENT,
)


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
