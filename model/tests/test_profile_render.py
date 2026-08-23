"""画像证据渲染器测试：只渲染有证据的事实，其余待评估。"""
from app.services.profile_render import render_profile_report


def test_render_lists_confirmed_facts_and_pending_fields():
    dims = {
        "learningGoal": {
            "currentCourse": "神经病学", "shortTerm": "掌握脑血管解剖",
            "longTerm": "", "ev_status": "confirmed",
        },
        "knowledgeBase": {
            "level": "", "weakTopics": ["脑血管解剖"], "masteredTopics": [],
            "topics": {}, "ev_status": "confirmed",
        },
        "resourcePreference": {
            "preferences": ["视频", "病例分析"], "ev_status": "confirmed",
        },
        "cognitiveStyle": {"type": "", "preferences": [], "ev_status": "suspected"},
        "learningPace": {"weeklyHours": 0, "speed": "", "ev_status": "unknown"},
        "clinicalExperience": {"level": "", "ev_status": "unknown"},
        "errorPattern": {"errorType": "", "frequentErrors": [], "ev_status": "unknown"},
    }

    text = render_profile_report(dims)

    assert "神经病学" in text
    assert "脑血管解剖" in text
    assert "视频" in text and "病例分析" in text
    assert "待评估" in text
    # 未知字段不应出现臆测值
    assert "beginner" not in text
    assert "none" not in text


def test_render_empty_dimensions():
    assert "暂无已确认" in render_profile_report({})
    assert "暂无已确认" in render_profile_report(None)


def test_render_does_not_emit_inferred_enum_as_fact():
    dims = {
        "knowledgeBase": {"level": "", "weakTopics": [], "ev_status": "unknown"},
        "clinicalExperience": {"level": "", "ev_status": "unknown"},
        "learningPace": {"weeklyHours": 0, "speed": "", "ev_status": "unknown"},
    }

    text = render_profile_report(dims)

    assert "知识基础" in text or "待评估" in text
    assert "beginner" not in text
