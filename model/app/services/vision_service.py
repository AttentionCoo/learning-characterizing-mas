import asyncio
import base64
import logging
import os
import threading
from typing import AsyncGenerator, List

from app.config.qwen import get_qwen_api_key, get_qwen_vision_model

logger = logging.getLogger(__name__)

_KEYWORDS_REPORT = ["课件", "笔记", "教材", "习题", "作业", "考试", "成绩", "报告", "学习资料"]
_KEYWORDS_DRUG = ["代码", "编程", "程序", "算法", "截图", "界面", "软件"]

_STREAM_DONE = object()
_MAX_IMAGE_BYTES = int(os.getenv("QWEN_VISION_MAX_IMAGE_BYTES", str(10 * 1024 * 1024)))


class VisionAnalysisService:

    def __init__(self, prompt_manager):
        self.prompt_manager = prompt_manager
        self._api_key = get_qwen_api_key(required=False)
        self._model = get_qwen_vision_model()
        if not self._api_key:
            logger.warning(
                "⚠️ 未配置 QWEN_API_KEY/DASHSCOPE_API_KEY，影像分析功能将不可用"
            )

    def _detect_image_type(self, question: str) -> str:
        q = question.lower()
        if any(keyword in q for keyword in _KEYWORDS_REPORT):
            return "image_report"
        if any(keyword in q for keyword in _KEYWORDS_DRUG):
            return "image_drug"
        return "image_general"

    @staticmethod
    def _normalize_image(image: str) -> str:
        if image.startswith("data:"):
            return image
        return f"data:image/jpeg;base64,{image}"

    @staticmethod
    def _validate_image(image: str) -> None:
        payload = image.partition(",")[2] if image.startswith("data:") else image
        raw = base64.b64decode(payload, validate=False)
        if len(raw) > _MAX_IMAGE_BYTES:
            max_mb = _MAX_IMAGE_BYTES // (1024 * 1024)
            raise ValueError(f"图片超过 {max_mb}MB 限制，请压缩后重试")

    def _build_messages(
        self,
        images: List[str],
        user_text: str,
        system_text: str,
    ) -> list:
        messages = []
        if system_text.strip():
            messages.append({
                "role": "system",
                "content": [{"text": system_text.strip()}],
            })

        user_content = []
        for image in images:
            self._validate_image(image)
            user_content.append({"image": self._normalize_image(image)})
        user_content.append({"text": user_text})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _run_sync_stream(
        self,
        messages: list,
        queue: asyncio.Queue,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        from dashscope import MultiModalConversation

        def put(item):
            asyncio.run_coroutine_threadsafe(queue.put(item), loop)

        try:
            response = MultiModalConversation.call(
                model=self._model,
                api_key=self._api_key,
                messages=messages,
                stream=True,
                incremental_output=True,
            )
            for chunk in response:
                if chunk.status_code != 200:
                    put(Exception(
                        f"Qwen VL API 错误 {chunk.status_code}: "
                        f"{getattr(chunk, 'message', '')}"
                    ))
                    return
                try:
                    content = chunk.output.choices[0].message.content
                    for item in content:
                        text = item.get("text", "")
                        if text:
                            put(text)
                except (AttributeError, IndexError, KeyError, TypeError):
                    continue
        except Exception as exc:
            put(exc)
        finally:
            put(_STREAM_DONE)

    async def analyze_stream(
        self,
        images: List[str],
        question: str,
        all_info: str,
    ) -> AsyncGenerator[dict, None]:
        image_type = self._detect_image_type(question)
        logger.info(f"影像分析意图: {image_type}，图片数量: {len(images)}")

        if not self._api_key:
            yield {
                "type": "chunk",
                "content": "影像分析服务未配置（缺少 Qwen API Key），请联系管理员。",
            }
            return

        if image_type == "image_report":
            system_text = (
                self.prompt_manager.get("image_report_system")
                or _DEFAULT_REPORT_SYSTEM
            )
            user_prefix = "请分析以下学习资料图片。"
        elif image_type == "image_drug":
            system_text = (
                self.prompt_manager.get("image_drug_system")
                or _DEFAULT_DRUG_SYSTEM
            )
            user_prefix = "请分析以下代码或学习资源截图。"
        else:
            system_text = (
                self.prompt_manager.get("image_general_system")
                or _DEFAULT_GENERAL_SYSTEM
            )
            user_prefix = "请分析以下图片。"

        yield {
            "type": "thinking",
            "step": "Vision",
            "title": "🔍 正在分析图片...",
            "content": (
                f"意图类型：{image_type}，共 {len(images)} 张图片，"
                f"调用 {self._model} 图片理解模型"
            ),
        }

        student_context = (
            f"学生信息：{all_info.strip()}"
            if all_info and all_info.strip()
            else ""
        )
        user_text = "\n\n".join(
            filter(None, [student_context, user_prefix, question])
        ).strip()
        messages = self._build_messages(images, user_text, system_text)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        thread = threading.Thread(
            target=self._run_sync_stream,
            args=(messages, queue, loop),
            daemon=True,
        )
        thread.start()

        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                logger.error(f"Qwen 图片理解模型调用失败: {item}", exc_info=False)
                yield {
                    "type": "chunk",
                    "content": (
                        "图片分析失败，请稍后重试。"
                        f"（{type(item).__name__}: {item}）"
                    ),
                }
                break
            yield {"type": "chunk", "content": item}


_DEFAULT_REPORT_SYSTEM = """\
你是一位高等教育教学资料分析专家，正在查看学生上传的学习资料图片。

## 任务
请按以下步骤分析这张学习资料图片：

### 第一步：内容识别
准确识别图片上的所有文字和结构信息，以结构化形式列出：
- 资料类型（课件/笔记/教材/习题等）
- 涉及课程和知识点
- 关键内容摘要

### 第二步：内容解读
对识别出的内容进行解读：
- 知识点覆盖范围
- 难度级别评估
- 与学生当前学习阶段的匹配度

### 第三步：学习建议
结合学生已知学习信息（如有），给出学习建议和推荐补充资料

## 安全约束
- 禁止给出绝对性结论，使用"建议""可能""推荐"等措辞
- 如果图片模糊无法识别，明确告知用户"""

_DEFAULT_DRUG_SYSTEM = """\
你是一位学习资源分析专家，正在查看学生上传的学习资源截图。

## 任务
请按以下步骤分析这张资源截图：

### 第一步：基础识别
从截图中识别：资源类型、课程名称、知识点范围、难度级别

### 第二步：资源评估
基于识别出的信息，提供：资源质量评估、适用学习阶段、推荐使用方式

### 第三步：补充建议
推荐与该资源搭配的其他学习材料

## 安全约束
- 如果无法从截图中准确识别资源，明确告知用户
- 禁止建议学生跳过必要的学习步骤"""

_DEFAULT_GENERAL_SYSTEM = """\
你是一位高等教育个性化学习顾问，请仔细分析用户上传的图片，结合学生学习信息给出专业回答。

## 安全约束
- 禁止给出绝对性结论，使用"建议""可能""推荐"等措辞
- 建议学生在老师或辅导员指导下进一步评估"""
