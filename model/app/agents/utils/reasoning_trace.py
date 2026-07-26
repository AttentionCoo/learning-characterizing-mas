"""生成可公开展示的推理摘要与 RAG 检索依据。"""

import re
from typing import Any, Dict, List


_DOCUMENT_PATTERN = re.compile(
    r"【文献\d+】\[来源:(.*?)\s+p\.([^\]]+)\]\(相关度:([^)]+)\)\s*\n"
    r"(.*?)(?=\n\s*(?:【文献\d+】|---|###\s*检索维度)|\Z)",
    re.DOTALL,
)
_QUERY_PATTERN = re.compile(r"###\s*检索维度\d+\s*:\s*([^\n]+)")


def _clean_guide_name(source: str) -> str:
    name = (source or "未知指南").strip()
    return re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)


def _compact_text(text: str, limit: int | None = 240) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if limit is None or len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def parse_retrieval_evidence(evidence: str, max_sources: int | None = None) -> List[Dict[str, str]]:
    """从现有证据文本中提取指南、页码、检索问题和命中片段。"""
    if not evidence:
        return []

    query_matches = list(_QUERY_PATTERN.finditer(evidence))
    sources: List[Dict[str, str]] = []

    for match in _DOCUMENT_PATTERN.finditer(evidence):
        query = ""
        for query_match in query_matches:
            if query_match.start() > match.start():
                break
            query = query_match.group(1).strip()

        sources.append({
            "guide": _clean_guide_name(match.group(1)),
            "page": match.group(2).strip(),
            "query": query,
            "score": match.group(3).strip(),
            "excerpt": _compact_text(match.group(4), limit=None),
        })
        if max_sources is not None and len(sources) >= max_sources:
            break

    return sources


def build_node_trace(node: str, output: Any) -> Dict[str, Any]:
    """把节点输出转换为可审计摘要，不暴露提示词或隐藏思维链。"""
    data = output if isinstance(output, dict) else {}

    if node == "intent":
        intent = data.get("intent_type") or "学习请求"
        return {"title": "意图识别完成", "content": f"已将本次请求识别为：{intent}。"}

    if node == "analysis":
        questions = [str(item).strip() for item in data.get("learning_questions", []) if str(item).strip()]
        content = "已拆解本次任务。"
        if questions:
            content = "重点分析：" + "；".join(questions[:5])
        return {"title": "学习需求分析完成", "content": content}

    if node == "retrieve":
        sources = data.get("retrieval_sources") or parse_retrieval_evidence(
            str(data.get("evidence", ""))
        )
        guide_count = len({source["guide"] for source in sources})
        if sources:
            content = f"RAG 共命中 {len(sources)} 条指南证据，来自 {guide_count} 本指南。"
        else:
            content = "本轮未检索到可展示的指南证据。"
        return {"title": "RAG 检索完成", "content": content, "sources": sources}

    if node == "reason":
        experts = [str(item).strip() for item in data.get("active_experts", []) if str(item).strip()]
        debate_rounds = len(data.get("debate_history", []) or [])
        parts = []
        if experts:
            parts.append(f"参与智能体：{'、'.join(experts)}")
        if debate_rounds:
            parts.append(f"完成 {debate_rounds} 轮交叉校验")
        parts.append("已综合形成回答方案，并检查潜在遗漏与冲突")
        return {"title": "多智能体推理完成", "content": "；".join(parts) + "。"}

    if node == "validate":
        passed = data.get("validation_passed", True)
        feedback = _compact_text(str(data.get("validation_feedback", "")), 160)
        if passed:
            content = "事实一致性、完整性与安全性检查通过。"
        else:
            content = f"质量检查发现问题并进入修正：{feedback or '需要重新生成部分内容'}"
        return {"title": "质量校验完成", "content": content}

    if node == "vision":
        findings = data.get("vision_findings") or {}
        image_type = findings.get("image_type", "医学影像") if isinstance(findings, dict) else "医学影像"
        key_count = len(findings.get("key_findings", []) or []) if isinstance(findings, dict) else 0
        return {"title": "影像分析完成", "content": f"已识别 {image_type}，提取 {key_count} 项关键发现。"}

    if node in {"generate_report", "knowledge_answer"}:
        return {"title": "回答生成完成", "content": "已根据分析结果和检索证据组织最终回答。"}

    return {"title": "处理完成", "content": "该步骤已完成。"}
