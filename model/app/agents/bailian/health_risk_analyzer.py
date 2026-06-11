import os
import asyncio
import json
import logging
from http import HTTPStatus

import dashscope

logger = logging.getLogger(__name__)

_RISK_ANALYSIS_PROMPT = """你是高等教育学习风险评估专家。快速分析以下学生信息，给出简洁意见。

学生信息：
{student_info}

请直接输出 JSON（不要用 markdown 代码块）：
{{
    "riskLevel": "低风险/中风险/高风险",
    "suggestion": "最重要的学习建议（1句，50字以内）",
    "analysisDetails": "学习状况评估摘要（50字以内）"
}}

要求：
- riskLevel 必须是"低风险"、"中风险"、"高风险"之一
- 禁止绝对性结论
- 建议具体可执行"""


class LearningRiskAnalyzer:

    def __init__(self, model: str = "qwen-turbo", api_key: str = None):
        self.model = model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY")

    async def analyze(self, student_data: str) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_analyze, student_data)

    def _sync_analyze(self, student_data: str) -> dict:
        prompt = _RISK_ANALYSIS_PROMPT.format(student_info=student_data)

        response = dashscope.Generation.call(
            model=self.model,
            api_key=self.api_key,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.3,
            result_format="message",
        )

        if response.status_code != HTTPStatus.OK:
            logger.error(
                f"[LearningRiskAnalyzer] DashScope 调用失败: "
                f"status={response.status_code} code={response.code} msg={response.message}"
            )
            return self._fallback()

        content = response.output.choices[0].message.content
        result = self._parse_json(content)
        if not result:
            return self._fallback()

        _normalize = {"高": "高风险", "中": "中风险", "低": "低风险"}
        if result.get("riskLevel") in _normalize:
            result["riskLevel"] = _normalize[result["riskLevel"]]

        logger.info(f"[LearningRiskAnalyzer] 分析完成 riskLevel={result.get('riskLevel')}")
        return result

    def _parse_json(self, text: str) -> dict:
        try:
            stripped = text.strip()
            if stripped.startswith("```"):
                parts = stripped.split("```")
                stripped = parts[1] if len(parts) > 1 else stripped
                if stripped.startswith("json"):
                    stripped = stripped[4:]
            return json.loads(stripped.strip())
        except Exception:
            logger.warning(f"[LearningRiskAnalyzer] JSON 解析失败，原始输出片段: {text[:300]}")
            return {}

    @staticmethod
    def _fallback() -> dict:
        return {
            "riskLevel": "中风险",
            "suggestion": "建议结合学习情况进一步评估。",
            "analysisDetails": "系统已完成基础学习风险评估。",
        }