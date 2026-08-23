"""画像维度证据链元数据测试：source/confidence/evidence/updated_at 归一化。"""
import json
from datetime import date

import pytest
from langchain_core.runnables import RunnableLambda

from app.services.profile_extractor import (
    _normalize_dimensions,
    extract_profile_dimensions,
)


def test_normalize_adds_default_meta_to_every_dimension():
    raw = {
        "knowledgeBase": {
            "level": "beginner",
            "description": "基础知识一般",
            "weakTopics": ["脑血管解剖"],
        },
        "emotionState": {"status": "motivated", "description": "学习动力强"},
    }

    result = _normalize_dimensions(raw)

    kb = result["knowledgeBase"]
    assert kb["source"] == "inferred"
    assert kb["confidence"] == 0.5
    assert kb["evidence"] == ""
    assert kb["updated_at"] == date.today().isoformat()

    emotion = result["emotionState"]
    assert emotion["observed_at"] == date.today().isoformat()


def test_normalize_preserves_valid_meta_and_clamps_confidence():
    raw = {
        "learningPace": {
            "weeklyHours": 12,
            "source": "user_statement",
            "confidence": 1.5,
            "evidence": "我每周能学12小时",
        },
        "cognitiveStyle": {
            "type": "visual",
            "source": "inferred",
            "confidence": -0.3,
            "evidence": "",
        },
    }

    result = _normalize_dimensions(raw)

    assert result["learningPace"]["source"] == "user_statement"
    assert result["learningPace"]["confidence"] == 1.0
    assert result["learningPace"]["evidence"] == "我每周能学12小时"
    assert result["cognitiveStyle"]["confidence"] == 0.0


def test_normalize_falls_back_to_inferred_on_invalid_source():
    raw = {
        "learningGoal": {
            "shortTerm": "掌握脑血管解剖",
            "source": "llm_guessed",
            "confidence": 0.9,
        }
    }

    result = _normalize_dimensions(raw)

    assert result["learningGoal"]["source"] == "inferred"
    assert result["learningGoal"]["confidence"] == 0.9


def test_normalize_passes_through_non_dimension_keys():
    raw = {"custom_field": {"anything": 1}, "knowledgeBase": {"level": "beginner"}}

    result = _normalize_dimensions(raw)

    assert result["custom_field"] == {"anything": 1}
    assert "source" in result["knowledgeBase"]


def test_normalize_knowledge_base_topic_tree():
    raw = {
        "knowledgeBase": {
            "level": "beginner",
            "topics": {
                "mca": {"status": "weak", "source": "user_statement",
                        "confidence": 1.0, "evidence": "MCA和PCA供血区域比较容易搞混"},
                "pca": {"status": "weak", "source": "user_statement", "confidence": 0.9},
            },
        }
    }

    result = _normalize_dimensions(raw)

    topics = result["knowledgeBase"]["topics"]
    # 九个固定子主题全部补齐
    assert set(topics.keys()) == {
        "willis_circle", "ica_system", "mca", "aca", "pca",
        "vertebrobasilar", "brainstem", "cerebellum", "venous_system",
    }
    assert topics["mca"]["status"] == "weak"
    assert topics["mca"]["evidence"] == "MCA和PCA供血区域比较容易搞混"
    assert topics["pca"]["confidence"] == 0.9
    # 未提及的子主题默认 unknown + unknown 来源
    assert topics["willis_circle"]["status"] == "unknown"
    assert topics["willis_circle"]["source"] == "unknown"
    assert topics["willis_circle"]["confidence"] == 0.2


def test_normalize_topic_invalid_status_falls_back_to_unknown():
    raw = {
        "knowledgeBase": {
            "topics": {"aca": {"status": "excellent", "source": "inferred", "confidence": 0.8}},
        }
    }

    result = _normalize_dimensions(raw)

    assert result["knowledgeBase"]["topics"]["aca"]["status"] == "unknown"


@pytest.mark.asyncio
async def test_extract_profile_dimensions_returns_normalized_dict():
    from types import SimpleNamespace

    payload = json.dumps({
        "knowledgeBase": {
            "level": "beginner",
            "description": "基础一般",
            "weakTopics": ["脑血管解剖"],
            "source": "user_statement",
            "confidence": 1.0,
            "evidence": "我的脑血管解剖比较薄弱",
        },
        "learningPace": {
            "weeklyHours": 12,
            "source": "inferred",
            "confidence": 0.5,
            "evidence": "",
        },
    }, ensure_ascii=False)
    llm = RunnableLambda(lambda _: SimpleNamespace(content=payload))

    result = await extract_profile_dimensions(llm, "测试对话")

    assert result["knowledgeBase"]["source"] == "user_statement"
    assert result["knowledgeBase"]["confidence"] == 1.0
    assert result["learningPace"]["updated_at"] == date.today().isoformat()


@pytest.mark.asyncio
async def test_extract_profile_dimensions_returns_none_on_failure():
    def fail(_):
        raise RuntimeError("llm down")

    result = await extract_profile_dimensions(RunnableLambda(fail), "对话")

    assert result is None
