"""
VisionAnalysisNode — LangGraph 医学影像分析节点

将医学多模态影像分析深度集成到多智能体推理工作流中。
影像分析结果作为"视觉证据"参与后续的检索、推理和辩论环节。

工作流位置：
  intent → vision → retrieve → reason → validate → generate_report
  (当 state 中存在 images 且非空时)

防护机制（四层）：
  Tier 0: 图片预校验 — API 调用前快速检测格式/大小/明显非医学特征
  Tier 1: 快速门控 — 增强中文 Prompt 调用 VL 模型，严格判断是否脑卒中相关
  Tier 2: 类型检测 — 检查 image_type 是否属于神经/医学影像类别
  Tier 3: 硬指标检测 — 统计医学解剖术语密度 + 非医学指标 + 对抗性检测
"""

import asyncio
import logging
import re
import threading
from typing import Dict, List, Optional, Tuple

from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.config.qwen import get_qwen_api_key, get_qwen_vision_model

logger = logging.getLogger(__name__)

# 流结束哨兵
_STREAM_DONE = object()

# ============================================================
# Tier 0: 图片预校验常量
# ============================================================

# 最大图片大小（Base64 编码后，约 10MB 原始 → ~13.3MB Base64）
_MAX_IMAGE_SIZE_BYTES = 14 * 1024 * 1024  # 14MB
# 单次最大图片数量
_MAX_IMAGE_COUNT = 5
# 支持的图片 MIME 类型
_SUPPORTED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/jpg",
    "image/bmp", "image/tiff", "image/dicom",
    "application/dicom",
}
# 明显非医学的数据URI前缀特征（日常截图的Base64开头）
_NON_MEDICAL_BASE64_PATTERNS = [
    # 注意：这些检测极其保守，仅拦截最明显的非医学内容
]

# ============================================================
# Tier 1 门控 Prompt（增强版 — 更严格的拒绝策略）
# ============================================================
_STROKE_GATE_PROMPT_CN = """你是脑卒中（中风）医学教育系统的安全守门人，职责是拦截一切与脑卒中无关的图片。

**重要原则：宁可误拦，绝不放行。不确定时，回答"否"。**

请仔细查看这张图片，然后只回答一个字："是" 或 "否"。

## 回答"是"的条件（必须严格满足）：
图片必须是以下类型之一：
- 脑部CT扫描影像（轴位/冠状/矢状位）
- 脑部MRI影像（T1WI/T2WI/FLAIR/DWI/ADC/SWI等序列）
- 脑血管造影（CTA/MRA/DSA）
- 头部/颅脑的医学扫描影像（有医疗设备标识、扫描参数等）
- 脑血管或脑组织的病理组织学切片（显微镜下图像）
- 脑卒中患者的临床体征照片（如面瘫、肢体偏瘫等，需有临床检查场景）
- 脑卒中相关的医学检验报告单（含医院名称、检验项目、参考范围）
- 脑卒中相关的影像诊断报告（含影像所见、诊断结论）
- 脑卒中相关的心电图报告（含波形和诊断文字）
- 脑血管解剖或卒中病理机制的医学图解/教学用图

## 回答"否"的情况（以下任一即拒绝）：
- 普通人物照片（自拍、大头照、证件照、全身照、合影、毕业照、家庭照等）
- 文字资料照片（数学题、试卷、作业、笔记、课本、PPT课件、合同、发票、收据等）
- 日常场景照片（动物、猫、狗、食物、餐厅、建筑、风景、旅游照、运动照等）
- 电子设备截图（手机截图、电脑桌面、软件界面、代码编辑器、聊天记录、社交媒体等）
- 二维码、条形码、表格、Excel、Word文档截图
- 非脑部的医学影像（胸部X光、肢体骨折、皮肤病变、牙科X光、眼科检查、腹部CT等）
- 任何不含医学影像特征的图片
- 纯色/近乎纯色的图片
- 模糊到无法辨认内容的图片
- 表情包、动漫、卡通、手绘非医学图画
- 任何你不确定是否属于脑卒中医学影像的图片

只回答"是"或"否"，不要解释，不要标点，不要其他任何文字。"""


class VisionAnalysisNode(BaseNode):
    """医学影像分析节点。

    防护流程：
    Tier 0 → 图片预校验（格式/大小/数量）
    Tier 1 → 增强中文门控（VL 模型直接判断，默认拒绝策略）
    Tier 2 → 影像类型检测（CT/MRI/DSA 放行）
    Tier 3 → 医学术语密度 + 非医学指标 + 对抗性检测
    """

    OUTPUT_FINDINGS_KEY = "vision_findings"
    OUTPUT_EVIDENCE_KEY = "vision_evidence"
    OUTPUT_STROKE_RELATED_KEY = "is_image_stroke_related"

    # ── 与脑卒中直接相关的影像类型 ──
    _STROKE_RELATED_IMAGE_TYPES = {
        "neuroimaging_ct", "neuroimaging_mri", "neuroimaging_angiography",
    }

    # ── 可能与脑卒中相关的影像类型（需 Tier 3 进一步检测）──
    _POTENTIALLY_STROKE_RELATED_TYPES = {
        "pathology_slide", "clinical_photo", "lab_report",
        "radiology_report", "ecg_waveform", "medical_illustration",
    }

    # ── 脑卒中关键词 ──
    _STROKE_KEYWORDS = [
        "脑卒中", "中风", "卒中", "脑梗", "脑梗死", "脑出血", "脑缺血",
        "脑血管", "缺血性", "出血性", "梗死", "梗塞", "血栓",
        "大脑中动脉", "大脑前动脉", "大脑后动脉", "基底动脉", "颈内动脉",
        "溶栓", "取栓", "抗血小板", "抗凝",
        "stroke", "cerebral", "infarction", "hemorrhage", "ischemic",
        "颅内", "脑实质", "脑室", "脑沟", "蛛网膜下腔",
    ]

    # ── 医学术语词库（用于密度检测）──
    # 非医学图片的 findings 中几乎不会出现这些词汇
    # 一个真实的医学影像会产生 5+ 个匹配
    _MEDICAL_ANATOMY_TERMS = [
        # 中文解剖/病理术语
        "脑实质", "脑室", "脑沟", "脑回", "脑干", "小脑", "大脑",
        "灰质", "白质", "基底节", "丘脑", "内囊", "外囊",
        "额叶", "颞叶", "顶叶", "枕叶", "岛叶", "海马",
        "中线", "占位", "水肿", "血肿", "缺血", "低密度", "高密度",
        "DWI", "ADC", "FLAIR", "T1", "T2", "SWI", "GRE",
        "血管", "动脉", "静脉", "狭窄", "闭塞", "灌注",
        "出血", "梗死", "钙化", "软化", "萎缩", "扩张",
        "信号", "密度", "增强", "强化", "病变", "异常",
        "左侧", "右侧", "双侧", "对称", "不对称",
        "供血区", "皮层", "髓质", "脑膜", "硬膜",
        # 英文解剖术语
        "brain", "cerebral", "cerebellar", "ventricle", "sulci",
        "gyrus", "cortex", "white matter", "gray matter", "basal ganglia",
        "thalamus", "frontal", "temporal", "parietal", "occipital",
        "midline", "edema", "hematoma", "ischemia", "infarct",
        "artery", "vein", "stenosis", "occlusion", "hemorrhage",
        # 检验/临床术语
        "血小板", "凝血", "INR", "PT", "APTT", "纤维蛋白原",
        "血糖", "血脂", "胆固醇", "甘油三酯", "肌酐",
        "白细胞", "红细胞", "血红蛋白", "血细胞比容",
        "房颤", "窦性心律", "ST段", "T波", "QT间期",
        # 报告/病理术语
        "影像所见", "诊断意见", "报告医师", "检查日期",
        "切片", "染色", "HE", "免疫组化", "细胞", "组织",
    ]

    # ── 非医学指标（命中即拦截，大幅扩展）──
    _NON_MEDICAL_INDICATORS = [
        # ===== 数学/作业/考试 =====
        "数学", "数学题", "方程式", "代数", "几何", "微积分",
        "数学作业", "考试题", "试卷", "考题", "习题",
        "选择题", "填空题", "解答题", "计算题", "证明题",
        "函数", "导数", "积分", "矩阵", "向量",
        "物理题", "化学题", "英语题", "语文题",
        # ===== 人像/自拍 =====
        "自拍", "大头照", "证件照", "肖像", "人像", "合影",
        "全家福", "毕业照", "合照", "自拍照",
        "portrait", "selfie", "headshot", "face",
        "a person", "a man", "a woman", "a boy", "a girl",
        "smiling", "posing", "looking at the camera",
        # ===== 日常场景 =====
        "猫", "狗", "宠物", "动物", "食物", "餐厅", "厨房",
        "汽车", "风景", "旅游", "运动", "游戏",
        "手机", "截图", "聊天", "二维码",
        "cat", "dog", "pet", "food", "meal", "restaurant",
        "car", "vehicle", "building", "landscape", "scenery",
        "sports", "game", "screenshot", "screenshot of",
        # ===== 电子设备/文档 =====
        "表格", "excel", "word", "ppt", "幻灯片", "电子表格",
        "合同", "发票", "收据", "笔记", "备忘录",
        "电脑桌面", "浏览器", "网页", "代码", "编程",
        "desktop", "browser", "website", "spreadsheet",
        "document", "presentation", "slide",
        # ===== 非卒中医學 =====
        "胸部", "骨折", "牙科", "眼科", "孕妇", "儿科",
        "chest", "x-ray", "xray", "fracture", "dental",
        "ophthalmology", "obstetric", "pediatric",
        "骨科", "皮肤科", "耳鼻喉", "泌尿", "消化",
        # ===== VL 模型对非医学图片的常见描述 =====
        "this is a photo of", "a person sitting", "a man in a",
        "everyday scene", "casual", "snapshot", "non-medical",
        "this image shows a", "the picture appears to be",
        "this appears to be a photo", "ordinary photo",
        "i can see a", "there is a",
        "nothing medical", "not a medical", "no medical",
        "unrelated to medicine", "not related to medical",
        # ===== 社交媒体/UI =====
        "微信", "微博", "抖音", "朋友圈", "聊天记录",
        "对话框", "通知栏", "状态栏", "导航栏",
        "点赞", "评论", "转发", "分享",
        # ===== 娱乐 =====
        "动漫", "卡通", "表情包", "搞笑", "meme",
        "anime", "cartoon", "comic", "animated",
        "celebrity", "actor", "singer", "entertainment",
        # ===== 纯色/模糊 =====
        "纯色", "纯白", "纯黑", "模糊不清",
        "too blurry", "blank image", "solid color",
    ]

    # ── 对抗性提示检测：用户试图用医学包装词绕过检测 ──
    _ADVERSARIAL_PROMPT_PATTERNS = [
        # 直接要求模型"放行"或"忽略"检测
        r"(忽略|无视|跳过|绕过).{0,10}(检测|审查|拦截|门控|限制|规则)",
        r"(不要|别|禁止).{0,10}(拒绝|拦截|检测)",
        r"(假装|假设|就当|看作).{0,10}(医学|脑卒中|CT|MRI)",
        r"(请|必须|一定要).{0,5}(放行|通过|接受|分析).{0,5}(这张|此|这个).{0,5}(图片|照片|图像)",
        r"(ignore|skip|bypass|override).{0,10}(check|gate|filter|rule|restriction)",
        # 伪装身份
        r"(我是|本人是|职务是).{0,10}(医生|教授|专家|主任|院长)",
        r"(这是一个|这是).{0,5}(测试|调试|开发).{0,5}(图片|用例|样本)",
        # 在问题中堆砌医学术语来干扰分类
        r"(脑卒中|脑梗|脑出血|脑血管|CT|MRI|DSA).{0,3}(脑卒中|脑梗|脑出血|脑血管|CT|MRI|DSA).{0,3}(脑卒中|脑梗|脑出血|脑血管|CT|MRI|DSA)",
    ]

    # ── 用户问题中的非医学关键词（问题本身暴露了真实意图）──
    _NON_MEDICAL_QUESTION_KEYWORDS = [
        "数学", "物理", "化学", "英语", "语文", "历史", "地理",
        "编程", "代码", "算法", "数据结构", "debug", "python", "java",
        "游戏", "攻略", "装备", "角色",
        "做饭", "菜谱", "食谱", "烹饪",
        "旅游", "景点", "酒店", "机票",
        "股票", "基金", "理财", "保险",
        "翻译", "这段话", "这篇文章",
        "识别图中文字", "提取文字", "OCR",
        "这是什么车", "这是什么动物", "这是什么花",
        "帮我看看这个", "帮我分析一下这个",  # 过于模糊但不直接拦截
    ]

    def __init__(
        self,
        medical_vision_service=None,
        vision_rag_bridge=None,
        llm_fast=None,
    ):
        self._vision = medical_vision_service
        self._bridge = vision_rag_bridge
        self._llm = llm_fast
        self._api_key = get_qwen_api_key(required=False)
        self._vision_model = get_qwen_vision_model()

    # ================================================================
    # 主流程
    # ================================================================

    async def run(self, state: LearningState) -> Dict:
        images = state.get("images", [])
        if not images:
            return {
                self.OUTPUT_FINDINGS_KEY: None,
                self.OUTPUT_EVIDENCE_KEY: "",
                self.OUTPUT_STROKE_RELATED_KEY: False,
            }

        question = state.get("case_text", "")
        all_info = state.get("all_info", "")
        existing_evidence = state.get("evidence", "")

        logger.info(f"[vision_node] 处理 {len(images)} 张影像 | 问题: {question[:80]}")

        # ── Tier 0: 图片预校验（API 调用前的快速检测）──
        precheck_passed, precheck_reason = self._pre_validate_images(images, question)
        if not precheck_passed:
            logger.info(f"[vision_node] ❌ Tier 0 预校验未通过: {precheck_reason}")
            return {
                self.OUTPUT_FINDINGS_KEY: None,
                self.OUTPUT_EVIDENCE_KEY: "",
                self.OUTPUT_STROKE_RELATED_KEY: False,
                "_gate_result": "rejected_by_precheck",
                "_precheck_reason": precheck_reason,
            }

        # ── 对抗性提示检测 ──
        if self._detect_adversarial_prompt(question):
            logger.info("[vision_node] ❌ 检测到对抗性提示词 → 直接拦截")
            return {
                self.OUTPUT_FINDINGS_KEY: None,
                self.OUTPUT_EVIDENCE_KEY: "",
                self.OUTPUT_STROKE_RELATED_KEY: False,
                "_gate_result": "rejected_by_adversarial_detection",
            }

        # ── Tier 1: 中文门控 ──
        gate_passed = await self._run_stroke_gate_cn(images)
        if not gate_passed:
            logger.info("[vision_node] ❌ Tier 1 门控未通过")
            return {
                self.OUTPUT_FINDINGS_KEY: None,
                self.OUTPUT_EVIDENCE_KEY: "",
                self.OUTPUT_STROKE_RELATED_KEY: False,
                "_gate_result": "rejected_by_gate",
            }

        # ── 结构化分析 ──
        findings = None
        if self._vision:
            try:
                findings = await self._vision.analyze_structured(
                    images=images, question=question, all_info=all_info,
                )
                logger.info(
                    f"[vision_node] 分析完成 | 类型: {findings.image_type} | "
                    f"发现: {len(findings.key_findings)} 条 | 置信度: {findings.confidence:.0%}"
                )
            except Exception as e:
                logger.error(f"[vision_node] 分析失败: {e}", exc_info=True)
                findings = None

        # ── Tier 2+3: 硬指标检测 ──
        is_stroke_related = self._check_stroke_relevance(findings, question)

        if not is_stroke_related:
            logger.info("[vision_node] ❌ Tier 2/3 内容检测不通过")
            return {
                self.OUTPUT_FINDINGS_KEY: findings.model_dump() if findings else None,
                self.OUTPUT_EVIDENCE_KEY: "",
                self.OUTPUT_STROKE_RELATED_KEY: False,
                "_gate_result": "rejected_by_content_check",
            }

        # ── RAG 桥接 ──
        local_docs = []
        vision_evidence_text = ""

        if findings and self._bridge:
            local_docs = self._bridge.search_local_knowledge(findings, top_k=3)
            vision_evidence_text = self._bridge.format_evidence_for_agent(
                findings=findings, local_docs=local_docs,
            )

        merged_evidence = existing_evidence
        if vision_evidence_text:
            merged_evidence = (
                f"{vision_evidence_text}\n\n---\n\n{merged_evidence}"
                if merged_evidence else vision_evidence_text
            )

        vision_questions = self._generate_vision_questions(findings) if findings else []
        merged_questions = vision_questions + list(state.get("learning_questions", []))

        logger.info(f"[vision_node] ✅ 完成 | 证据: {len(vision_evidence_text)} 字 | 本地文献: {len(local_docs)} 条")
        return {
            self.OUTPUT_FINDINGS_KEY: findings.model_dump() if findings else None,
            self.OUTPUT_EVIDENCE_KEY: vision_evidence_text,
            "evidence": merged_evidence,
            "learning_questions": merged_questions,
            self.OUTPUT_STROKE_RELATED_KEY: True,
        }

    # ================================================================
    # Tier 0: 图片预校验（API 调用前的快速检测）
    # ================================================================

    def _pre_validate_images(self, images: List[str], question: str = "") -> Tuple[bool, str]:
        """图片预校验：在调用VL模型前，快速检测明显无效/非医学的图片。

        返回 (是否通过, 拒绝原因)。
        """
        # 检查1: 图片数量限制
        if len(images) > _MAX_IMAGE_COUNT:
            return False, f"图片数量 {len(images)} 超过上限 {_MAX_IMAGE_COUNT}"

        for i, img in enumerate(images):
            # 检查2: 空图片
            if not img or not img.strip():
                return False, f"第{i+1}张图片为空"

            # 检查3: 数据URI格式校验
            if img.startswith("data:"):
                # 提取 MIME 类型
                mime_match = re.match(r"data:([^;]+);", img)
                if mime_match:
                    mime_type = mime_match.group(1).lower()
                    # 检查是否为支持的图片格式
                    if mime_type not in _SUPPORTED_MIME_TYPES:
                        logger.info(f"[vision_node] T0 不支持的MIME类型: {mime_type}")
                        # 非图片MIME直接拒绝
                        if any(non_img in mime_type for non_img in [
                            "text/", "application/pdf", "application/zip",
                            "application/json", "video/", "audio/",
                        ]):
                            return False, f"第{i+1}张图片格式不支持: {mime_type}"

                # 检查4: 图片大小限制
                img_size = len(img)
                if img_size > _MAX_IMAGE_SIZE_BYTES:
                    return False, f"第{i+1}张图片过大 ({img_size / 1024 / 1024:.1f}MB)"

                # 检查5: 极小图片（可能是恶意数据或纯色图）
                # 一个有效的Base64医学影像至少要有几百字节
                if img_size < 200:
                    return False, f"第{i+1}张图片数据过小 ({img_size} bytes)，不是有效图片"

            # 检查6: 非数据URI的纯字符串（不是Base64编码的图片）
            elif not any(img.startswith(prefix) for prefix in [
                "http://", "https://", "/9j/",  # JPEG Base64
                "iVBOR",  # PNG Base64
                "R0lGOD",  # GIF Base64
                "Qk",     # BMP Base64 (简化)
                "SUkq",   # TIFF Base64 (简化)
            ]):
                # 看起来不像Base64图片编码，检查是否是文件名/路径
                if re.match(r'^[a-zA-Z0-9_\-\./\\]+$', img[:50]) and '.' in img[:50]:
                    logger.info(f"[vision_node] T0 疑似文件路径而非图片数据: {img[:80]}")
                    # 不是硬拒绝，只是警告

        # 检查7: 用户问题预筛 — 问题中包含明显的非医学意图
        if question:
            question_lower = question.lower().strip()
            for kw in self._NON_MEDICAL_QUESTION_KEYWORDS:
                if kw in question_lower:
                    # 不直接拒绝，但记录下来；结合图片类型再判断
                    logger.info(f"[vision_node] T0 用户问题包含非医学关键词: '{kw}'")

        logger.info(f"[vision_node] ✅ T0 预校验通过 ({len(images)} 张图片)")
        return True, ""

    # ================================================================
    # 对抗性提示检测
    # ================================================================

    def _detect_adversarial_prompt(self, question: str) -> bool:
        """检测用户是否试图用对抗性提示绕过图片检测。

        返回 True 表示检测到对抗性尝试，应当直接拦截。
        """
        if not question or not question.strip():
            return False

        question_clean = question.strip()

        for pattern in self._ADVERSARIAL_PROMPT_PATTERNS:
            if re.search(pattern, question_clean, re.IGNORECASE):
                logger.warning(f"[vision_node] ⚠️ 对抗性提示检测命中: {pattern}")
                return True

        # 额外检查：问题异常短且包含强制性动词（如 "放行"、"通过"）
        if len(question_clean) < 20:
            short_adversarial = ["放行", "通过", "忽略", "跳过", "绕过", "无视"]
            if any(w in question_clean for w in short_adversarial):
                logger.warning(f"[vision_node] ⚠️ 短对抗性提示: '{question_clean}'")
                return True

        return False

    # ================================================================
    # Tier 1: 中文门控
    # ================================================================

    async def _run_stroke_gate_cn(self, images: List[str]) -> bool:
        """中文门控：对每张图片调用 VL 模型，问"是不是脑卒中医学影像？"

        所有图片都被判定为"否"才拒绝。任一图片通过即放行。
        """
        if not self._api_key:
            logger.warning("[vision_node] 无 API KEY，跳过门控（放行）")
            return True

        for i, img in enumerate(images[:3]):
            try:
                answer = await self._call_vl_gate(img)
                passed = self._parse_cn_gate(answer)

                logger.info(
                    f"[vision_node] 门控 图{i+1}/{min(len(images),3)}: "
                    f"回答='{answer[:60]}' → {'✅' if passed else '❌'}"
                )

                if passed:
                    return True  # 一张通过即放行
            except Exception as e:
                logger.warning(f"[vision_node] 门控 图{i+1} 异常: {e}")

        logger.info("[vision_node] 所有图片均未通过门控 → 拦截")
        return False

    async def _call_vl_gate(self, image: str) -> str:
        """同步调用 VL 模型执行门控（非流式，获取完整回答）"""
        messages = [
            {"role": "system", "content": [{"text": _STROKE_GATE_PROMPT_CN}]},
            {"role": "user", "content": [
                {"image": image if image.startswith("data:") else f"data:image/jpeg;base64,{image}"},
                {"text": '这张图片是否属于脑卒中相关的医学影像？只回答「是」或「否」。'},
            ]},
        ]

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(
            target=self._run_sync_vl, args=(messages, queue, loop), daemon=True
        )
        t.start()

        parts = []
        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                raise item
            parts.append(str(item))

        return "".join(parts).strip()

    def _run_sync_vl(self, messages: list, queue: asyncio.Queue, loop):
        """后台线程调用 DashScope VL API（流式，收集完整文本）"""
        from dashscope import MultiModalConversation

        def put(item):
            asyncio.run_coroutine_threadsafe(queue.put(item), loop)

        try:
            response = MultiModalConversation.call(
                model=self._vision_model,
                api_key=self._api_key,
                messages=messages,
                stream=True,
                incremental_output=True,
            )
            for chunk in response:
                if chunk.status_code != 200:
                    put(Exception(f"API {chunk.status_code}"))
                    return
                try:
                    for item in chunk.output.choices[0].message.content:
                        text = item.get("text", "")
                        if text:
                            put(text)
                except (AttributeError, IndexError, KeyError):
                    continue
        except Exception as e:
            put(e)
        finally:
            put(_STREAM_DONE)

    @staticmethod
    def _parse_cn_gate(answer: str) -> bool:
        """解析中文门控回答。

        策略（极其严格，宁可误拦绝不放过）：
        - 回答以"是"开头且不包含否定词 → 放行
        - 回答以"否"/"不"开头 → 拦截
        - 回答包含脑卒中医学强信号 且 无否定词 → 容错放行（但要求回答简短）
        - 回答过长（模型在详细描述而非简单判断）→ 检查是否包含否定
        - 其他 → 拦截
        """
        answer_clean = answer.strip().replace(" ", "").replace("\n", "").replace("\r", "")

        # 如果回答为空，拦截
        if not answer_clean:
            logger.info("[vision_node] 门控回答为空 → 拦截")
            return False

        # 明确的"是"开头（极短回答）
        if answer_clean.startswith("是") and len(answer_clean) <= 60:
            # 但不能包含后续的否定
            if not any(neg in answer_clean[:30] for neg in ["不是", "否", "不", "non", "not"]):
                return True

        # 明确的"否"或"不"开头
        if answer_clean.startswith("否") or answer_clean.startswith("不"):
            return False
        if answer_clean.startswith("NO") or answer_clean.startswith("no"):
            return False
        if answer_clean.startswith("不是"):
            return False

        # 回答较长时（模型在"解释"而非"判断"）— 更严格地处理
        if len(answer_clean) > 100:
            # 长回答中找"否"字
            if "否" in answer_clean[:20] or "不" in answer_clean[:20]:
                return False
            # 长回答中出现 "不是" 或 "不属于"
            if any(phrase in answer_clean[:100] for phrase in [
                "不是", "不属于", "不相关", "无关", "不是脑卒中",
                "not", "no ", "not a medical", "unrelated",
            ]):
                return False
            # 长回答没有明确判断 — 保守拦截
            logger.info(f"[vision_node] 门控回答过长({len(answer_clean)}字)且无明确判断 → 拦截")
            return False

        # 容错：强烈的脑卒中医学信号（仅限短回答）
        # 降低容错回答的长度阈值，避免模型长篇大论时误放行
        strong_signals = [
            "脑卒中", "脑梗", "脑出血", "脑血管",
            "CT扫描", "MRI扫描", "DSA", "CTA", "MRA",
            "NEUROIMAGING", "CEREBRAL", "STROKE", "INTRACRANIAL",
            "缺血", "梗死", "血栓", "溶栓",
        ]
        has_strong = any(s in answer_clean.upper() or s in answer_clean for s in strong_signals)
        # 严格检查：没有否定词 + 回答长度合理（< 80字）
        no_marker = not any(
            m in answer_clean[:30]
            for m in ["否", "不", "NO", "not", "non", "unrelated", "无关"]
        )

        if has_strong and no_marker and len(answer_clean) <= 80:
            logger.info(f"[vision_node] 门控容错放行: '{answer[:60]}'")
            return True

        # 默认拦截
        logger.info(f"[vision_node] 门控解析判定拦截: '{answer[:80]}'")
        return False

    # ================================================================
    # Tier 2+3: 硬指标检测
    # ================================================================

    def _check_stroke_relevance(self, findings, question: str = "") -> bool:
        """硬指标检测：医学影像产生大量解剖术语，非医学图片几乎没有。

        这个检测不依赖 LLM 判断，完全基于可量化的术语匹配。
        """
        if not findings:
            return False

        img_type = findings.image_type if hasattr(findings, 'image_type') else ""

        # ── Tier 2: 影像类型直接放行 ──
        if img_type in self._STROKE_RELATED_IMAGE_TYPES:
            logger.info(f"[vision_node] ✅ T2 类型 {img_type} 直接放行")
            return True

        # ── 构建合并文本 ──
        combined_text = " ".join([
            img_type,
            findings.anatomical_region if hasattr(findings, 'anatomical_region') else "",
            " ".join(findings.key_findings) if hasattr(findings, 'key_findings') and findings.key_findings else "",
            " ".join(ab.description for ab in (findings.abnormalities or [])),
            " ".join(findings.differential_diagnosis) if hasattr(findings, 'differential_diagnosis') and findings.differential_diagnosis else "",
            findings.raw_description if hasattr(findings, 'raw_description') else "",
            question,
        ]).lower()

        confidence = findings.confidence if hasattr(findings, 'confidence') else 0

        # ── Tier 3a: 非医学指标 → 直接拦截 ──
        for indicator in self._NON_MEDICAL_INDICATORS:
            if indicator.lower() in combined_text:
                logger.info(f"[vision_node] ❌ T3a 非医学指标 '{indicator}' → 拦截")
                return False

        # ── Tier 3b: 硬指标 — 医学解剖术语计数 ──
        medical_term_count = sum(
            1 for term in self._MEDICAL_ANATOMY_TERMS
            if term.lower() in combined_text
        )

        # ── Tier 3c: 卒中关键词计数 ──
        stroke_kw_count = sum(
            1 for kw in self._STROKE_KEYWORDS
            if kw.lower() in combined_text
        )

        logger.info(
            f"[vision_node] T3 指标: 医学解剖术语={medical_term_count}, "
            f"卒中关键词={stroke_kw_count}, 类型={img_type}, 置信度={confidence:.0%}"
        )

        # ── 硬判断逻辑 ──

        # 规则1: 医学解剖术语 >= 5 → 肯定是医学影像 → 放行
        if medical_term_count >= 5:
            logger.info(f"[vision_node] ✅ 医学解剖术语 {medical_term_count} >= 5 → 放行")
            return True

        # 规则2: 卒中关键词 >= 3 且 医学术语 >= 2 → 放行
        if stroke_kw_count >= 3 and medical_term_count >= 2:
            logger.info(f"[vision_node] ✅ 卒中关键词 {stroke_kw_count} + 术语 {medical_term_count} → 放行")
            return True

        # 规则3: 潜在相关类型 + 医学术语 >= 3 → 放行
        if img_type in self._POTENTIALLY_STROKE_RELATED_TYPES:
            if medical_term_count >= 3 and confidence > 0.3:
                logger.info(f"[vision_node] ✅ 医学类型 {img_type} + 术语 {medical_term_count} → 放行")
                return True
            logger.info(f"[vision_node] ❌ 医学类型 {img_type} 但术语不足 ({medical_term_count}) → 拦截")
            return False

        # 规则4: courseware_image → 极其严格，必须同时满足多个条件
        if img_type == "courseware_image":
            if stroke_kw_count >= 2 and medical_term_count >= 3 and confidence > 0.4:
                logger.info(f"[vision_node] ✅ courseware 满足严格条件 → 放行")
                return True
            logger.info(f"[vision_node] ❌ courseware 不满足 (卒中{stroke_kw_count}/术语{medical_term_count}/置信度{confidence:.0%}) → 拦截")
            return False

        # 规则5: 其他未知类型 → 必须医学术语 >= 4 或 (卒中关键词 >= 2 且 术语 >= 2)
        if medical_term_count >= 4:
            logger.info(f"[vision_node] ✅ 未知类型但术语 {medical_term_count} >= 4 → 放行")
            return True
        if stroke_kw_count >= 2 and medical_term_count >= 2:
            logger.info(f"[vision_node] ✅ 未知类型 卒中{stroke_kw_count} + 术语{medical_term_count} → 放行")
            return True

        # ── Tier 3d: 问题意图检测 — 问题本身暴露了非医学意图 ──
        if question:
            question_lower = question.lower().strip()
            non_medical_hits = []
            for kw in self._NON_MEDICAL_QUESTION_KEYWORDS:
                if kw in question_lower:
                    non_medical_hits.append(kw)
            if len(non_medical_hits) >= 3:
                logger.info(
                    f"[vision_node] ❌ T3d 问题意图暴露非医学目的: {non_medical_hits} → 拦截"
                )
                return False
            elif non_medical_hits:
                logger.info(
                    f"[vision_node] T3d 问题含非医学关键词: {non_medical_hits} "
                    f"(不足3个，继续评估)"
                )

        # 默认拦截
        logger.info(
            f"[vision_node] ❌ 不满足任何放行条件 "
            f"(术语{medical_term_count}/卒中{stroke_kw_count}/类型{img_type}) → 拦截"
        )
        return False

    # ================================================================
    # 辅助方法
    # ================================================================

    def _generate_vision_questions(self, findings) -> List[str]:
        if not findings:
            return []
        questions = []
        for ab in findings.abnormalities[:3]:
            if ab.description and ab.location:
                questions.append(f"{ab.location}{ab.description}的脑卒中影像学特征和临床处理")
            elif ab.description:
                questions.append(f"{ab.description}的脑卒中相关知识")
        for dd in findings.differential_diagnosis[:2]:
            if dd:
                questions.append(f"{dd}的诊断标准和影像学鉴别要点")
        for test in findings.recommended_confirmatory_tests[:2]:
            if test:
                questions.append(f"脑卒中患者{test}的适应症和临床意义")
        img_type_name = findings.image_type.replace("neuroimaging_", "").replace("_", " ").upper()
        if img_type_name:
            questions.append(f"{img_type_name}在脑卒中诊断中的价值和典型表现")
        return questions

    @staticmethod
    def has_images(state: LearningState) -> bool:
        return bool(state.get("images", []))
