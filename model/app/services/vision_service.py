
import asyncio
import base64
import json
import logging
import os
import threading
from typing import AsyncGenerator, List

import websocket

from app.utils.xfyun_auth import assemble_auth_url, get_xfyun_credentials

logger = logging.getLogger(__name__)

_KEYWORDS_REPORT = ["课件", "笔记", "教材", "习题", "作业", "考试", "成绩", "报告", "学习资料"]
_KEYWORDS_DRUG = ["代码", "编程", "程序", "算法", "截图", "界面", "软件"]

_STREAM_DONE = object()

# 讯飞图片理解 WebSocket 接口；domain: general=基础版, imagev3=高级版
_IMAGE_WS_URL = "wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image"
_IMAGE_DOMAIN = os.getenv("XFYUN_IMAGE_DOMAIN", "general")
_MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 接口限制单图 4M


class VisionAnalysisService:

    def __init__(self, prompt_manager):
        self.prompt_manager = prompt_manager
        self._app_id, self._api_key, self._api_secret = get_xfyun_credentials()
        if not all([self._app_id, self._api_key, self._api_secret]):
            logger.warning("⚠️ 未配置 XFYUN_APP_ID/XFYUN_API_KEY/XFYUN_API_SECRET，影像分析功能将不可用")

    def _detect_image_type(self, question: str) -> str:
        q = question.lower()
        if any(kw in q for kw in _KEYWORDS_REPORT):
            return "image_report"
        if any(kw in q for kw in _KEYWORDS_DRUG):
            return "image_drug"
        return "image_general"

    @staticmethod
    def _normalize_image(img: str) -> str:
        """统一为纯 base64（去掉 data URL 前缀）。"""
        if img.startswith("data:"):
            _, _, tail = img.partition(",")
            return tail
        return img

    def _build_request(self, image_b64: str, user_text: str) -> dict:
        """构造单张图片的请求体：图片必须是 text 数组的首个元素。"""
        return {
            "header": {"app_id": self._app_id},
            "parameter": {
                "chat": {
                    "domain": _IMAGE_DOMAIN,
                    "temperature": 0.5,
                    "max_tokens": 4096,
                }
            },
            "payload": {
                "message": {
                    "text": [
                        {"role": "user", "content": image_b64, "content_type": "image"},
                        {"role": "user", "content": user_text, "content_type": "text"},
                    ]
                }
            },
        }

    def _stream_one_image(self, image_b64: str, user_text: str, put) -> None:
        """同步调用一张图片的理解接口，流式片段经 put 回传。"""
        raw = base64.b64decode(image_b64, validate=False)
        if len(raw) > _MAX_IMAGE_BYTES:
            put(Exception("图片超过 4MB 限制，请压缩后重试"))
            return

        url = assemble_auth_url(_IMAGE_WS_URL, self._api_key, self._api_secret, method="GET")
        ws = websocket.create_connection(url, timeout=60)
        try:
            ws.send(json.dumps(self._build_request(image_b64, user_text), ensure_ascii=False))
            while True:
                frame = json.loads(ws.recv())
                header = frame.get("header", {})
                if header.get("code", -1) != 0:
                    put(Exception(f"讯飞图片理解错误 {header.get('code')}: {header.get('message', '')}"))
                    return
                choices = frame.get("payload", {}).get("choices", {})
                for item in choices.get("text", []):
                    content = item.get("content", "")
                    if content:
                        put(content)
                if choices.get("status") == 2 or header.get("status") == 2:
                    return
        finally:
            ws.close()

    def _run_sync_stream(self, images: List[str], user_text: str,
                         queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        def put(item):
            asyncio.run_coroutine_threadsafe(queue.put(item), loop)

        try:
            # 讯飞图片理解单次会话只接受一张图片，多图逐张分析后拼接
            for idx, img in enumerate(images):
                if len(images) > 1:
                    put(f"\n\n### 第 {idx + 1} 张图片分析\n\n")
                self._stream_one_image(self._normalize_image(img), user_text, put)
        except Exception as e:
            put(e)
        finally:
            put(_STREAM_DONE)

    async def analyze_stream(
        self, images: List[str], question: str, all_info: str
    ) -> AsyncGenerator[dict, None]:
        image_type = self._detect_image_type(question)
        logger.info(f"影像分析意图: {image_type}，图片数量: {len(images)}")

        if not all([self._app_id, self._api_key, self._api_secret]):
            yield {"type": "chunk", "content": "影像分析服务未配置（缺少讯飞三元组凭证），请联系管理员。"}
            return

        if image_type == "image_report":
            system_text = self.prompt_manager.get("image_report_system") or _DEFAULT_REPORT_SYSTEM
            user_prefix = "请分析以下学习资料图片。"
        elif image_type == "image_drug":
            system_text = self.prompt_manager.get("image_drug_system") or _DEFAULT_DRUG_SYSTEM
            user_prefix = "请分析以下代码或学习资源截图。"
        else:
            system_text = self.prompt_manager.get("image_general_system") or _DEFAULT_GENERAL_SYSTEM
            user_prefix = "请分析以下图片。"

        yield {
            "type": "thinking",
            "step": "Vision",
            "title": "🔍 正在分析图片...",
            "content": f"意图类型：{image_type}，共 {len(images)} 张图片，调用讯飞星火图片理解模型",
        }

        # 图片理解接口无独立 system 角色，把系统提示合并进用户文本
        student_context = f"学生信息：{all_info.strip()}" if all_info and all_info.strip() else ""
        user_text = "\n\n".join(filter(None, [system_text.strip(), student_context, user_prefix, question])).strip()

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(
            target=self._run_sync_stream,
            args=(images, user_text, queue, loop),
            daemon=True,
        )
        t.start()

        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                logger.error(f"图片理解模型调用失败: {item}", exc_info=False)
                yield {"type": "chunk", "content": f"图片分析失败，请稍后重试。（{type(item).__name__}: {item}）"}
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
