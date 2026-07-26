import logging
import json
import re
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

    _CODE_ASSIST_TYPE_PATTERN = re.compile(r"【辅助功能代码】\s*(complete|diagnose|optimize|explain)")
    _CODE_ASSIST_SYSTEMS = {
        "complete": """你是一名专业的 Python 开发助手，当前唯一任务是代码补全。
只补齐用户明确缺失的函数、分支或流程，保持已有结构、接口和行为，不执行错误诊断、性能优化或教学讲解。
输出结构：## 补全后的完整代码、## 补全内容。代码必须放在 ```python 围栏中，完整可运行，不得使用省略号代替实现。用中文回答。""",
        "diagnose": """你是一名专业的 Python 调试助手，当前唯一任务是错误诊断。
只定位报错或异常行为的根因并修复，不扩展无关功能，也不附带泛化的优化和教学内容。
输出结构：## 错误根因、## 修复后的完整代码、## 验证方法。代码必须放在 ```python 围栏中，完整可运行。用中文回答。""",
        "optimize": """你是一名专业的 Python 代码优化助手，当前唯一任务是代码优化。
必须保持原有功能、接口与输出语义不变，只优化性能、可读性或健壮性，不新增业务功能，不转为错误诊断或逐行教学。
输出结构：## 优化点、## 优化后的完整代码、## 效果说明。代码必须放在 ```python 围栏中，完整可运行。用中文回答。""",
        "explain": """你是一名专业的 Python 编程讲师，当前唯一任务是代码讲解。
只解释用户现有代码的整体结构、执行流程、关键语句和输入输出，不改写代码，不提供补全、修复或优化后的版本。
输出结构：## 整体作用、## 执行流程、## 关键代码、## 输入与输出。可引用必要的短代码片段。用中文回答。""",
    }

    @classmethod
    def _resolve_code_assist_type(cls, case_text: str):
        match = cls._CODE_ASSIST_TYPE_PATTERN.search(case_text or "")
        return match.group(1) if match else None

    @classmethod
    def _build_code_assist_retry_system(cls, assist_type: str) -> str:
        return (
            cls._CODE_ASSIST_SYSTEMS[assist_type]
            + "\n你上一次没有按要求返回完整 Python 代码块。请严格按当前唯一功能重新回答，"
              "必须包含完整的 ```python ... ``` 代码块。"
        )

    async def _generate_code_assist(self, state: LearningState) -> Dict:
        """code_assist 模式：不依赖 proposal/evidence/critique，
        直接用 LLM 生成代码补全/诊断/优化/讲解内容。

        调用策略（三层降级）：
        1. 非流式调用（避免 LLM 反问用户的无用内容被流式推送到前端）
        2. 非流式为空 → 降级重试
        3. 内容不含代码块 → 强化提示词流式重试
           （流式重试可让 on_chat_model_stream 事件把内容推送到前端）
        """
        case_text = state.get("case_text", "")
        assist_type = self._resolve_code_assist_type(case_text)
        if not assist_type:
            logger.warning("[report][code_assist] 缺少辅助功能代码，拒绝调用模型")
            return {
                "report": "请先选择代码补全、错误诊断、优化建议或代码讲解中的一项功能。"
            }
        requires_code_block = assist_type != "explain"
        logger.info(
            f"[report][code_assist] case_text 长度: {len(case_text)}, assist_type={assist_type}"
        )

        messages = [
            SystemMessage(content=self._CODE_ASSIST_SYSTEMS[assist_type]),
            HumanMessage(content=case_text),
        ]

        # ── 第一轮：非流式调用 ──
        # 注意：首次使用非流式而不使用流式，防止 LLM 反问用户的无用内容
        # 被流式发送到前端（一旦流式发送就无法撤回）。
        # 如果首次就产出代码块 → on_chain_end 会将完整报告发送给前端。
        # 如果首次无代码块 → 触发强化重试（流式），重试内容正常流式推送。
        report, stream_error = await self._try_generate(messages, use_stream=False)

        # ── 第二轮：内容质量校验 ──
        # 即使内容非空，如果 LLM 在"反问用户"而非给出代码，也需要重试
        has_code_block = bool(report.strip()) and (
            "```python" in report or "```" in report
        )
        if report.strip():
            logger.info(f"[report][code_assist] 内容预览:\n{report[:500]}")
            if has_code_block:
                logger.info(f"[report][code_assist] 包含代码块: 是 ✓")
            elif requires_code_block:
                logger.warning(
                    f"[report][code_assist] 包含代码块: 否，"
                    f"疑似 LLM 反问用户或未按格式输出，触发强化重试"
                )
            else:
                logger.info("[report][code_assist] 讲解模式无需强制返回代码块")

        # ── 第三轮：内容不含代码块时，用强化提示词重试 ──
        # 只在用户确实提供了代码时才触发重试，避免用户没写代码时白白浪费 LLM 调用
        user_has_code = case_text and ("```" in case_text)
        if report.strip() and not has_code_block and requires_code_block:
            if user_has_code:
                logger.info(
                    f"[report][code_assist] 用户提供了代码但 LLM 未输出代码块，触发强化重试"
                )
                retry_messages = [
                    SystemMessage(content=self._build_code_assist_retry_system(assist_type)),
                    HumanMessage(
                        content=(
                            f"用户原始输入：\n{case_text}\n\n"
                            f"你上一次的回复（不包含代码块，请重新回答）：\n{report[:300]}"
                        )
                    ),
                ]
                retry_report, _ = await self._try_generate(retry_messages, use_stream=True)
                if retry_report.strip():
                    retry_has_code = "```python" in retry_report or "```" in retry_report
                    logger.info(
                        f"[report][code_assist] 重试完成，长度: {len(retry_report)}, "
                        f"包含代码块: {'是' if retry_has_code else '否'}"
                    )
                    if retry_has_code:
                        report = retry_report
                        has_code_block = True
            else:
                logger.info(
                    f"[report][code_assist] 用户未提供代码，LLM 正常询问，跳过重试"
                )

        # ── 最终兜底 ──
        if not report.strip():
            logger.error(
                f"[report][code_assist] 所有尝试均未返回有效内容"
            )
            report = (
                "代码辅助生成失败：LLM 服务当前不可用。\n\n"
                "请检查模型服务日志或稍后重试。"
            )
        elif not has_code_block and user_has_code and requires_code_block:
            # 只有用户提供了代码但 LLM 没输出代码块时才追加提示
            logger.warning(
                f"[report][code_assist] 用户提供了代码但 LLM 未输出代码块，"
                f"返回原始内容并附加提示"
            )
            report = (
                f"{report}\n\n"
                f"---\n"
                f"⚠️ **注意**：AI 本次未生成代码示例。请尝试：\n"
                f"1. 在编辑器中多写一些代码，让 AI 有更多上下文\n"
                f"2. 在「诉求」框中更具体地描述你希望 AI 帮你做什么\n"
                f"3. 如果问题持续，请检查模型服务配置"
            )

        return {"report": report}

    async def _try_generate(
        self, messages: list, use_stream: bool = True
    ) -> tuple:
        """统一的 LLM 生成调用，返回 (报告文本, 异常对象)。

        先尝试流式，失败/为空时自动降级为非流式。
        """
        report = ""
        chunk_count = 0
        stream_error = None

        # ── 流式调用 ──
        if use_stream:
            try:
                async for chunk in self.llm_proposer.astream(messages):
                    chunk_count += 1
                    if hasattr(chunk, "content"):
                        c = chunk.content
                        if c is None:
                            c = ""
                        elif not isinstance(c, str):
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
                    f"[report][code_assist] 流式生成失败: "
                    f"{type(e).__name__} - {str(e)}"
                )

            logger.info(
                f"[report][code_assist] 流式完成，长度: {len(report)}, "
                f"块数: {chunk_count}, 有效内容: {bool(report.strip())}"
            )

        # ── 非流式降级 ──
        if not report.strip():
            if use_stream:
                logger.warning(
                    f"[report][code_assist] 流式返回空内容"
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
                    f"[report][code_assist] 非流式完成，长度: {len(report)}, "
                    f"有效内容: {bool(report.strip())}"
                )
            except Exception as e:
                logger.error(
                    f"[report][code_assist] 非流式调用失败: "
                    f"{type(e).__name__} - {str(e)}"
                )
                report = (
                    f"代码辅助生成失败：LLM 服务当前不可用。\n\n"
                    f"流式调用{f'报错: {stream_error}' if stream_error else '返回空内容'}，"
                    f"非流式降级报错: {type(e).__name__}。\n"
                    f"请检查模型服务日志或稍后重试。"
                )

        return report, stream_error
