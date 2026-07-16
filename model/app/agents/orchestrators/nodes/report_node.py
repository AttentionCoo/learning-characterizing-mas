import logging
import json
from typing import Dict
from langchain_core.messages import HumanMessage, SystemMessage
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_PROPOSAL_CHARS, MAX_CRITIQUE_CHARS
from app.agents.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)


class ReportNode(BaseNode):

    def __init__(self, llm_proposer, report_manager):
        self.llm_proposer = llm_proposer
        self.report_manager = report_manager

    async def run(self, state: LearningState) -> Dict:
        logger.info(f"[report] 开始执行报告生成节点")
        logger.info(f"[report] 报告模式: {state['report_mode']}")
        logger.info(f"[report] 意图类型: {state.get('intent_type', 'N/A')}")
        logger.info(f"[report] 提案长度: {len(state['proposal']) if state['proposal'] else 0}")
        logger.info(f"[report] 批判长度: {len(state['critique']) if state['critique'] else 0}")
        logger.info(f"[report] 证据长度: {len(state['evidence']) if state['evidence'] else 0}")
        logger.info(f"[report] 校验状态: {state['validation_passed']}")
        logger.info(f"[report] 反思次数: {state['reflection_count']}")

        report_mode = state.get('report_mode', 'emergency')
        logger.info(f"[report] 使用模板: {report_mode}")

        if state['user_questions']:
            logger.info(f"[report] 存在用户问题，直接返回提案")
            return {"report": state['proposal']}

        # ── code_assist 模式：直接用 LLM 生成代码辅助内容 ──
        if report_mode == "code_assist":
            return await self._generate_code_assist(state)

        if not state['proposal']:
            logger.warning(f"[report] 没有提案，生成默认报告")
            default_report = f"""## 学习分析报告

### 学生情况
{state['case_text']}

### 分析结果
系统已完成初步分析，但未能生成具体的学习建议。

### 可能原因
- 需要进一步的学习信息
- 建议提供更详细的学习背景

### 建议
请提供更详细的学习信息，以便系统进行个性化分析。
"""
            return {"report": default_report}

        context_str = (
            json.dumps(state['context'], ensure_ascii=False, indent=2)
            if isinstance(state['context'], dict) else str(state['context'])
        )

        logger.info(f"[report] 上下文长度: {len(context_str)}")

        warning_text = ""
        if not state['validation_passed'] and state['validation_feedback']:
            warning_text = f"\n\n⚠️ **质量警告**: {state['validation_feedback']}\n\n"
            logger.info(f"[report] 添加质量警告到报告")

        motivational_text = ""
        motivational_feedback = state.get('motivational_feedback', '')
        if motivational_feedback:
            motivational_text = f"\n\n💡 **学习激励**: {motivational_feedback}\n\n"
            logger.info(f"[report] 添加学习激励反馈到报告")

        report_template = self.report_manager.get_template(report_mode)

        if not report_template:
            logger.warning(f"[report] 模板为空: report_mode={report_mode}，使用 emergency 模板")
            report_template = self.report_manager.get_template("emergency")

        logger.info(f"[report] 模板内容前100字: {report_template[:100]}")

        try:
            prompt_text = report_template.format(
                context=context_str,
                all_info=state['all_info'] or "无历史记录",
                evidence=state['evidence'] or "未检索到相关证据",
                proposal=truncate_text(state['proposal'], MAX_PROPOSAL_CHARS) or "无",
                critique=truncate_text(state['critique'], MAX_CRITIQUE_CHARS) or "无批判意见",
            )
        except KeyError as e:
            logger.error(f"[report] 模板格式化失败！模板中包含非法占位符: {e}，report_mode={report_mode}")
            logger.error(f"[report] 模板内容: {report_template[:500]}")
            emergency_template = self.report_manager.get_template("emergency")
            prompt_text = emergency_template.format(
                context=context_str,
                all_info=state['all_info'] or "无历史记录",
                evidence=state['evidence'] or "未检索到相关证据",
                proposal=truncate_text(state['proposal'], MAX_PROPOSAL_CHARS) or "无",
                critique=truncate_text(state['critique'], MAX_CRITIQUE_CHARS) or "无批判意见",
            )

        if warning_text:
            prompt_text = prompt_text.replace("### 个性化建议", f"### 质量警告{warning_text}### 个性化建议")

        if motivational_text:
            prompt_text = prompt_text.replace("### 个性化建议", f"### 学习激励{motivational_text}### 个性化建议")

        logger.info(f"[report] Prompt长度: {len(prompt_text)}")
        logger.info(f"[report] 开始生成报告")

        template_config = self.report_manager.get_template_config(report_mode)
        role_text = template_config.get("role", "") if template_config else ""

        human_content = prompt_text
        if role_text:
            human_content = f"{role_text}\n\n{prompt_text}"

        logger.info(f"[report] role_text长度: {len(role_text) if role_text else 0}")
        logger.info(f"[report] HumanMessage前100字: {human_content[:100]}")

        messages = [
            SystemMessage(content=self.report_manager.system_role),
            HumanMessage(content=human_content),
        ]
        report = ""
        chunk_count = 0
        try:
            async for chunk in self.llm_proposer.astream(messages):
                c = chunk.content if hasattr(chunk, "content") else str(chunk)
                report += c
                chunk_count += 1
        except Exception as e:
            logger.error(f"[report] 报告生成失败: {type(e).__name__} - {str(e)}")
            report = f"## 学习分析报告\n\n{state['proposal']}\n\n{warning_text}"

        logger.info(f"[report] 报告生成完成，长度: {len(report)}, 块数: {chunk_count}")
        return {"report": report}

    async def _generate_code_assist(self, state: LearningState) -> Dict:
        """code_assist 模式：不依赖 proposal/evidence/critique，
        直接用 LLM 流式生成代码补全/诊断/优化/讲解内容。

        流式调用优先，若流式返回空内容则自动降级为非流式调用。
        """
        case_text = state.get("case_text", "")
        logger.info(f"[report][code_assist] case_text 长度: {len(case_text)}")

        code_assist_system = (
            "你是一名专业的 Python 编程导师，专注于医学数据分析领域。\n"
            "请根据用户的代码和诉求，提供代码补全、错误诊断、优化建议或代码讲解。\n"
            "\n"
            "【核心要求：必须按以下结构输出，每部分都要有实际内容】\n"
            "\n"
            "## 优化后的代码示例\n"
            "（给出完整的、可直接运行的 Python 代码，用 ```python 围栏格式包裹。\n"
            " 补全场景：补全用户未完成的代码段；\n"
            " 诊断场景：修复错误后的完整代码；\n"
            " 优化场景：优化后的完整代码；\n"
            " 讲解场景：被讲解的代码片段。\n"
            " 即使只有一行改动，也要输出完整代码，不要省略！）\n"
            "\n"
            "## 改动说明\n"
            "（逐条列出改动位置、原因和效果；错误诊断场景需先指出错误根因）\n"
            "\n"
            "## 相关知识点\n"
            "（涉及的语法特性、库用法或医学数据处理惯例）\n"
            "\n"
            "## 进阶建议\n"
            "（性能、可读性或健壮性方面可进一步优化的方向）\n"
            "\n"
            "其他要求：\n"
            "- 用中文回答\n"
            "- 解释清晰、步骤分明\n"
            "- 涉及医学统计（如 pandas/numpy/scipy/scikit-learn）时，结合领域知识说明\n"
            "- 代码块必须完整可运行，不要用 ... 或 # 省略 代替实际代码"
        )

        messages = [
            SystemMessage(content=code_assist_system),
            HumanMessage(content=case_text),
        ]

        report = ""
        chunk_count = 0
        stream_error = None

        # ── 第一轮：流式调用 ──
        try:
            async for chunk in self.llm_proposer.astream(messages):
                chunk_count += 1
                # 安全提取 chunk 内容：兼容 content 为 None / "" / list 等情况
                if hasattr(chunk, "content"):
                    c = chunk.content
                    if c is None:
                        c = ""
                    elif not isinstance(c, str):
                        # 某些模型 content 可能为 list[dict]，尝试转字符串
                        try:
                            c = str(c) if c else ""
                        except Exception:
                            c = ""
                else:
                    c = str(chunk) if chunk else ""
                report += c
        except Exception as e:
            stream_error = e
            logger.error(
                f"[report][code_assist] 流式生成失败: {type(e).__name__} - {str(e)}"
            )

        logger.info(
            f"[report][code_assist] 流式完成，长度: {len(report)}, "
            f"块数: {chunk_count}, 有效内容: {bool(report.strip())}"
        )

        # ── 第二轮：流式为空时降级为非流式调用 ──
        if not report.strip():
            logger.warning(
                f"[report][code_assist] 流式返回空内容 "
                f"(stream_error={type(stream_error).__name__ if stream_error else '无异常'})，"
                f"降级为非流式调用"
            )
            try:
                response = await self.llm_proposer.ainvoke(messages)
                if hasattr(response, "content"):
                    c = response.content
                    if c is None:
                        c = ""
                    elif not isinstance(c, str):
                        try:
                            c = str(c) if c else ""
                        except Exception:
                            c = ""
                    report = c
                else:
                    report = str(response) if response else ""
                logger.info(
                    f"[report][code_assist] 非流式降级完成，长度: {len(report)}, "
                    f"有效内容: {bool(report.strip())}"
                )
            except Exception as e:
                logger.error(
                    f"[report][code_assist] 非流式降级也失败: {type(e).__name__} - {str(e)}"
                )
                report = (
                    f"代码辅助生成失败：LLM 服务当前不可用。\n\n"
                    f"流式调用{f'报错: {stream_error}' if stream_error else '返回空内容'}，"
                    f"非流式降级报错: {type(e).__name__}。\n"
                    f"请检查模型服务日志或稍后重试。"
                )

        if report.strip():
            logger.info(f"[report][code_assist] 内容预览:\n{report[:500]}")
            if "```python" in report or "```" in report:
                logger.info(f"[report][code_assist] 包含代码块: 是")
            else:
                logger.warning(f"[report][code_assist] 包含代码块: 否")
        else:
            logger.error(
                f"[report][code_assist] 流式+非流式均未返回有效内容，"
                f"将返回空报告（前端将提示用户）"
            )

        return {"report": report}