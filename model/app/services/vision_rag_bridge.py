"""
Vision-RAG 桥接服务 — Vision-RAG Bridge

将医学影像分析的结构化发现自动转化为检索查询，
桥接视觉理解与循证检索（PubMed + 本地ChromaDB）。
"""

import logging
from typing import Dict, List, Any, Optional

from app.schemas.medical_image import MedicalImageFindings

logger = logging.getLogger(__name__)


class VisionRAGBridge:
    """视觉发现 → RAG 检索的桥接服务。

    将结构化的影像发现转化为：
    1. PubMed 检索查询字符串
    2. 本地 ChromaDB 向量检索查询字符串
    3. 由证据等级排序的综合证据包
    """

    # 脑卒中影像发现 → MeSH 术语映射
    _FINDING_TO_MESH: Dict[str, List[str]] = {
        "缺血": ["brain ischemia", "cerebral infarction", "ischemic stroke"],
        "梗死": ["cerebral infarction", "brain infarction", "acute ischemic stroke"],
        "出血": ["cerebral hemorrhage", "intracranial hemorrhage", "hemorrhagic stroke"],
        "蛛网膜下腔出血": ["subarachnoid hemorrhage", "SAH", "aneurysmal subarachnoid hemorrhage"],
        "大脑中动脉": ["middle cerebral artery", "MCA infarction", "MCA stroke"],
        "大脑前动脉": ["anterior cerebral artery", "ACA infarction"],
        "大脑后动脉": ["posterior cerebral artery", "PCA infarction"],
        "基底动脉": ["basilar artery", "basilar artery occlusion", "posterior circulation stroke"],
        "颈内动脉": ["internal carotid artery", "carotid stenosis", "carotid artery disease"],
        "脑水肿": ["cerebral edema", "brain edema", "malignant cerebral edema"],
        "脑疝": ["brain herniation", "cerebral herniation", "transtentorial herniation"],
        "脑萎缩": ["brain atrophy", "cerebral atrophy"],
        "白质病变": ["white matter hyperintensity", "leukoaraiosis", "white matter disease"],
        "微出血": ["cerebral microbleeds", "microhemorrhage", "cerebral amyloid angiopathy"],
        "血管狭窄": ["arterial stenosis", "vascular stenosis", "cerebrovascular stenosis"],
        "血管闭塞": ["arterial occlusion", "large vessel occlusion", "LVO"],
        "动脉瘤": ["intracranial aneurysm", "cerebral aneurysm", "aneurysmal"],
        "动静脉畸形": ["arteriovenous malformation", "AVM", "cerebral AVM"],
        "静脉窦血栓": ["cerebral venous sinus thrombosis", "CVST", "venous thrombosis"],
        "溶栓": ["thrombolysis", "alteplase", "thrombolytic therapy", "tPA"],
        "取栓": ["thrombectomy", "mechanical thrombectomy", "endovascular treatment"],
        "抗血小板": ["antiplatelet therapy", "aspirin", "clopidogrel", "dual antiplatelet"],
        "抗凝": ["anticoagulation", "warfarin", "DOAC", "atrial fibrillation"],
        "他汀": ["statin", "lipid-lowering", "atorvastatin", "secondary prevention"],
        "康复": ["stroke rehabilitation", "motor recovery", "post-stroke rehabilitation"],
        "影像": ["neuroimaging", "CT stroke", "MRI stroke", "stroke imaging"],
        "鉴别诊断": ["stroke mimics", "differential diagnosis", "pseudostroke"],
    }

    def __init__(self, pubmed_service=None, unified_search_engine=None):
        self._pubmed = pubmed_service
        self._search_engine = unified_search_engine

    # ----------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------

    def generate_search_queries(self, findings: MedicalImageFindings) -> List[str]:
        """从结构化影像发现生成检索查询列表。

        策略：
        1. 从异常发现的描述中提取关键词 → MeSH映射
        2. 从鉴别诊断列表生成查询
        3. 组合解剖位置 + 病理发现生成综合查询
        """
        queries = []

        # 来源1：异常发现的 MeSH 映射
        for ab in findings.abnormalities:
            combined_text = f"{ab.location} {ab.description} {ab.significance}"
            mesh_terms = self._extract_mesh_terms(combined_text)
            if mesh_terms:
                queries.append(" ".join(mesh_terms[:3]))

        # 来源2：鉴别诊断
        for dd in findings.differential_diagnosis[:3]:
            if dd and len(dd) > 3:
                queries.append(f"{dd} stroke")

        # 来源3：解剖区域 + 影像类型
        if findings.anatomical_region:
            img_type_name = findings.image_type.replace("neuroimaging_", "").replace("_", " ")
            queries.append(f"{findings.anatomical_region} {img_type_name} stroke")

        # 来源4：关键发现关键词组合
        if findings.key_findings:
            keywords = " ".join(findings.key_findings[:3])
            if len(keywords) > 10:
                queries.append(f"{keywords} cerebrovascular")

        # 去重 + 限制数量
        seen = set()
        unique_queries = []
        for q in queries:
            q_lower = q.lower().strip()
            if q_lower and q_lower not in seen:
                seen.add(q_lower)
                unique_queries.append(q)

        logger.info(f"[vision_rag] 从影像发现生成 {len(unique_queries)} 个检索查询")
        return unique_queries[:5]

    async def search_pubmed_from_findings(
        self,
        findings: MedicalImageFindings,
        max_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """从影像发现检索PubMed文献。

        Returns:
            List of paper dicts, ranked by evidence level
        """
        if not self._pubmed:
            logger.warning("[vision_rag] PubMed 服务未初始化")
            return []

        queries = self.generate_search_queries(findings)
        all_papers: Dict[str, Dict] = {}

        for query in queries[:3]:  # 限制查询数量避免API过载
            try:
                papers = await self._pubmed.search_papers(query, max_results=3)
                for paper in papers:
                    pmid = paper.get("pmid", "")
                    if pmid and pmid not in all_papers:
                        all_papers[pmid] = paper
            except Exception as e:
                logger.warning(f"[vision_rag] PubMed查询失败 '{query}': {e}")

        # 按证据等级排序
        from app.services.pubmed_service import _EVIDENCE_RANK

        def evidence_score(paper: Dict) -> int:
            pub_types = paper.get("pub_type", [])
            return min(
                (_EVIDENCE_RANK.get(pt, 8) for pt in pub_types),
                default=8,
            )

        ranked = sorted(all_papers.values(), key=evidence_score)[:max_results]
        logger.info(f"[vision_rag] PubMed检索完成 | 去重后 {len(all_papers)} 篇 → 返回 {len(ranked)} 篇")
        return ranked

    def search_local_knowledge(self, findings: MedicalImageFindings, top_k: int = 3) -> List[Dict[str, Any]]:
        """从本地 ChromaDB 知识库检索与影像发现相关的文档。

        Returns:
            List of document dicts with content and metadata
        """
        if not self._search_engine:
            logger.warning("[vision_rag] 检索引擎未初始化")
            return []

        # 构建综合查询文本
        query_parts = []
        if findings.anatomical_region:
            query_parts.append(findings.anatomical_region)
        query_parts.extend(findings.key_findings[:3])
        query_parts.extend(findings.differential_diagnosis[:2])
        query_text = " ".join(query_parts)

        if not query_text.strip():
            return []

        try:
            results = self._search_engine.search(query_text, top_k=top_k)
            logger.info(f"[vision_rag] 本地知识库检索 | 查询='{query_text[:80]}' | 结果={len(results)} 条")
            return results
        except Exception as e:
            logger.warning(f"[vision_rag] 本地知识库检索失败: {e}")
            return []

    def format_evidence_for_agent(
        self,
        findings: MedicalImageFindings,
        pubmed_papers: List[Dict[str, Any]],
        local_docs: List[Dict[str, Any]],
    ) -> str:
        """将视觉发现和检索证据格式化为适合多智能体推理的文本。

        这个文本会被注入到 LearningState.evidence 中，供 reason_node 使用。
        """
        parts = []

        # 1. 影像发现摘要
        parts.append("## 📷 医学影像分析结果")
        parts.append(f"- 影像类型：{findings.image_type}")
        parts.append(f"- 解剖区域：{findings.anatomical_region}")
        parts.append(f"- 关键发现：")
        for f in findings.key_findings:
            parts.append(f"  * {f}")
        if findings.abnormalities:
            parts.append(f"- 异常发现（{len(findings.abnormalities)} 处）：")
            for ab in findings.abnormalities:
                parts.append(f"  * {ab.location}：{ab.description}（临床意义：{ab.significance}）")
        if findings.differential_diagnosis:
            parts.append(f"- 鉴别诊断：{' > '.join(findings.differential_diagnosis)}")
        parts.append(f"- 紧急程度：{findings.urgency_level}")
        parts.append(f"- 置信度：{findings.confidence:.0%}")
        parts.append(f"- 建议确认性检查：{', '.join(findings.recommended_confirmatory_tests) if findings.recommended_confirmatory_tests else '无'}")
        if findings.limitations:
            parts.append(f"- 分析局限性：{findings.limitations}")

        # 2. PubMed 循证文献
        if pubmed_papers:
            parts.append("\n## 📚 PubMed 循证文献")
            for i, paper in enumerate(pubmed_papers, 1):
                pub_types = ", ".join(paper.get("pub_type", [])[:3])
                parts.append(f"{i}. **{paper.get('title', '')}**")
                parts.append(f"   - 期刊：{paper.get('journal', '')} ({paper.get('pub_date', '')})")
                parts.append(f"   - 作者：{paper.get('authors', '')}")
                parts.append(f"   - 类型：{pub_types}")
                parts.append(f"   - 摘要：{paper.get('abstract', '')[:200]}...")
                parts.append(f"   - PubMed: {paper.get('url', '')}")

        # 3. 本地知识库
        if local_docs:
            parts.append("\n## 📖 本地卒中指南参考")
            for i, doc in enumerate(local_docs, 1):
                content = doc.get("content", "")[:200] if isinstance(doc, dict) else str(doc)[:200]
                source = doc.get("metadata", {}).get("source", "") if isinstance(doc, dict) else ""
                parts.append(f"{i}. [{source}] {content}...")

        # 4. 免责声明
        parts.append("\n---")
        parts.append("> ⚠️ **AI辅助教育说明**：以上影像分析由多模态AI模型自动生成，仅供医学教育参考。")
        parts.append("> 所有AI影像判读结果必须由具备资质的放射科医生或临床医生确认。")
        parts.append("> 请勿基于AI分析结果做出临床决策。")

        return "\n".join(parts)

    # ----------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------

    def _extract_mesh_terms(self, text: str) -> List[str]:
        """从中文医学描述中提取英文 MeSH 术语"""
        terms = []
        text_lower = text.lower()
        for cn_keyword, en_terms in self._FINDING_TO_MESH.items():
            if cn_keyword.lower() in text_lower or any(
                t.lower() in text_lower for t in en_terms
            ):
                terms.extend(en_terms)
        # 去重
        return list(dict.fromkeys(terms))
