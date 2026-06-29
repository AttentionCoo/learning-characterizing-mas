import os
import sys
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from typing import AsyncGenerator

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.assistant import LearningAssistant
from app.agents.orchestrators.qwen_agent import LearningAgent
from app.agents.core.schema import LearningState
from app.config.config_loader import PromptManager, ReportTemplateManager


@pytest.fixture
def mock_llm():
    llm = Mock()
    llm.astream = AsyncMock()
    llm.ainvoke = AsyncMock()
    llm.invoke = Mock()
    return llm


@pytest.fixture
def mock_retriever():
    retriever = Mock()
    retriever.search = Mock(return_value=[])
    return retriever


@pytest.fixture
def mock_prompt_manager():
    manager = Mock(spec=PromptManager)
    manager.get = Mock(return_value=None)
    return manager


@pytest.fixture
def mock_report_manager():
    manager = Mock(spec=ReportTemplateManager)
    manager.system_role = "你是资深学习顾问。"
    manager.get_template = Mock(return_value="模板内容")
    manager.get_template_name = Mock(return_value="默认模式")
    return manager


class TestLearningAssistant:

    def test_init(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        assistant = LearningAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        assert assistant.llm == mock_llm
        assert assistant.llm_fast == mock_llm
        assert assistant.retriever == mock_retriever
        assert assistant.prompts == mock_prompt_manager
        assert assistant.reports == mock_report_manager

    def test_init_with_default_llm(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        assistant = LearningAssistant(
            llm=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        assert assistant.llm == mock_llm
        assert assistant.llm_fast == mock_llm

    @pytest.mark.asyncio
    async def test_afast_parallel_retrieve_empty(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        assistant = LearningAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )
        result = await assistant.afast_parallel_retrieve([])
        assert result == ""

    @pytest.mark.asyncio
    async def test_stream_fast_response(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        async def mock_astream(*args, **kwargs):
            mock_chunk = Mock()
            mock_chunk.content = "测试响应"
            yield mock_chunk

        mock_llm.astream = mock_astream

        assistant = LearningAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        result = []
        async for chunk in assistant.stream_fast_response("测试问题"):
            result.append(chunk)

        assert len(result) > 0
        assert "测试响应" in result

    @pytest.mark.asyncio
    async def test_stream_fast_response_with_evidence(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        async def mock_astream(*args, **kwargs):
            mock_chunk = Mock()
            mock_chunk.content = "基于证据的回答"
            yield mock_chunk

        mock_llm.astream = mock_astream

        assistant = LearningAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        result = []
        async for chunk in assistant.stream_fast_response("测试问题", evidence="参考证据"):
            result.append(chunk)

        assert len(result) > 0
        assert "基于证据的回答" in result


class TestLearningAgent:

    def test_init(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        learning_assistant = LearningAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        agent = LearningAgent(
            llm_proposer=mock_llm,
            llm_critic=mock_llm,
            learning_assistant=learning_assistant,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        assert agent.llm_proposer == mock_llm
        assert agent.llm_critic == mock_llm
        assert agent.learning_assistant == learning_assistant
        assert agent.prompts == mock_prompt_manager
        assert agent.reports == mock_report_manager

    @pytest.mark.asyncio
    async def test_analyze_learning_risk_fast(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        learning_assistant = LearningAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        agent = LearningAgent(
            llm_proposer=mock_llm,
            llm_critic=mock_llm,
            learning_assistant=learning_assistant,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        mock_response = Mock()
        mock_response.content = '{"riskLevel": "高风险", "suggestion": "建议加强基础学习", "analysisDetails": "知识点掌握不足"}'
        mock_llm.ainvoke.return_value = mock_response

        result = await agent.analyze_learning_risk_fast("学生男，大二，基础薄弱")

        assert "riskLevel" in result
        assert "suggestion" in result
        assert "analysisDetails" in result

    @pytest.mark.asyncio
    async def test_analyze_learning_risk_fast_fallback(self, mock_llm, mock_retriever, mock_prompt_manager, mock_report_manager):
        learning_assistant = LearningAssistant(
            llm_main=mock_llm,
            llm_fast=mock_llm,
            retriever=mock_retriever,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        agent = LearningAgent(
            llm_proposer=mock_llm,
            llm_critic=mock_llm,
            learning_assistant=learning_assistant,
            prompt_manager=mock_prompt_manager,
            report_manager=mock_report_manager
        )

        mock_llm.ainvoke.side_effect = Exception("LLM调用失败")

        result = await agent.analyze_learning_risk_fast("学生信息")

        assert result["riskLevel"] == "中风险"
        assert "进一步评估" in result["suggestion"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])