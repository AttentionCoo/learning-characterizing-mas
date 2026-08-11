"""
证据路由与查询翻译 — Evidence Router & Query Translator
========================================================

Evidence Router:
    判断一个查询需要哪类证据（treatment/anatomy/etiology/prevention/guideline），
    并路由到对应的主题隔离 collection。

Query Translator:
    把临床口语翻译成医学检索语言：
    - 40+ 同义词扩展（rt-pa → 阿替普酶/重组组织型纤溶酶原激活剂）
    - OR-AND 范式（原词与扩展词并列，提升 BM25 与向量召回）
    - 剔除患者特异变量（NIHSS 分数、ASPECTS 分数、年龄、血压数值等），
      避免把患者数值当成检索关键词污染结果。

设计原则：规则优先（确定性、离线可测），LLM 增强为可选项。

证据类型与 collection 一一对应：
    treatment  → treatment 库
    anatomy    → anatomy 库
    etiology   → etiology 库
    prevention → prevention 库
    guideline  → guideline 库
"""

import logging
import re
from typing import List, Optional

from .labels import (
    COLLECTIONS,
    DECISION_NODE_KEYWORDS,
    DECISION_NODES,
    SUBTOPIC_COLLECTION,
)

logger = logging.getLogger(__name__)

# 与主题隔离 collection 一一对应的证据类型
EVIDENCE_TYPES: tuple = COLLECTIONS

EVIDENCE_TYPE_NAMES_CN = {
    "treatment": "治疗干预",
    "anatomy": "解剖结构",
    "etiology": "病因机制",
    "prevention": "预防康复",
    "guideline": "指南与管理",
}

# ═══════════════════════════════════════════════════════════════
# 1. 证据类型分类（关键词加权打分）
# ═══════════════════════════════════════════════════════════════

_EVIDENCE_KEYWORDS: dict = {
    "treatment": {
        "溶栓": 3, "取栓": 3, "治疗": 2, "药物": 2, "用药": 2, "剂量": 2,
        "适应证": 2, "禁忌证": 2, "手术": 2, "介入": 2, "阿替普酶": 3,
        "rt-pa": 3, "rtpa": 3, "替奈普酶": 3, "他汀": 2, "抗血小板": 3,
        "抗凝": 3, "降压": 2, "去骨瓣": 3, "支架": 2, "机械取栓": 3,
        "血管内治疗": 3, "静脉溶栓": 3, "再灌注": 3, "时间窗": 2,
        "神经保护": 2, "依达拉奉": 3, "丁苯酞": 3, "华法林": 3,
        "氯吡格雷": 3, "阿司匹林": 3, "降脂": 2, "降压药": 2,
        "桥接": 2, "用药方案": 2, "给药": 2, "血运重建": 3,
    },
    "anatomy": {
        "解剖": 3, "血管解剖": 3, "供血": 2, "willis": 3, "基底节": 2,
        "丘脑": 2, "脑干": 2, "小脑": 2, "皮层": 2, "额叶": 2, "颞叶": 2,
        "顶叶": 2, "枕叶": 2, "内囊": 2, "侧支循环": 3, "神经解剖": 3,
        "颅神经": 2, "大脑中动脉": 3, "大脑前动脉": 3, "大脑后动脉": 3,
        "mca": 3, "aca": 3, "pca": 3, "椎动脉": 2, "基底动脉": 2,
        "颈内动脉": 2, "前循环": 2, "后循环": 2, "神经": 2, "脑室": 2,
        "解剖位置": 3, "定位": 2, "功能区": 2, "供血区": 3,
    },
    "etiology": {
        "病因": 3, "发病机制": 3, "危险因素": 3, "房颤": 3, "心房颤动": 3,
        "心源性": 3, "栓塞": 3, "动脉粥样硬化": 3, "斑块": 3, "狭窄": 2,
        "血栓形成": 3, "toast": 3, "病因分型": 3, "卵圆孔未闭": 3,
        "夹层": 2, "高凝": 2, "感染性心内膜炎": 3, "心源性栓塞": 3,
        "大动脉粥样硬化": 3, "小动脉闭塞": 2, "危险因素": 3,
        "发病原因": 3, "机制": 2, "病理": 2, "糖尿病": 2, "高脂血症": 2,
    },
    "prevention": {
        "二级预防": 3, "一级预防": 3, "预防": 3, "复发": 3, "再发": 2,
        "康复": 3, "护理": 2, "随访": 2, "生活方式": 2, "戒烟": 2,
        "运动": 2, "饮食": 2, "防复发": 3, "长期管理": 2, "抗血小板预防": 3,
        "血压管理": 2, "血糖控制": 2, "康复训练": 3, "物理治疗": 3,
        "作业治疗": 3, "语言康复": 3, "吞咽康复": 3, "日常生活能力": 2,
        "危险因素控制": 3, "健康宣教": 2,
    },
    "guideline": {
        "诊断": 3, "鉴别诊断": 3, "评估": 2, "影像": 3, "ct": 2, "mri": 2,
        "dwi": 3, "cta": 3, "mra": 3, "灌注": 2, "aspects": 3, "nihss": 3,
        "mrs": 3, "量表": 2, "评分": 2, "检查": 2, "指南": 3, "共识": 3,
        "标准": 2, "分诊": 2, "卒中单元": 2, "影像学": 3, "血管造影": 3,
        "dsa": 3, "flair": 3, "swi": 3, "磁共振": 2, "时间窗评估": 3,
        "诊断流程": 3, "诊断标准": 3, "推荐": 2, "证据级别": 2, "鉴别": 2,
        "临床表现": 2, "症状": 1, "体征": 1, "偏瘫": 2, "失语": 2,
        "面瘫": 2, "构音障碍": 2, "fast": 2, "be-fast": 2, "卒中识别": 3,
    },
}

# 决策节点 → 证据类型强先验（决策规划结果直接决定路由）
_DECISION_NODE_EVIDENCE: dict = {
    "reperfusion": "treatment",
    "lvo": "treatment",
    "blood_pressure": "treatment",
    "etiology": "etiology",
    "secondary_prevention": "prevention",
}

# subtopic → 证据类型（用于查询侧主题一致性）
_EVIDENCE_FOR_SUBTOPIC = {sub: col for sub, col in SUBTOPIC_COLLECTION.items()}

# 负向关键词：强命中时压低某个证据类型（消歧）
_EVIDENCE_NEGATIVES: dict = {
    "anatomy": {
        "溶栓": 2, "取栓": 2, "治疗": 1, "药物": 1, "预防": 1,
        "二级预防": 2, "康复": 1, "诊断": 1,
    },
    "treatment": {
        "解剖": 1, "预防": 1, "康复": 1, "随访": 1, "生活方式": 1,
    },
    "etiology": {
        "溶栓": 1, "取栓": 1, "治疗": 1, "诊断": 1, "影像": 1,
    },
    "prevention": {
        "溶栓": 1, "取栓": 1, "急性期": 2, "急诊": 2, "时间窗": 1,
        "手术": 1,
    },
    "guideline": {
        "溶栓": 1, "取栓": 1, "手术": 1, "药物": 1,
    },
}


def classify_evidence_type(
    query: str,
    decision_nodes: Optional[List[str]] = None,
) -> str:
    """
    判断查询的证据类型（5 类之一）。

    参数:
        query: 用户查询（临床语言）
        decision_nodes: Clinical Decision Planner 输出的决策节点列表（可空）

    返回:
        evidence_type: treatment / anatomy / etiology / prevention / guideline
    """
    if not query or not query.strip():
        return "guideline"
    lowered = query.lower()

    scores: dict = {t: 0 for t in EVIDENCE_TYPES}
    for evidence_type, keywords in _EVIDENCE_KEYWORDS.items():
        score = 0
        for keyword, weight in keywords.items():
            if keyword.lower() in lowered:
                score += weight
        scores[evidence_type] = score

    # 负向消歧
    for evidence_type, negatives in _EVIDENCE_NEGATIVES.items():
        penalty = 0
        for keyword, weight in negatives.items():
            if keyword.lower() in lowered:
                penalty += weight
        scores[evidence_type] = max(0, scores[evidence_type] - penalty)

    # 决策节点强先验
    for node in (decision_nodes or []):
        evidence_type = _DECISION_NODE_EVIDENCE.get(node)
        if evidence_type:
            scores[evidence_type] += 4

    best = max(scores, key=lambda k: scores[k])
    if scores[best] <= 0:
        return "guideline"
    return best


# ═══════════════════════════════════════════════════════════════
# 2. 查询翻译（Query Translator）
# ═══════════════════════════════════════════════════════════════

# 患者特异变量剔除（避免把患者数值当检索词）
# 注意：不能依赖 \b 词边界——中文也是 \w，"rt-pa静脉"中 "a→静" 无边界，
# 统一用 (?<![a-z0-9]) / (?![a-z0-9]) 环视代替。
_PATIENT_VARIABLE_PATTERNS = [
    re.compile(r"(?<![a-z0-9])nihss\s*[－\-—]?\s*\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])aspects\s*[－\-—]?\s*\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])mrs\s*[－\-—]?\s*\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"(?<![a-z0-9])gcs\s*[－\-—]?\s*\d+(?:\.\d+)?", re.IGNORECASE),
    re.compile(r"年龄\s*\d+\s*岁", re.IGNORECASE),
    re.compile(r"\d+\s*岁", re.IGNORECASE),
    re.compile(r"血压\s*\d+[/／]\s*\d+\s*mmhg", re.IGNORECASE),
    re.compile(r"\d+[/／]\s*\d+\s*mmhg", re.IGNORECASE),
    re.compile(r"血糖\s*\d+(?:\.\d+)?\s*mmol/l", re.IGNORECASE),
]

# 同义词扩展表：(正则, 追加的扩展词)。命中后在原查询末尾追加扩展词。
_SYNONYM_EXPANSIONS: List[tuple] = [
    (re.compile(r"(?<![a-z0-9])rt[- ]?pa(?![a-z0-9])", re.IGNORECASE),
     "阿替普酶 重组组织型纤溶酶原激活剂"),
    (re.compile(r"(?<![a-z0-9])tpa(?![a-z0-9])", re.IGNORECASE), "阿替普酶"),
    (re.compile(r"溶栓", re.IGNORECASE), "静脉溶栓 溶栓治疗"),
    (re.compile(r"取栓", re.IGNORECASE), "机械取栓 血栓切除术 血管内治疗"),
    (re.compile(r"支架取栓", re.IGNORECASE), "机械取栓"),
    (re.compile(r"房颤", re.IGNORECASE), "心房颤动 心源性栓塞"),
    (re.compile(r"中风", re.IGNORECASE), "脑卒中 缺血性卒中"),
    (re.compile(r"脑梗", re.IGNORECASE), "脑梗死 缺血性卒中"),
    (re.compile(r"脑梗塞", re.IGNORECASE), "脑梗死"),
    (re.compile(r"(?<![a-z0-9])tia(?![a-z0-9])", re.IGNORECASE), "短暂性脑缺血发作"),
    (re.compile(r"抗血小板", re.IGNORECASE), "阿司匹林 氯吡格雷 抗血小板治疗"),
    (re.compile(r"双抗", re.IGNORECASE), "双联抗血小板"),
    (re.compile(r"抗凝", re.IGNORECASE), "华法林 新型口服抗凝药"),
    (re.compile(r"他汀", re.IGNORECASE), "降脂 阿托伐他汀"),
    (re.compile(r"降脂", re.IGNORECASE), "他汀 血脂管理"),
    (re.compile(r"降压", re.IGNORECASE), "血压管理 硝普钠 拉贝洛尔"),
    (re.compile(r"高血压", re.IGNORECASE), "血压升高 血压管理"),
    (re.compile(r"溶栓时间窗", re.IGNORECASE), "4.5小时 时间窗"),
    (re.compile(r"取栓时间窗", re.IGNORECASE), "6小时 24小时 时间窗"),
    (re.compile(r"时间窗", re.IGNORECASE), "4.5小时 6小时 24小时"),
    (re.compile(r"神经保护", re.IGNORECASE), "依达拉奉 丁苯酞"),
    (re.compile(r"去骨瓣", re.IGNORECASE), "去骨瓣减压 颅骨切除减压"),
    (re.compile(r"支架", re.IGNORECASE), "血管成形 颈动脉支架"),
    (re.compile(r"血管内介入", re.IGNORECASE), "血管内治疗 机械取栓"),
    (re.compile(r"心源性", re.IGNORECASE), "心房颤动 栓塞"),
    (re.compile(r"动脉粥样硬化", re.IGNORECASE), "大动脉粥样硬化 斑块"),
    (re.compile(r"戒烟", re.IGNORECASE), "生活方式 危险因素"),
    (re.compile(r"康复", re.IGNORECASE), "康复训练 物理治疗 作业治疗"),
    (re.compile(r"吞咽困难", re.IGNORECASE), "吞咽评估 吞咽训练"),
    (re.compile(r"失语", re.IGNORECASE), "语言康复 语言训练"),
    (re.compile(r"偏瘫", re.IGNORECASE), "肢体康复 运动疗法"),
    (re.compile(r"半暗带", re.IGNORECASE), "缺血半暗带 灌注"),
    (re.compile(r"影像", re.IGNORECASE), "ct mri dwi"),
    (re.compile(r"血管造影", re.IGNORECASE), "cta mra dsa"),
    (re.compile(r"大血管闭塞", re.IGNORECASE), "机械取栓 lvo"),
    (re.compile(r"脑出血", re.IGNORECASE), "出血性卒中 颅内出血"),
    (re.compile(r"缺血性卒中", re.IGNORECASE), "脑梗死 脑梗塞"),
    (re.compile(r"二次预防", re.IGNORECASE), "二级预防"),
    (re.compile(r"血压控制", re.IGNORECASE), "血压管理 降压"),
    (re.compile(r"血糖", re.IGNORECASE), "血糖管理 胰岛素"),
    (re.compile(r"营养", re.IGNORECASE), "营养支持 肠内营养"),
    (re.compile(r"氧疗", re.IGNORECASE), "呼吸支持 机械通气"),
    (re.compile(r"亚低温", re.IGNORECASE), "体温管理 降温"),
    (re.compile(r"(?<![a-z0-9])mrs(?![a-z0-9])", re.IGNORECASE), "改良Rankin量表"),
    (re.compile(r"(?<![a-z0-9])nihss(?![a-z0-9])", re.IGNORECASE), "美国国立卫生研究院卒中量表"),
    (re.compile(r"抗血小板药", re.IGNORECASE), "阿司匹林 氯吡格雷"),
]

# ═══════════════════════════════════════════════════════════════
# 3. 路由
# ═══════════════════════════════════════════════════════════════

# 严格隔离模式：默认只搜主库，保证"血脂指南 chunk 物理上不进 anatomy 候选集"。
# 可配置的相关库用于复杂问题（如解剖+治疗），默认关闭。
STRICT_ROUTING = True
RELATED_COLLECTIONS: dict = {
    "treatment": ("guideline",),
    "anatomy": (),
    "etiology": (),
    "prevention": ("guideline",),
    "guideline": (),
}


def route_collections(
    evidence_type: str,
    *,
    strict: bool = STRICT_ROUTING,
) -> List[str]:
    """
    按证据类型返回目标 collection 列表。

    strict=True（默认）：仅返回主库——入口约束，不匹配主题的 chunk 连候选集都进不了。
    strict=False：主库 + 相关库（跨库 RRF 融合用）。
    """
    if evidence_type not in EVIDENCE_TYPES:
        evidence_type = "guideline"
    if strict:
        return [evidence_type]
    related = RELATED_COLLECTIONS.get(evidence_type, ())
    return [evidence_type, *related]


# ═══════════════════════════════════════════════════════════════
# 4. 翻译主函数
# ═══════════════════════════════════════════════════════════════


def translate_query(query: str) -> str:
    """
    临床语言 → 医学检索语言。

    步骤：
        1. 剔除患者特异变量（NIHSS/ASPECTS/mRS/GCS 分数、年龄、血压、血糖值）
        2. 40+ 同义词扩展（OR-AND 范式：原词与扩展词并列）
        3. 压缩空白，返回扩展后的查询串

    纯规则、确定性，离线可用。
    """
    if not query or not query.strip():
        return query or ""
    text = query.strip()

    # 1. 剔除患者变量
    for pattern in _PATIENT_VARIABLE_PATTERNS:
        text = pattern.sub(" ", text)

    # 2. 同义词扩展（原词保留，扩展词追加，形成 OR-AND 检索范式）
    expansions: List[str] = []
    for pattern, extra in _SYNONYM_EXPANSIONS:
        if pattern.search(text):
            expansions.append(extra)

    # 3. 合并
    parts = [text]
    if expansions:
        parts.append(" ".join(dict.fromkeys(expansions)))  # 去重保序
    translated = " ".join(parts)
    translated = re.sub(r"\s+", " ", translated).strip()
    return translated


def translate_and_route(
    query: str,
    decision_nodes: Optional[List[str]] = None,
) -> dict:
    """
    一站式：翻译 + 分类 + 路由。

    返回:
        {
            "original": 原始查询,
            "translated": 翻译后的检索查询,
            "evidence_type": 证据类型,
            "collections": 目标 collection 列表,
            "decision_nodes": 决策节点列表,
        }
    """
    evidence_type = classify_evidence_type(query, decision_nodes=decision_nodes)
    return {
        "original": query,
        "translated": translate_query(query),
        "evidence_type": evidence_type,
        "collections": route_collections(evidence_type),
        "decision_nodes": decision_nodes or [],
    }
