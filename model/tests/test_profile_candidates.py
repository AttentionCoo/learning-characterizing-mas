"""Profile Update Candidate 生成器测试。"""
import json
from types import SimpleNamespace

import pytest
from langchain_core.runnables import RunnableLambda

from app.services.profile_candidates import (
    _normalize_candidates,
    generate_profile_candidates,
)


def test_normalize_keeps_valid_candidates():
    raw = [
        {
            "dimension": "knowledgeBase",
            "topic": "mca",
            "topic_status": "weak",
            "source": "user_statement",
            "confidence": 0.9,
            "evidence": "MCA和PCA供血区域比较容易搞混",
            "reason": "学生明确自述",
        },
        {
            "dimension": "learningPace",
            "field": "weeklyHours",
            "value": 12,
            "source": "user_statement",
            "confidence": 1.0,
            "evidence": "我每周能学12小时",
            "reason": "",
        },
    ]

    result = _normalize_candidates(raw)

    assert len(result) == 2
    assert result[0]["topic"] == "mca"
    assert result[0]["topic_status"] == "weak"
    assert result[0]["confidence"] == 0.9
    assert result[1]["field"] == "weeklyHours"
    assert result[1]["value"] == 12


def test_normalize_drops_candidates_without_evidence():
    raw = [
        {
            "dimension": "knowledgeBase",
            "topic": "pca",
            "topic_status": "weak",
            "source": "inferred",
            "confidence": 0.5,
            "evidence": "",
            "reason": "可能是薄弱点",
        },
        {
            "dimension": "emotionState",
            "field": "status",
            "value": "motivated",
            "source": "user_statement",
            "confidence": 0.8,
            "evidence": "",
            "reason": "",
        },
    ]

    result = _normalize_candidates(raw)

    assert result == []


def test_normalize_drops_invalid_dimension_topic_and_source():
    raw = [
        {"dimension": "hobby", "source": "user_statement", "confidence": 1.0, "evidence": "我喜欢动漫"},
        {"dimension": "knowledgeBase", "topic": "hobby_anatomy", "topic_status": "weak",
         "source": "user_statement", "confidence": 0.8, "evidence": "不太熟"},
        {"dimension": "learningGoal", "field": "shortTerm", "value": "x",
         "source": "guessed", "confidence": 0.8, "evidence": "原话"},
    ]

    result = _normalize_candidates(raw)

    assert result == []


def test_normalize_topic_without_knowledge_base_is_dropped():
    raw = [{
        "dimension": "learningPace",
        "topic": "mca",
        "topic_status": "weak",
        "source": "user_statement",
        "confidence": 0.8,
        "evidence": "原话",
    }]

    result = _normalize_candidates(raw)

    assert result == []


@pytest.mark.asyncio
async def test_generate_profile_candidates_returns_normalized_list():
    llm = RunnableLambda(lambda _: SimpleNamespace(content=json.dumps([
        {
            "dimension": "learningPace",
            "field": "weeklyHours",
            "value": 12,
            "source": "user_statement",
            "confidence": 1.0,
            "evidence": "我每周能学12小时",
            "reason": "学生明确自述",
        },
        {
            "dimension": "knowledgeBase",
            "topic": "mca",
            "topic_status": "weak",
            "source": "user_statement",
            "confidence": 0.9,
            "evidence": "MCA和PCA容易搞混",
            "reason": "",
        },
        {"dimension": "emotionState", "field": "status", "value": "anxious",
         "source": "inferred", "confidence": 0.5, "evidence": "", "reason": ""},
    ], ensure_ascii=False)))

    result = await generate_profile_candidates(llm, "测试对话")

    assert len(result) == 2
    assert result[0]["source"] == "user_statement"


@pytest.mark.asyncio
async def test_generate_profile_candidates_empty_on_failure():
    def fail(_):
        raise RuntimeError("llm down")

    result = await generate_profile_candidates(RunnableLambda(fail), "对话")

    assert result == []


@pytest.mark.asyncio
async def test_generate_profile_candidates_empty_conversation():
    result = await generate_profile_candidates(RunnableLambda(lambda _: "[]"), "")

    assert result == []
