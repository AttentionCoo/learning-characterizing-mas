"""
VisionAnalysisNode — LangGraph 医学影像分析节点

将医学多模态影像分析深度集成到多智能体推理工作流中。
影像分析结果作为"视觉证据"参与后续的检索、推理和辩论环节。

工作流位置：
  intent → vision → retrieve → reason → validate → generate_report
  (当 state 中存在 images 且非空时)

防护机制（三层）：
  Tier 1: 快速门控 — 中文 Prompt 调用 VL 模型，询问是否脑卒中相关
  Tier 2: 类型检测 — 检查 image_type 是否属于神经/医学影像类别
  Tier 3: 硬指标检测 — 统计医学解剖术语密度，非医学图片天然缺乏这些术语
"""

import asyncio
import logging
import os
import re
import threading
from typing import Dict, List, Optional

from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode

logger = logging.getLogger(__name__)

# 流结束哨兵
_STREAM_DONE = object()

# ============================================================
# Tier 1 门控 Prompt（中文版 — Qwen 对中文指令遵从度更高）
# ============================================================
_STROKE_GATE_PROMPT_CN = """你是脑卒中（中风）医学教育系统的严格守门人。请仔细查看这张图片，然后只回答一个字："是" 或 "否"。

图片属于以下任一类型，回答"是"：
- 脑部CT、脑部MRI、脑血管造影（CTA/MRA/DSA）
- 头部/颅脑的医学扫描影像
- 脑血管相关的病理切片
- 脑卒中体征的临床照片（面瘫、肢体偏瘫等）
- 脑卒中相关的检验报告单（血常规、凝血功能等）
- 脑卒中相关的影像诊断报告
- 脑卒中相关的心电图（房颤等）
- 脑血管解剖或卒中机制的医学图解

图片属于以下任一类型，回答"否"：
- 普通人像照片（自拍、大头照、证件照、合影等）
- 文字资料（数学题、试卷、作业、笔记、课本、PPT、合同等）
- 日常场景（动物、食物、建筑、风景、物品等）
- 手机/电脑截图、社交媒体、聊天记录
- 非脑部的医学影像（胸部X光、骨折、皮肤、牙科等）
- 任何不属于脑卒中医学影像的图片

只回答"是"或"否"，不要解释，不要标点，不要其他任何文字。"""


class VisionAnalysisNode(BaseNode):
    """医学影像分析节点。

    防护流程：
    Tier 1 → 中文门控（VL 模型直接判断）
    Tier 2 → 影像类型检测（CT/MRI/DSA 放行）
    Tier 3 → 医学术语密度检测（非医学图片天然缺乏医学术语）
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

    # ── 非医学指标（命中即拦截）──
    _NON_MEDICAL_INDICATORS = [
        # 数学/作业
        "数学", "数学题", "方程式", "代数", "几何", "微积分",
        "数学作业", "考试题", "试卷", "考题", "习题",
        # 人像/自拍
        "自拍", "大头照", "证件照", "肖像", "人像", "合影",
        "全家福", "毕业照", "合照", "自拍照",
        "portrait", "selfie", "headshot",
        # 日常
        "猫", "狗", "宠物", "动物", "食物", "餐厅", "厨房",
        "汽车", "风景", "旅游", "运动", "游戏",
        "手机", "截图", "聊天", "二维码",
        # 文档
        "表格", "excel", "word", "ppt", "幻灯片", "电子表格",
        "合同", "发票", "收据", "笔记", "备忘录",
        # 非卒中医學
        "胸部", "骨折", "牙科", "眼科", "孕妇", "儿科",
        # Qwen VL 对非医学图片的描述
        "this is a photo of", "a person sitting", "a man in a",
        "everyday scene", "casual", "snapshot", "non-medical",
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
        self._api_key = os.getenv("DASHSCOPE_API_KEY")

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
        pubmed_papers = []
        local_docs = []
        vision_evidence_text = ""

        if findings and self._bridge:
            import asyncio as _asyncio
            pubmed_task = _asyncio.create_task(
                self._bridge.search_pubmed_from_findings(findings, max_results=3)
            )
            local_docs = self._bridge.search_local_knowledge(findings, top_k=3)
            try:
                pubmed_papers = await pubmed_task
            except Exception as e:
                logger.warning(f"[vision_node] PubMed 检索失败: {e}")

        if findings and self._bridge:
            vision_evidence_text = self._bridge.format_evidence_for_agent(
                findings=findings, pubmed_papers=pubmed_papers, local_docs=local_docs,
            )

        merged_evidence = existing_evidence
        if vision_evidence_text:
            merged_evidence = (
                f"{vision_evidence_text}\n\n---\n\n{merged_evidence}"
                if merged_evidence else vision_evidence_text
            )

        vision_questions = self._generate_vision_questions(findings) if findings else []
        merged_questions = vision_questions + list(state.get("learning_questions", []))

        logger.info(f"[vision_node] ✅ 完成 | 证据: {len(vision_evidence_text)} 字 | PubMed: {len(pubmed_papers)} 篇")
        return {
            self.OUTPUT_FINDINGS_KEY: findings.model_dump() if findings else None,
            self.OUTPUT_EVIDENCE_KEY: vision_evidence_text,
            "evidence": merged_evidence,
            "learning_questions": merged_questions,
            self.OUTPUT_STROKE_RELATED_KEY: True,
        }

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
                model="qwen-vl-max",
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
        - 回答以"是"开头 → 放行
        - 回答包含"否" → 拦截
        - 回答包含脑卒中医学强信号 → 容错放行
        - 其他 → 拦截
        """
        answer = answer.strip().replace(" ", "").replace("\n", "")

        # 明确的"是"
        if answer.startswith("是"):
            return True

        # 明确的"否"
        if "否" in answer[:10]:
            return False
        if answer.startswith("不"):
            return False
        if "NO" in answer[:10].upper():
            return False

        # 容错：强烈的脑卒中医学信号
        strong_signals = [
            "脑卒中", "脑梗", "脑出血", "脑血管", "CT", "MRI",
            "NEUROIMAGING", "CEREBRAL", "STROKE", "INTRACRANIAL",
            "缺血", "梗死", "血栓", "溶栓",
        ]
        has_strong = any(s in answer.upper() or s in answer for s in strong_signals)
        no_marker = "否" in answer or "NO" in answer[:20].upper()

        if has_strong and not no_marker:
            logger.info(f"[vision_node] 门控容错放行: '{answer[:60]}'")
            return True

        # 默认拦截
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
