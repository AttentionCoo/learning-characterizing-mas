"""
医学OCR服务 — Medical OCR Service

对检验报告、处方等医学文档图片进行结构化文本提取。
基于 xf-xinghuo-vl-max 多模态模型，输出结构化 JSON。
"""

import asyncio
import json
import logging
import os
import threading
from typing import AsyncGenerator, List, Optional

from app.schemas.medical_image import LabReport, LabValue, PrescriptionInfo

logger = logging.getLogger(__name__)
_STREAM_DONE = object()


class MedicalOCRService:
    """医学文档OCR与结构化提取服务。

    支持：
    - 检验报告单 → LabReport 结构化数据
    - 处方 → PrescriptionInfo 列表
    - 通用医学文档 → 纯文本提取
    """

    def __init__(self, prompt_manager=None):
        self._prompt_manager = prompt_manager
        self._api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self._api_key:
            logger.warning("⚠️ 未找到 DASHSCOPE_API_KEY，医学OCR功能将不可用")

    # ----------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------

    async def extract_lab_report(
        self,
        image_base64: str,
        all_info: str = "",
    ) -> LabReport:
        """从检验报告图片中提取结构化数据。

        Args:
            image_base64: Base64编码的报告图片
            all_info: 学生画像上下文

        Returns:
            LabReport: 结构化的检验报告数据
        """
        system_prompt = """\
你是一位临床检验医学专家，正在从检验报告图片中提取结构化数据。

## 任务
从图片中逐项提取所有检验项目，包括：
- 项目名称（中文全称）
- 测定值
- 参考范围
- 单位

## 异常判断标准
- 测定值 > 参考范围上限 → abnormality_direction: "high"
- 测定值 < 参考范围下限 → abnormality_direction: "low"
- 测定值为危急值 → abnormality_direction: "critical_high" 或 "critical_low"
- 测定值在参考范围内 → is_abnormal: false

## 脑卒中相关关键指标
特别注意以下与脑卒中密切相关的指标：
- 凝血功能：PT, APTT, INR（溶栓/抗凝评估）
- 血小板计数：PLT（抗血小板治疗安全性）
- 血糖：GLU（脑卒中危险因素）
- 血脂：TC, TG, LDL-C, HDL-C（动脉粥样硬化评估）
- 电解质：Na+, K+（脑水肿管理）
- 肾功能：Cr, BUN（对比剂肾病风险）

## 输出格式
严格输出以下JSON格式（不要markdown代码块）：
{
  "report_type": "血常规/生化/凝血功能/血气分析/其他",
  "collection_time": "采样时间（如有）",
  "lab_values": [
    {"item_name": "白细胞计数", "value": "6.5", "unit": "×10⁹/L", "reference_range": "3.5-9.5", "is_abnormal": false, "abnormality_direction": ""}
  ],
  "abnormal_summary": ["异常项目及临床意义简述"],
  "overall_impression": "总体印象（50字以内）"
}

## 安全约束
- 本提取结果为AI辅助教育工具，数值可能不精确
- 如有识别不清的项目，在value中标注"识别不清"
- 不提取患者身份信息"""

        messages = self._build_single_image_message(image_base64, system_prompt, "请提取该检验报告中的所有项目。")

        raw_text = await self._call_vl_sync(messages)
        return self._parse_lab_report_json(raw_text)

    async def extract_prescription(
        self,
        image_base64: str,
    ) -> List[PrescriptionInfo]:
        """从处方图片中提取药品信息。

        Returns:
            List[PrescriptionInfo]: 药品信息列表
        """
        system_prompt = """\
你是一位临床药学专家，正在从处方图片中提取药品信息。

## 任务
逐一提取处方中的每种药品：
- 药品通用名
- 商品名（如有）
- 单次剂量
- 用药频率
- 给药途径
- 用药时长
- 备注（特殊用法说明）

## 输出格式
严格输出以下JSON数组格式（不要markdown代码块）：
[
  {"drug_name": "阿司匹林", "brand_name": "拜阿司匹林", "dosage": "100mg", "frequency": "每日一次", "route": "口服", "duration": "长期", "notes": "饭后服用"}
]

## 安全约束
- 不提取患者和医生身份信息
- 如有辨识不清的字段，标注"识别不清"
- 本结果为AI辅助教育工具，不替代药师审核"""

        messages = self._build_single_image_message(image_base64, system_prompt, "请提取该处方中的所有药品信息。")

        raw_text = await self._call_vl_sync(messages)
        return self._parse_prescription_json(raw_text)

    async def extract_text_stream(
        self,
        image_base64: str,
        document_type: str = "general",
    ) -> AsyncGenerator[dict, None]:
        """流式通用医学文档OCR（用于实时显示提取进度）。

        Args:
            image_base64: Base64编码的文档图片
            document_type: 文档类型 (lab_report/prescription/medical_record/general)
        """
        type_labels = {
            "lab_report": "检验报告",
            "prescription": "处方",
            "medical_record": "病历",
            "general": "医学文档",
        }
        label = type_labels.get(document_type, "医学文档")

        yield {
            "type": "thinking",
            "step": "MedicalOCR",
            "title": f"📄 正在识别{label}...",
            "content": f"文档类型：{label}，调用 XF-Xinghuo-VL-Max OCR识别",
        }

        system_prompt = f"你是一位医学文档识别专家。请准确识别以下{label}中的所有文字，保持原有的结构和格式。如遇模糊文字，标注[模糊]。不提取患者身份信息。"
        messages = self._build_single_image_message(image_base64, system_prompt, f"请识别该{label}中的所有文字内容。")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(target=self._run_sync_stream, args=(messages, queue, loop), daemon=True)
        t.start()

        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                yield {"type": "chunk", "content": f"OCR识别失败: {item}"}
                break
            yield {"type": "chunk", "content": item}

    # ----------------------------------------------------------
    # 内部辅助方法
    # ----------------------------------------------------------

    async def _call_vl_sync(self, messages: list) -> str:
        """同步调用VL模型获取完整输出"""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(target=self._run_sync_stream, args=(messages, queue, loop), daemon=True)
        t.start()

        parts = []
        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                raise item
            parts.append(str(item))

        return "".join(parts)

    def _run_sync_stream(self, messages: list, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        """后台线程：调用 DashScope VL API"""
        from dashscope import MultiModalConversation

        def put(item):
            asyncio.run_coroutine_threadsafe(queue.put(item), loop)

        try:
            response = MultiModalConversation.call(
                model="qwen-vl-max",
                api_key=self._api_key,
                messages=messages,
                stream=True,
                incremental_output=True,
            )
            for chunk in response:
                if chunk.status_code != 200:
                    put(Exception(f"API 错误 {chunk.status_code}: {getattr(chunk, 'message', '')}"))
                    return
                try:
                    content_list = chunk.output.choices[0].message.content
                    for item in content_list:
                        text = item.get("text", "")
                        if text:
                            put(text)
                except (AttributeError, IndexError, KeyError):
                    continue
        except Exception as e:
            put(e)
        finally:
            put(_STREAM_DONE)

    def _build_single_image_message(self, image_base64: str, system_text: str, user_text: str) -> list:
        """构建单图消息"""
        messages = []
        if system_text.strip():
            messages.append({"role": "system", "content": [{"text": system_text.strip()}]})

        url = image_base64 if image_base64.startswith("data:") else f"data:image/jpeg;base64,{image_base64}"
        user_content = [{"image": url}, {"text": user_text}]
        messages.append({"role": "user", "content": user_content})
        return messages

    @staticmethod
    def _parse_lab_report_json(text: str) -> LabReport:
        """解析检验报告JSON"""
        data = MedicalOCRService._extract_json(text)

        lab_values = []
        for item in data.get("lab_values", []):
            lab_values.append(LabValue(
                item_name=item.get("item_name", ""),
                value=item.get("value", ""),
                unit=item.get("unit", ""),
                reference_range=item.get("reference_range", ""),
                is_abnormal=item.get("is_abnormal", False),
                abnormality_direction=item.get("abnormality_direction", ""),
            ))

        return LabReport(
            report_type=data.get("report_type", ""),
            collection_time=data.get("collection_time", ""),
            lab_values=lab_values,
            abnormal_summary=data.get("abnormal_summary", []),
            overall_impression=data.get("overall_impression", ""),
        )

    @staticmethod
    def _parse_prescription_json(text: str) -> List[PrescriptionInfo]:
        """解析处方JSON数组"""
        data = MedicalOCRService._extract_json(text)
        items = data if isinstance(data, list) else data.get("medications", [])

        results = []
        for item in items:
            if isinstance(item, dict):
                results.append(PrescriptionInfo(
                    drug_name=item.get("drug_name", ""),
                    brand_name=item.get("brand_name", ""),
                    dosage=item.get("dosage", ""),
                    frequency=item.get("frequency", ""),
                    route=item.get("route", ""),
                    duration=item.get("duration", ""),
                    notes=item.get("notes", ""),
                ))
        return results

    @staticmethod
    def _extract_json(text: str) -> dict:
        """通用JSON提取（多策略容错）"""
        text = text.strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            pass
        for marker in ["```json", "```"]:
            if marker in text:
                try:
                    inner = text.split(marker)[1].split("```")[0].strip()
                    return json.loads(inner)
                except (json.JSONDecodeError, IndexError):
                    pass
        # 尝试找到最外层 {...} 或 [...]
        for sc, ec in [("{", "}"), ("[", "]")]:
            si, ei = text.find(sc), text.rfind(ec)
            if si != -1 and ei > si:
                try:
                    return json.loads(text[si:ei + 1])
                except json.JSONDecodeError:
                    pass
        logger.warning("[medical_ocr] 无法解析JSON，返回空结果")
        return {}
