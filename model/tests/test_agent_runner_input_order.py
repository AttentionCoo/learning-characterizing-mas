import pytest

from app.runtime import resources
from app.agents.orchestrators.nodes.vision_node import VisionAnalysisNode
from app.services.agent_runner import run_agent_background


class _TaskManager:
    def __init__(self):
        self.events = []
        self.result = None

    def add_event(self, _task_id, event):
        self.events.append(event)

    def complete_task(self, _task_id, result):
        self.result = result

    def fail_task(self, _task_id, message):
        raise AssertionError(message)


class _Agent:
    def __init__(self):
        self.images = None

    async def run_learning_reasoning(self, **kwargs):
        self.images = kwargs.get("images")
        yield {"type": "token", "content": "处理完成"}


class _LegacyVisionService:
    def __init__(self):
        self.called = False

    async def analyze_stream(self, **_kwargs):
        self.called = True
        if False:
            yield None


@pytest.mark.asyncio
async def test_images_enter_graph_before_any_legacy_vision_analysis(monkeypatch):
    agent = _Agent()
    task_manager = _TaskManager()
    legacy_vision = _LegacyVisionService()
    monkeypatch.setitem(resources, "vision_service", legacy_vision)

    await run_agent_background(
        task_id="task-1",
        agent=agent,
        case_text="请分析这张图片",
        all_info="",
        report_mode="tutor",
        task_mgr=task_manager,
        images=["image-data"],
    )

    assert legacy_vision.called is False
    assert agent.images == ["image-data"]
    assert task_manager.result == "处理完成"


@pytest.mark.asyncio
async def test_image_gate_rejects_when_visual_model_is_unavailable():
    node = object.__new__(VisionAnalysisNode)
    node._api_key = None

    assert await node._run_stroke_gate_cn(["image-data"]) is False


@pytest.mark.asyncio
async def test_complete_report_replaces_streamed_parts_in_task_result():
    class ReplacingAgent:
        async def run_learning_reasoning(self, **_kwargs):
            yield {"type": "token", "content": "一、旧内容\n"}
            yield {"type": "replace", "content": "一、新内容\n二、下一项"}

    task_manager = _TaskManager()

    await run_agent_background(
        task_id="task-replace",
        agent=ReplacingAgent(),
        case_text="生成报告",
        all_info="",
        report_mode="tutor",
        task_mgr=task_manager,
    )

    assert task_manager.result == "一、新内容\n二、下一项"
