"""
VisionAnalysisNode — LangGraph 医学影像分析节点

将医学多模态影像分析深度集成到多智能体推理工作流中。
影像分析结果作为"视觉证据"参与后续的检索、推理和辩论环节。

工作流位置：
  intent → vision → retrieve → reason → validate → generate_report
  (当 state 中存在 images 且非空时)

防护机制（三层）：
  Tier 1: 快速门控 — 调用 VL 模型直接询问"是否与脑卒中相关"，非则直接拒绝
  Tier 2: 类型检测 — 检查 image_type 是否属于神经/医学影像类别
  Tier 3: 内容检测 — 检查 findings 文本是否包含卒中关键词或医学发现
"""

import asyncio
import logging
import os
import threading
from typing import Dict, List, Optional

from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode

logger = logging.getLogger(__name__)

# 流结束哨兵
_STREAM_DONE = object()

# Tier 1 快速门控 Prompt — 硬判断图片是否与脑卒中医学相关
_STROKE_GATE_PROMPT = """You are a strict medical image gatekeeper for a stroke (脑卒中) education system. Look at this image and answer exactly ONE word: YES or NO.

Answer YES only if the image is a MEDICAL image related to stroke medicine:
- Brain CT, brain MRI, cerebral angiography (CTA/MRA/DSA)
- Medical scans of the head/brain showing cross-sections
- Pathology slides of cerebrovascular tissue
- Clinical photos of stroke signs (facial asymmetry, limb weakness)
- Medical reports/lab results for stroke diagnosis (blood tests, coagulation)
- ECGs for atrial fibrillation / cardiac sources of embolism
- Medical illustrations of brain vasculature or stroke mechanisms

Answer NO for ANYTHING else, especially:
- Photos of people (selfies, portraits, group photos, ID photos)
- Text documents, math problems, homework, exam papers, books
- Screenshots of phones/computers, social media, chat apps
- Animals, pets, scenery, buildings, food, objects
- Non-brain medical images (chest X-ray, bone fracture, skin rash, dental, etc.)
- Any image that is NOT a medical image of the brain/head/vasculature

Output ONLY the word YES or NO. No explanation, no punctuation, no other text."""


class VisionAnalysisNode(BaseNode):
    """医学影像分析节点。

    职责：
    1. Tier 1 快速门控：VL 模型直接判断图片是否脑卒中相关
    2. 调用 MedicalVisionService 进行结构化分析
    3. 通过 VisionRAGBridge 将影像发现转化为 PubMed + 本地知识库检索
    4. 将影像分析结果和循证证据写入 state，供后续节点使用

    节点输出字段：
    - vision_findings: 结构化的 MedicalImageFindings（dict）
    - vision_evidence: 格式化的影像分析+证据文本（str）
    - evidence: 在原有 evidence 基础上追加视觉证据
    - is_image_stroke_related: 图片是否与脑卒中相关（bool）
    """

    # 节点输出键名（用于 LangGraph state 更新）
    OUTPUT_FINDINGS_KEY = "vision_findings"
    OUTPUT_EVIDENCE_KEY = "vision_evidence"
    OUTPUT_STROKE_RELATED_KEY = "is_image_stroke_related"

    # 与脑卒中直接相关的影像类型
    _STROKE_RELATED_IMAGE_TYPES = {
        "neuroimaging_ct", "neuroimaging_mri", "neuroimaging_angiography",
    }

    # 可能与脑卒中相关的影像类型（取决于分析内容）
    _POTENTIALLY_STROKE_RELATED_TYPES = {
        "pathology_slide", "clinical_photo", "lab_report",
        "radiology_report", "ecg_waveform", "medical_illustration",
    }

    # 脑卒中相关关键词（用于检查 findings 文本）
    _STROKE_FINDING_KEYWORDS = [
        "脑卒中", "中风", "卒中", "脑梗", "脑梗死", "脑出血", "脑缺血",
        "脑血管", "缺血性", "出血性", "梗死", "梗塞", "血栓",
        "大脑中动脉", "大脑前动脉", "大脑后动脉", "基底动脉", "颈内动脉",
        "溶栓", "取栓", "抗血小板", "抗凝",
        "stroke", "cerebral", "infarction", "hemorrhage", "ischemic",
        "颅内", "脑实质", "脑室", "脑沟", "蛛网膜下腔",
    ]

    # 明确非医学/非卒中内容指示词 — 出现在 findings 中直接判定不相关
    _NON_MEDICAL_INDICATORS = [
        # ── 数学/作业/考试 ──
        "数学", "数学题", "数学公式", "方程式", "代数", "几何", "微积分",
        "数学作业", "数学试卷", "考试题", "习题", "作业", "试卷", "考题",
        "math", "equation", "algebra", "calculus", "geometry",
        # ── 大头照/人像/自拍 ──
        "自拍", "大头照", "证件照", "肖像", "人像", "人脸", "正面照",
        "自拍照", "合影", "全家福", "毕业照", "聚会", "合照",
        "portrait", "selfie", "headshot", "face photo", "person smiling",
        "a person wearing", "a man in", "a woman in", "someone is",
        "this is a photograph of a person",
        # ── 日常场景 ──
        "猫", "狗", "宠物", "动物", "食物", "菜", "饭", "餐厅", "厨房", "烹饪",
        "车", "汽车", "建筑", "风景", "山", "海", "花", "草", "树", "天空",
        "旅游", "运动", "运动场", "比赛", "操场", "健身",
        "手机", "电脑", "屏幕截图", "聊天记录", "二维码", "社交媒体",
        # ── 文档/表格 ──
        "表格", "excel", "word", "ppt", "幻灯片", "电子表格",
        "文档", "合同", "发票", "收据", "笔记", "备忘录",
        "spreadsheet", "document", "slide", "presentation",
        # ── 非卒中的医学内容 ──
        "胸部", "肺", "骨折", "皮肤", "皮疹", "眼科", "牙", "口腔",
        "孕妇", "胎儿", "儿科", "骨科", "外科手术", "腹腔",
        "chest x-ray", "pneumonia", "bone fracture", "dermatology",
        "dental", "ophthalmology", "obstetric",
        # ── Qwen VL 对非医学图片的常见描述 ──
        "this is a photo", "this image shows a person", "ordinary",
        "casual", "snapshot", "screenshot", "selfie",
        "non-medical", "not a medical image", "everyday scene",
        "no medical content", "no obvious medical",
    ]

    # Tier 1 门控通过阈值
    _GATE_CONFIDENCE_THRESHOLD = 0.5

    def __init__(
        self,
        medical_vision_service=None,
        vision_rag_bridge=None,
        llm_fast=None,
    ):
        """
        Args:
            medical_vision_service: MedicalVisionService 实例
            vision_rag_bridge: VisionRAGBridge 实例
            llm_fast: 快速LLM（用于生成检索查询等轻量任务）
        """
        self._vision = medical_vision_service
        self._bridge = vision_rag_bridge
        self._llm = llm_fast
        self._api_key = os.getenv("DASHSCOPE_API_KEY")

    async def run(self, state: LearningState) -> Dict:
        """执行影像分析节点。

        流程：
        Tier 1 快速门控 → 结构化分析 → PubMed检索 → 本地知识库检索 → 证据融合
        """
        images = state.get("images", [])
        if not images:
            logger.info("[vision_node] 无图片输入，跳过影像分析")
            return {
                self.OUTPUT_FINDINGS_KEY: None,
                self.OUTPUT_EVIDENCE_KEY: "",
                self.OUTPUT_STROKE_RELATED_KEY: False,
            }

        question = state.get("case_text", "")
        all_info = state.get("all_info", "")
        existing_evidence = state.get("evidence", "")

        logger.info(f"[vision_node] 开始处理 {len(images)} 张医学影像 | 问题: {question[:80]}")

        # ================================================================
        # Tier 1: 快速门控 — 直接问 VL 模型图片是否与脑卒中相关
        # ================================================================
        gate_passed = await self._run_stroke_gate(images, question)
        if not gate_passed:
            logger.info("[vision_node] Tier 1 门控未通过 → 图片与脑卒中无关，直接拒绝")
            return {
                self.OUTPUT_FINDINGS_KEY: None,
                self.OUTPUT_EVIDENCE_KEY: "",
                self.OUTPUT_STROKE_RELATED_KEY: False,
                "_gate_result": "rejected_by_gate",
            }

        # ================================================================
        # Step 1: 结构化影像分析
        # ================================================================
        findings = None
        vision_evidence_text = ""

        if self._vision:
            try:
                findings = await self._vision.analyze_structured(
                    images=images,
                    question=question,
                    all_info=all_info,
                )
                logger.info(
                    f"[vision_node] 影像分析完成 | 类型: {findings.image_type} | "
                    f"发现: {len(findings.key_findings)} 条 | 置信度: {findings.confidence:.0%}"
                )
            except Exception as e:
                logger.error(f"[vision_node] 影像分析失败: {e}", exc_info=True)
                findings = None
        else:
            logger.warning("[vision_node] MedicalVisionService 未初始化")

        # ================================================================
        # Tier 2+3: 内容检测 — 从分析结果判断卒中相关性
        # ================================================================
        is_stroke_related = self._check_stroke_relevance(findings, question)

        if not is_stroke_related:
            logger.info("[vision_node] Tier 2/3 检测不通过 → 图片内容与脑卒中无关")
            return {
                self.OUTPUT_FINDINGS_KEY: findings.model_dump() if findings else None,
                self.OUTPUT_EVIDENCE_KEY: vision_evidence_text,
                self.OUTPUT_STROKE_RELATED_KEY: False,
                "_gate_result": "rejected_by_content_check",
            }

        # ================================================================
        # Step 2-5: 正常的检索与证据融合（仅卒中相关图片执行）
        # ================================================================
        pubmed_papers = []
        local_docs = []

        if findings and self._bridge:
            import asyncio as _asyncio
            pubmed_task = _asyncio.create_task(
                self._bridge.search_pubmed_from_findings(findings, max_results=3)
            )
            local_docs = self._bridge.search_local_knowledge(findings, top_k=3)
            try:
                pubmed_papers = await pubmed_task
            except Exception as e:
                logger.warning(f"[vision_node] PubMed检索失败: {e}")

        if findings and self._bridge:
            vision_evidence_text = self._bridge.format_evidence_for_agent(
                findings=findings,
                pubmed_papers=pubmed_papers,
                local_docs=local_docs,
            )

        merged_evidence = existing_evidence
        if vision_evidence_text:
            if merged_evidence:
                merged_evidence = f"{vision_evidence_text}\n\n---\n\n{merged_evidence}"
            else:
                merged_evidence = vision_evidence_text

        vision_questions = self._generate_vision_questions(findings) if findings else []
        existing_questions = list(state.get("learning_questions", []))
        merged_questions = vision_questions + existing_questions

        result = {
            self.OUTPUT_FINDINGS_KEY: findings.model_dump() if findings else None,
            self.OUTPUT_EVIDENCE_KEY: vision_evidence_text,
            "evidence": merged_evidence,
            "learning_questions": merged_questions,
            self.OUTPUT_STROKE_RELATED_KEY: True,
        }

        logger.info(
            f"[vision_node] 节点完成 | 影像证据长度: {len(vision_evidence_text)} | "
            f"新增子问题: {len(vision_questions)} | PubMed文献: {len(pubmed_papers)}"
        )
        return result

    # ================================================================
    # Tier 1: 快速门控
    # ================================================================

    async def _run_stroke_gate(self, images: List[str], question: str) -> bool:
        """对每张图片调用 VL 模型进行门控判断。

        策略：逐一检查每张图片（最多3张）。
        - 任一图片判定为 YES → 整体放行
        - 所有图片判定为 NO → 整体拒绝
        - API 异常 → 默认放行（交由 Tier 2/3 处理）

        返回 True（放行）或 False（拒绝）。
        """
        if not self._api_key:
            logger.warning("[vision_node] 未配置 DASHSCOPE_API_KEY，跳过快门控（默认放行）")
            return True

        images_to_check = images[:3]  # 最多检查3张

        for i, img in enumerate(images_to_check):
            try:
                gate_answer = await self._call_gate_for_image(img, question)
                is_stroke = self._parse_gate_answer(gate_answer)

                logger.info(
                    f"[vision_node] Tier 1 门控 图片{i+1}/{len(images_to_check)}: "
                    f"原始回答='{gate_answer[:80].strip()}' → "
                    f"{'✅ 放行' if is_stroke else '❌ 不通过'}"
                )

                if is_stroke:
                    # 有任意一张通过门控即可放行
                    return True
            except Exception as e:
                logger.warning(f"[vision_node] 门控 图片{i+1} 异常: {e}，继续检查下一张")

        # 所有图片都未通过门控
        logger.info(f"[vision_node] Tier 1 门控: {len(images_to_check)} 张图片全部未通过 → 拦截")
        return False

    async def _call_gate_for_image(self, image: str, question: str) -> str:
        """对单张图片执行门控调用，返回 VL 模型的原始回答文本。"""
        messages = self._build_gate_messages([image], question)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(
            target=self._run_sync_gate,
            args=(messages, queue, loop),
            daemon=True,
        )
        t.start()

        full_text_parts = []
        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                raise item
            full_text_parts.append(str(item))

        return "".join(full_text_parts).strip()

    def _build_gate_messages(self, images: List[str], question: str) -> list:
        """构建门控 API 消息"""
        messages = [
            {"role": "system", "content": [{"text": _STROKE_GATE_PROMPT}]}
        ]
        user_content = []
        for img in images:
            url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
            user_content.append({"image": url})
        user_content.append({"text": "Is this image related to stroke (脑卒中) medicine? YES or NO:"})
        messages.append({"role": "user", "content": user_content})
        return messages

    def _run_sync_gate(self, messages: list, queue: asyncio.Queue, loop):
        """后台线程：调用 DashScope VL API 执行门控判断"""
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
                    put(Exception(f"API error {chunk.status_code}"))
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

    @staticmethod
    def _parse_gate_answer(answer: str) -> bool:
        """解析门控返回的 YES/NO 答案。

        极其严格的策略（宁可误拦 100 张合法图片，也不放过 1 张非医学图片）：
        - 以 YES 开头（无视大小写和空格）→ 放行
        - 以 NO 开头 → 拦截
        - 包含 "NO"（明确拒绝）→ 拦截
        - 包含特定医学信号词（neuro/stroke/brain/ct/mri等）→ 容错放行
        - 其他所有情况 → 拦截
        """
        answer = answer.strip().upper().replace(" ", "")

        # 明确 YES
        if answer.startswith("YES"):
            return True
        if answer == "Y":
            return True

        # 明确 NO（包括各种变体）
        if answer.startswith("NO"):
            return False
        if answer == "N":
            return False

        # 检查前15字符是否包含 NO（模型可能在前面加了一些词）
        if "NO" in answer[:15]:
            return False

        # 最后手段容错：检查是否有强烈的医学阳性信号
        # 这些词几乎不会出现在非医学图片的描述中
        strong_medical = [
            "NEUROIMAGING", "CEREBRAL", "INTRACRANIAL",
            "ANGIOGRAPHY", "ISCHEMIC", "HEMORRHAGE",
            "BRAINCT", "BRAINMRI", "CTSCAN", "MRISCAN",
        ]
        has_strong = any(s in answer for s in strong_medical)
        if has_strong:
            logger.info(f"[vision_node] 门控容错放行（强医学信号）: '{answer[:80]}'")
            return True

        # 其他情况一律拦截
        return False

    # ================================================================
    # Tier 2+3: 内容检测
    # ================================================================

    def _check_stroke_relevance(self, findings, question: str = "") -> bool:
        """判断医学影像分析结果是否与脑卒中相关。

        三层检测：
        Tier 2 — 影像类型检测：CT/MRI/DSA → 确定相关
        Tier 3 — 内容检测：findings 中查找卒中关键词 + 排除非医学指标
        """
        if not findings:
            return False

        img_type = findings.image_type if hasattr(findings, 'image_type') else ""

        # === Tier 2: 影像类型检测 ===
        if img_type in self._STROKE_RELATED_IMAGE_TYPES:
            logger.info(f"[vision_node] T2 影像类型 {img_type} 与脑卒中直接相关 → 放行")
            return True

        # === 合并所有文本 ===
        combined_text = " ".join([
            img_type,
            findings.anatomical_region if hasattr(findings, 'anatomical_region') else "",
            " ".join(findings.key_findings) if hasattr(findings, 'key_findings') and findings.key_findings else "",
            " ".join(ab.description for ab in (findings.abnormalities or [])),
            " ".join(findings.differential_diagnosis) if hasattr(findings, 'differential_diagnosis') and findings.differential_diagnosis else "",
            question,
        ]).lower()

        # === Tier 3a: 先检查非医学指标 — 命中则直接拒绝 ===
        non_medical_hit = None
        for indicator in self._NON_MEDICAL_INDICATORS:
            if indicator.lower() in combined_text:
                non_medical_hit = indicator
                break

        if non_medical_hit:
            logger.info(f"[vision_node] T3a 检测到非医学指标 '{non_medical_hit}' → 拦截")
            return False

        # === Tier 3b: 检查卒中关键词 ===
        has_stroke_keyword = any(
            kw.lower() in combined_text for kw in self._STROKE_FINDING_KEYWORDS
        )

        if has_stroke_keyword:
            logger.info(f"[vision_node] T3b 内容包含脑卒中关键词 → 放行")
            return True

        # === Tier 3c: 医学类型 + 有意义的发现 ===
        confidence = findings.confidence if hasattr(findings, 'confidence') else 0
        has_medical_findings = (
            (findings.key_findings and len(findings.key_findings) > 0) or
            (findings.abnormalities and len(findings.abnormalities) > 0)
        )

        if img_type in self._POTENTIALLY_STROKE_RELATED_TYPES:
            if has_medical_findings and confidence > 0.4:
                logger.info(f"[vision_node] T3c 医学类型 {img_type} + 有发现 + 置信度 {confidence:.0%} → 放行")
                return True
            logger.info(f"[vision_node] T3c 医学类型 {img_type} 但缺少发现或置信度不足 → 拦截")
            return False

        # === courseware_image 严格检查 ===
        if img_type == "courseware_image":
            # 必须同时有：卒中关键词 + 足够置信度 + 明确发现
            if has_stroke_keyword and has_medical_findings and confidence > 0.5:
                logger.info(f"[vision_node] courseware 含卒中关键词+发现 → 放行")
                return True
            logger.info(f"[vision_node] courseware_image 不满足严格条件 → 拦截")
            return False

        # 其他未知类型
        if has_medical_findings and has_stroke_keyword and confidence > 0.5:
            logger.info(f"[vision_node] 未知类型但含卒中关键词+发现 → 放行")
            return True

        logger.info(
            f"[vision_node] 最终判断不相关 | 类型: {img_type} | "
            f"置信度: {confidence:.0%} | 发现数: {len(findings.key_findings or [])} | "
            f"卒中关键词: {has_stroke_keyword}"
        )
        return False

    # ================================================================
    # 辅助方法
    # ================================================================

    def _generate_vision_questions(self, findings) -> List[str]:
        """从影像发现生成学习子问题，引导后续的检索和推理。"""
        questions = []

        if not findings:
            return questions

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
        """检查 state 中是否包含需要分析的医学影像。

        供 clinical_graph.py 中的条件路由使用。
        """
        images = state.get("images", [])
        return bool(images)
