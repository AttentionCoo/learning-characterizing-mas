"""专家共享工具集：为 ReasonNode 中的专家 Agent 提供有界能力。

工具以闭包形式构建，捕获当前 state 与共享记忆系统，供 create_react_agent 使用。
每个工具带审计副作用：调用时经 emit 回调推送 agent_tool 事件，前端可审计"专家到底调了哪个工具"。
"""
import logging
from typing import Callable, Dict, List, Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _dict_to_text(item: Dict) -> str:
    """从记忆条目中提取文本（兼容不同返回结构）。"""
    if not isinstance(item, dict):
        return str(item)
    for key in ("content", "text", "document", "page_content"):
        if item.get(key):
            return str(item[key])
    return str(item)[:300]


def build_expert_tools(
    state: Dict,
    shared_memory_system=None,
    emit: Optional[Callable[[Dict], None]] = None,
) -> Dict[str, object]:
    """构建专家可用工具，键为工具名。"""
    evidence_text = state.get("evidence", "") or ""
    profile_text = state.get("profile_summary", "") or ""

    def _notify(name: str, args: Dict):
        if emit:
            try:
                emit({"type": "agent_tool", "tool": name, "args": args})
            except Exception:
                pass

    @tool
    def lookup_evidence(query: str) -> str:
        """在已检索的循证材料中查找与 query 相关的证据片段，返回匹配片段（截断）。"""
        _notify("lookup_evidence", {"query": (query or "")[:80]})
        if not evidence_text:
            return "当前无已检索证据"
        lines = [l for l in evidence_text.split("\n") if l.strip()]
        keywords = [k for k in (query or "").split() if len(k) >= 2][:6]
        hits = [l for l in lines if any(k in l for k in keywords)] if keywords else []
        result = "\n".join(hits[:6]) if hits else evidence_text[:1200]
        return result[:2000]

    @tool
    def get_student_profile() -> str:
        """获取当前学生的学习画像摘要。"""
        _notify("get_student_profile", {})
        return profile_text[:2000] if profile_text else "暂无学习画像信息"

    @tool
    def retrieve_shared_memory(query: str) -> str:
        """从跨会话共享记忆中检索与 query 相关的高价值结论。"""
        _notify("retrieve_shared_memory", {"query": (query or "")[:80]})
        if not shared_memory_system:
            return "共享记忆不可用"
        try:
            hits: List[Dict] = shared_memory_system.retrieve_relevant(query or "", top_k=3)
            if not hits:
                return "共享记忆无相关结论"
            return "\n".join(f"- {_dict_to_text(h)[:200]}" for h in hits)[:1500]
        except Exception as e:
            logger.warning(f"共享记忆检索失败: {e}")
            return "共享记忆检索失败"

    return {
        "lookup_evidence": lookup_evidence,
        "get_student_profile": get_student_profile,
        "retrieve_shared_memory": retrieve_shared_memory,
    }
