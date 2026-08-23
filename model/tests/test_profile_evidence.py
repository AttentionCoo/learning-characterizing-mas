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


def test_status_derivation_five_states():
    raw = {
        "learningPace": {
            "weeklyHours": 12, "source": "user_statement",
            "confidence": 1.0, "evidence": "我每周能学12小时",
        },
        "errorPattern": {
            "errorType": "conceptual", "source": "case_performance",
            "confidence": 0.7, "evidence": "答题2/5",
        },
        "cognitiveStyle": {
            "type": "visual", "source": "inferred",
            "confidence": 0.6, "evidence": "喜欢看视频",
        },
        "learningGoal": {
            "shortTerm": "x", "source": "inferred",
            "confidence": 0.5, "evidence": "",
        },
        "clinicalExperience": {"source": "unknown", "confidence": 0.1, "evidence": ""},
    }

    result = _normalize_dimensions(raw)

    assert result["learningPace"]["ev_status"] == "confirmed"
    assert result["errorPattern"]["ev_status"] == "observed"
    assert result["cognitiveStyle"]["ev_status"] == "inferred"
    assert result["learningGoal"]["ev_status"] == "suspected"
    assert result["clinicalExperience"]["ev_status"] == "unknown"


def test_restraint_clears_inferred_enumerables_and_numbers():
    raw = {
        "learningPace": {
            "weeklyHours": 12, "speed": "moderate",
            "source": "inferred", "confidence": 0.5, "evidence": "",
        },
        "knowledgeBase": {
            "level": "beginner", "source": "inferred",
            "confidence": 0.5, "evidence": "",
        },
        "cognitiveStyle": {
            "type": "visual", "source": "inferred",
            "confidence": 0.6, "evidence": "",
        },
        "errorPattern": {
            "errorType": "conceptual", "source": "inferred",
            "confidence": 0.4, "evidence": "",
        },
        "clinicalExperience": {
            "level": "none", "source": "inferred",
            "confidence": 0.3, "evidence": "",
        },
    }

    result = _normalize_dimensions(raw)

    assert result["learningPace"]["weeklyHours"] == 0
    assert result["learningPace"]["speed"] == ""
    assert result["knowledgeBase"]["level"] == ""
    assert result["cognitiveStyle"]["type"] == ""
    assert result["errorPattern"]["errorType"] == ""
    assert result["clinicalExperience"]["level"] == ""


def test_restraint_keeps_user_confirmed_enumerables():
    raw = {
        "learningPace": {
            "weeklyHours": 12, "speed": "moderate",
            "source": "user_statement", "confidence": 1.0,
            "evidence": "我每周能学12小时，节奏中等",
        },
    }

    result = _normalize_dimensions(raw)

    assert result["learningPace"]["weeklyHours"] == 12
    assert result["learningPace"]["speed"] == "moderate"


def test_restraint_field_level_evidence():
    """枚举字段即便维度 source 为 user_statement，证据不含对应提示词也要清空。"""
    raw = {
        "cognitiveStyle": {
            "type": "visual", "source": "user_statement",
            "confidence": 1.0, "evidence": "我偏好看视频和病例分析",
        },
        "clinicalExperience": {
            "level": "none", "source": "user_statement",
            "confidence": 1.0, "evidence": "我是大三学生，正在学神经病学",
        },
        "knowledgeBase": {
            "level": "beginner", "source": "user_statement",
            "confidence": 1.0, "evidence": "我的脑血管解剖比较薄弱",
        },
        "errorPattern": {
            "errorType": "conceptual", "source": "user_statement",
            "confidence": 1.0, "evidence": "我的脑血管解剖比较薄弱",
        },
    }

    result = _normalize_dimensions(raw)

    assert result["cognitiveStyle"]["type"] == ""
    assert result["clinicalExperience"]["level"] == ""
    assert result["knowledgeBase"]["level"] == ""
    assert result["errorPattern"]["errorType"] == ""


def test_restraint_keeps_field_when_evidence_matches():
    raw = {
        "cognitiveStyle": {
            "type": "visual", "source": "user_statement",
            "confidence": 1.0, "evidence": "我是视觉型学习者，喜欢看视频",
        },
        "clinicalExperience": {
            "level": "none", "source": "user_statement",
            "confidence": 1.0, "evidence": "我还没有进入临床实习",
        },
    }

    result = _normalize_dimensions(raw)

    assert result["cognitiveStyle"]["type"] == "visual"
    assert result["clinicalExperience"]["level"] == "none"


def test_topic_ev_status_and_restraint():
    raw = {
        "knowledgeBase": {
            "topics": {
                "mca": {"status": "weak", "source": "user_statement",
                        "confidence": 0.9, "evidence": "MCA容易搞混"},
                "pca": {"status": "weak", "source": "inferred",
                        "confidence": 0.5, "evidence": ""},
            },
        }
    }

    result = _normalize_dimensions(raw)
    topics = result["knowledgeBase"]["topics"]

    assert topics["mca"]["ev_status"] == "confirmed"
    assert topics["mca"]["status"] == "weak"
    # 无事实证据的推断：知识状态清回 unknown，证据状态 suspected
    assert topics["pca"]["status"] == "unknown"
    assert topics["pca"]["ev_status"] == "suspected"


def test_emotion_status_not_overwritten_by_evidence_status():
    """情绪枚举 status（motivated/anxious）与证据状态 ev_status 不撞名。"""
    raw = {
        "emotionState": {
            "status": "motivated", "description": "学习动力强",
            "source": "inferred", "confidence": 0.5, "evidence": "",
        }
    }

    result = _normalize_dimensions(raw)

    assert result["emotionState"]["status"] == "motivated"
    assert result["emotionState"]["ev_status"] == "suspected"


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
