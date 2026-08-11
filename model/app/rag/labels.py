"""
Chunk 级结构化医学标签 — Medical Chunk Labeling
===================================================

把"一段文本"变成"带临床语义标签的证据单元"：
- collection      : 5 个主题隔离库（anatomy/guideline/etiology/treatment/prevention）
- subtopic        : 12 类主题分类（规则关键词打分，确定性、零 API 开销）
- intervention    : 命中的具体药物/操作（14 类，含别名归一，如 rt-pa → alteplase）
- decision_node   : 对应临床决策节点（再灌注/LVO/血压/病因/二级预防）
- time_window     : 治疗时间窗（如 4.5 小时 / 6h）
- evidence_level  : 证据级别 / 推荐级别（如 I 级推荐 / A 级证据）
- year / authority: 来源文献的发布年份与权威等级（从文件名/内容提取）

设计原则：
- 全部规则化（正则 + 关键词打分），离线可运行、行为确定、可单元测试。
- 标签写入 Document.metadata，检索与评分阶段直接消费，不再依赖"embedding 玄学"。
"""

import logging
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 1. 主题隔离 Collection 定义（物理隔离的 5 个库）
# ═══════════════════════════════════════════════════════════════

COLLECTIONS: tuple = (
    "anatomy",      # 解剖结构
    "guideline",    # 诊断/评估/影像/一般管理（指南性通用内容）
    "etiology",     # 病因与发病机制
    "treatment",    # 急性期治疗（再灌注/药物/手术/并发症）
    "prevention",   # 二级预防与康复护理
)
COLLECTION_NAMES_CN = {
    "anatomy": "解剖结构",
    "guideline": "指南与管理",
    "etiology": "病因机制",
    "treatment": "治疗干预",
    "prevention": "预防康复",
}

# ═══════════════════════════════════════════════════════════════
# 2. Subtopic 12 类分类
# ═══════════════════════════════════════════════════════════════

SUBTOPICS = (
    "anatomy",           # 解剖结构
    "pathophysiology",   # 病理生理
    "etiology",          # 病因危险因素
    "clinical",          # 临床表现与识别
    "diagnosis",         # 诊断评估
    "imaging",           # 影像诊断
    "reperfusion",       # 再灌注治疗
    "medication",        # 药物治疗
    "intervention",      # 手术介入
    "complication",      # 并发症管理
    "prevention",        # 二级预防
    "rehabilitation",    # 康复与护理
)
SUBTOPIC_NAMES_CN = {
    "anatomy": "解剖结构",
    "pathophysiology": "病理生理",
    "etiology": "病因危险因素",
    "clinical": "临床表现与识别",
    "diagnosis": "诊断评估",
    "imaging": "影像诊断",
    "reperfusion": "再灌注治疗",
    "medication": "药物治疗",
    "intervention": "手术介入",
    "complication": "并发症管理",
    "prevention": "二级预防",
    "rehabilitation": "康复与护理",
}

# subtopic → collection 映射：决定 chunk 进哪个物理库
SUBTOPIC_COLLECTION: Dict[str, str] = {
    "anatomy": "anatomy",
    "pathophysiology": "etiology",
    "etiology": "etiology",
    "clinical": "guideline",
    "diagnosis": "guideline",
    "imaging": "guideline",
    "reperfusion": "treatment",
    "medication": "treatment",
    "intervention": "treatment",
    "complication": "treatment",
    "prevention": "prevention",
    "rehabilitation": "prevention",
}

# 每个 subtopic 的关键词（命中即 +1；权重 2 表示强信号，用于消歧）
_SUBTOPIC_KEYWORDS: Dict[str, Dict[str, int]] = {
    "anatomy": {
        "解剖": 1, "血管解剖": 2, "供血": 1, "willis": 2, "基底节": 1,
        "丘脑": 1, "脑干": 1, "小脑": 1, "皮层": 1, "额叶": 1, "颞叶": 1,
        "顶叶": 1, "枕叶": 1, "内囊": 2, "外囊": 2, "放射冠": 1,
        "半卵圆中心": 1, "大脑中动脉供血": 2, "前循环": 1, "后循环": 1,
        "侧支循环": 2, "神经解剖": 2, "颅神经": 1, "脑室": 1, "脑膜": 1,
        "脑沟": 1, "脑回": 1, "神经纤维束": 1, "白质": 1, "灰质": 1,
        "皮质脊髓束": 2, "椎动脉": 1, "基底动脉": 1, "颈内动脉": 1,
        "大脑前动脉": 2, "大脑中动脉": 2, "大脑后动脉": 2,
    },
    "pathophysiology": {
        "病理生理": 2, "发病机制": 2, "缺血半暗带": 2, "半暗带": 2,
        "细胞毒性水肿": 2, "血管源性水肿": 2, "血脑屏障": 1, "氧化应激": 1,
        "炎症反应": 1, "凋亡": 1, "坏死": 1, "神经元": 1, "兴奋性毒性": 2,
        "钙超载": 2, "级联反应": 2, "再灌注损伤": 2, "机制": 1, "瀑布效应": 2,
        "线粒体": 1, "自由基": 1, "脑血流": 1, "脑灌注": 1, "自动调节": 1,
        "低灌注": 1, "高灌注": 1, "分子机制": 2, "病理": 1, "生理": 1,
    },
    "etiology": {
        "病因": 2, "危险因素": 2, "房颤": 2, "心房颤动": 2, "心源性": 2,
        "栓塞": 2, "动脉粥样硬化": 2, "斑块": 2, "狭窄": 1, "血栓形成": 2,
        "高血压": 1, "糖尿病": 1, "血脂": 1, "高脂血症": 1, "吸烟": 1,
        "饮酒": 1, "肥胖": 1, "高同型半胱氨酸": 2, "卵圆孔未闭": 2,
        "感染性心内膜炎": 2, "夹层": 2, "动脉炎": 2, "血液病": 1,
        "高凝状态": 2, "病因分型": 2, "toast": 2, "心源性栓塞": 2,
        "大动脉粥样硬化": 2, "小动脉闭塞": 2, "危险因素控制": 1,
        "阵发性": 1, "持续性房颤": 2,
    },
    "clinical": {
        "临床表现": 2, "症状": 1, "体征": 1, "偏瘫": 2, "失语": 2, "面瘫": 2,
        "构音障碍": 2, "吞咽困难": 1, "意识障碍": 1, "头痛": 1, "呕吐": 1,
        "fast": 2, "be-fast": 2, "卒中识别": 2, "突发": 1, "眩晕": 1,
        "共济失调": 2, "视野缺损": 2, "感觉障碍": 1, "凝视": 1, "忽视": 1,
        "肢体无力": 1, "麻木": 1, "言语不清": 1, "口角歪斜": 2, "卒中样": 1,
        "起病": 1, "发作": 1, "神经功能缺损": 1,
    },
    "diagnosis": {
        "诊断": 1, "鉴别诊断": 2, "评估": 1, "量表": 2, "nihss": 2, "mrs": 2,
        "gcs": 1, "评分": 1, "检查": 1, "实验室": 1, "血糖": 1, "心电图": 1,
        "病史": 1, "体格检查": 1, "确诊": 1, "分型": 2, "ocsp": 2,
        "诊断流程": 2, "诊断标准": 2, "排除": 1, "转诊": 1, "分诊": 1,
        "卒中单元": 1, "入院": 1, "急诊": 1, "筛查": 1, "影像学检查": 1,
        "辅助检查": 2, "血液检查": 1,
    },
    "imaging": {
        "影像": 1, "ct": 1, "mri": 1, "dwi": 2, "adc": 2, "cta": 2, "mra": 2,
        "灌注": 1, "aspects": 2, "血管造影": 2, "dsa": 2, "磁共振": 1,
        "计算机断层": 1, "梗死灶": 1, "出血灶": 1, "影像学": 2, "flair": 2,
        "swi": 2, "mip": 1, "平扫": 1, "增强": 1, "弥散": 2, "灌注成像": 2,
        "core": 1, "mismatch": 2, "高密度征": 2, "低密度": 1, "占位": 1,
        "脑室受压": 1, "中线移位": 2, "影像特征": 2,
    },
    "reperfusion": {
        "溶栓": 2, "阿替普酶": 2, "rt-pa": 3, "rtpa": 3, "替奈普酶": 2,
        "取栓": 2, "机械取栓": 3, "血栓切除": 2, "血管内治疗": 2,
        "时间窗": 2, "再灌注": 2, "静脉溶栓": 3, "动脉溶栓": 3, "桥接": 2,
        "4.5小时": 3, "4.5h": 3, "6小时": 2, "6h": 2, "24小时": 1, "24h": 1,
        "重组组织型纤溶酶原激活剂": 3, "tpa": 3, "rt-pa静脉": 3,
        "溶栓治疗": 2, "再通": 1, "闭塞血管": 1, "再灌注率": 2,
    },
    "medication": {
        "药物": 1, "用药": 1, "剂量": 1, "适应证": 1, "禁忌证": 1,
        "抗血小板": 2, "阿司匹林": 2, "氯吡格雷": 2, "替格瑞洛": 2,
        "双联抗血小板": 3, "dapt": 3, "抗凝": 2, "华法林": 2, "肝素": 1,
        "低分子肝素": 2, "noac": 2, "达比加群": 2, "利伐沙班": 2,
        "新型口服抗凝药": 3, "他汀": 2, "阿托伐他汀": 2, "瑞舒伐他汀": 2,
        "降脂": 1, "降压药": 1, "神经保护": 2, "依达拉奉": 2, "丁苯酞": 2,
        "尤瑞克林": 2, "不良反应": 1, "副作用": 1, "相互作用": 1,
        "静脉用药": 1, "口服": 1, "给药": 1, "药代": 1, "药效": 1,
        "溶栓药物": 2, "抗栓": 1, "抗血小板治疗": 2, "抗凝治疗": 2,
    },
    "intervention": {
        "手术": 1, "介入": 1, "支架": 2, "血管成形": 2, "去骨瓣": 2,
        "减压": 1, "颈动脉内膜剥脱": 3, "cea": 3, "cas": 3, "血肿清除": 2,
        "脑室外引流": 2, "动脉瘤夹闭": 2, "颅内压监测": 1, "开颅": 2,
        "微创": 1, "介入治疗": 2, "血管内介入": 2, "球囊": 1, "导管": 1,
        "抽吸": 1, "动脉内": 1, "颈动脉支架": 3, "颅骨切除": 2,
        "手术指征": 2, "外科治疗": 2,
    },
    "complication": {
        "并发症": 2, "出血转化": 3, "症状性颅内出血": 3, "脑水肿": 2,
        "脑疝": 2, "癫痫": 1, "感染": 1, "肺炎": 1, "深静脉血栓": 2,
        "压疮": 1, "消化道出血": 2, "恶性水肿": 2, "占位效应": 2,
        "预后": 1, "死亡率": 1, "致残率": 1, "再出血": 2, "血肿扩大": 2,
        "血管再闭塞": 2, "再狭窄": 1, "过敏": 1, "发热": 1, "尿路感染": 1,
        "误吸": 1, "营养障碍": 1, "出血风险": 2, "颅内出血": 2,
    },
    "prevention": {
        "二级预防": 3, "一级预防": 3, "预防": 2, "复发": 2, "再发": 1,
        "危险因素管理": 2, "生活方式": 1, "戒烟": 1, "限酒": 1, "运动": 1,
        "饮食": 1, "随访": 1, "危险因素控制": 2, "抗血小板预防": 3,
        "降脂治疗": 2, "血压管理": 1, "血糖控制": 1, "体重管理": 1,
        "预防策略": 2, "防复发": 2, "长期管理": 2, "慢病管理": 2,
    },
    "rehabilitation": {
        "康复": 2, "护理": 1, "运动疗法": 2, "物理治疗": 2, "作业治疗": 2,
        "语言康复": 2, "语言训练": 2, "吞咽康复": 2, "吞咽训练": 2,
        "心理": 1, "情绪": 1, "认知": 1, "日常生活能力": 2, "barthel": 2,
        "早期康复": 3, "良肢位": 3, "转移": 1, "体位": 1, "康复训练": 2,
        "康复治疗": 2, "护理措施": 2, "肢体康复": 2, "功能锻炼": 2,
        "轮椅": 1, "辅助器具": 1, "出院": 1, "社区康复": 2, "生活质量": 1,
    },
}

# 文档级先验：整篇文档更可能属于哪个主题（用于弱化 chunk 误分类）
_SOURCE_PRIOR: Dict[str, Dict[str, int]] = {
    "anatomy": {
        "neuroanatomy": 3, "blumenfeld": 3, "解剖": 3, "atlas": 2,
        "textbook": 1, "clinical cases": 2,
    },
    "guideline": {
        "指南": 2, "共识": 2, "规范": 2, "guideline": 2, "指导": 1,
    },
    "etiology": {
        "病因": 3, "发病机制": 2,
    },
    "treatment": {
        "治疗": 2, "介入": 2, "溶栓": 2, "取栓": 2,
    },
    "prevention": {
        "预防": 3, "防治": 2, "康复": 2, "护理": 1,
    },
}

# ═══════════════════════════════════════════════════════════════
# 3. Intervention 14 类（具体药物/操作，含别名归一）
# ═══════════════════════════════════════════════════════════════

INTERVENTIONS: tuple = (
    "iv_thrombolysis",        # 静脉溶栓
    "mechanical_thrombectomy",# 机械取栓
    "intraarterial_thrombolysis",  # 动脉溶栓
    "antiplatelet",           # 抗血小板
    "anticoagulation",        # 抗凝
    "lipid_lowering",         # 降脂（他汀）
    "blood_pressure_control", # 降压
    "glucose_control",        # 血糖管理
    "decompressive_craniectomy",  # 去骨瓣减压
    "stenting_angioplasty",   # 支架/血管成形
    "neuroprotection",        # 神经保护/其他药物
    "rehabilitation",         # 康复训练
    "nutrition_support",      # 营养支持
    "temperature_oxygen",     # 体温/氧疗管理
)
INTERVENTION_NAMES_CN = {
    "iv_thrombolysis": "静脉溶栓",
    "mechanical_thrombectomy": "机械取栓",
    "intraarterial_thrombolysis": "动脉溶栓",
    "antiplatelet": "抗血小板",
    "anticoagulation": "抗凝",
    "lipid_lowering": "降脂治疗",
    "blood_pressure_control": "降压管理",
    "glucose_control": "血糖管理",
    "decompressive_craniectomy": "去骨瓣减压",
    "stenting_angioplasty": "支架/血管成形",
    "neuroprotection": "神经保护药物",
    "rehabilitation": "康复训练",
    "nutrition_support": "营养支持",
    "temperature_oxygen": "体温/氧疗管理",
}

# 每类干预的触发词；值里含 "别名 → 标准名" 映射提示（用于 Query Translator）
INTERVENTION_KEYWORDS: Dict[str, Dict[str, int]] = {
    "iv_thrombolysis": {
        "静脉溶栓": 3, "阿替普酶": 3, "rt-pa": 3, "rtpa": 3, "tpa": 2,
        "替奈普酶": 3, "重组组织型纤溶酶原激活剂": 3, "溶栓": 2, "溶栓治疗": 2,
        "alteplase": 3, "tenecteplase": 3,
    },
    "mechanical_thrombectomy": {
        "机械取栓": 3, "取栓": 3, "血栓切除": 3, "支架取栓": 3, "抽吸取栓": 3,
        "thrombectomy": 3, "血管内治疗": 2, "取栓治疗": 3,
    },
    "intraarterial_thrombolysis": {
        "动脉溶栓": 3, "动脉内溶栓": 3, "动脉内给药": 2,
    },
    "antiplatelet": {
        "抗血小板": 3, "阿司匹林": 3, "氯吡格雷": 3, "替格瑞洛": 3,
        "双联抗血小板": 3, "dapt": 3, "aspirin": 3, "clopidogrel": 3,
        "抗血小板治疗": 3, "抗栓": 2,
    },
    "anticoagulation": {
        "抗凝": 3, "华法林": 3, "肝素": 2, "低分子肝素": 3, "达比加群": 3,
        "利伐沙班": 3, "新型口服抗凝药": 3, "noac": 3, "warfarin": 3,
        "抗凝治疗": 3, "普通肝素": 2,
    },
    "lipid_lowering": {
        "他汀": 3, "阿托伐他汀": 3, "瑞舒伐他汀": 3, "辛伐他汀": 3,
        "降脂": 3, "降脂治疗": 3, "他汀类": 3, "statins": 3, "atovastatin": 3,
        "血脂管理": 2,
    },
    "blood_pressure_control": {
        "降压": 3, "降压治疗": 3, "硝普钠": 3, "拉贝洛尔": 3, "尼卡地平": 3,
        "乌拉地尔": 3, "血压管理": 3, "降压药": 3, "静脉降压": 3,
        "收缩压": 1, "舒张压": 1, "目标血压": 2,
    },
    "glucose_control": {
        "降糖": 3, "胰岛素": 3, "血糖管理": 3, "血糖控制": 3, "血糖监测": 2,
        "降糖治疗": 3, "低血糖": 2, "高血糖": 2,
    },
    "decompressive_craniectomy": {
        "去骨瓣": 3, "去骨瓣减压": 3, "减压颅骨切除": 3, "颅骨切除减压": 3,
        "恶性脑水肿": 2, "减压手术": 2, "craniectomy": 3,
    },
    "stenting_angioplasty": {
        "支架": 3, "血管成形": 3, "颈动脉支架": 3, "cas": 3, "球囊扩张": 3,
        "支架植入": 3, "stenting": 3, "angioplasty": 3, "颅内支架": 3,
    },
    "neuroprotection": {
        "神经保护": 3, "依达拉奉": 3, "丁苯酞": 3, "尤瑞克林": 3,
        "神经保护剂": 3, "脑保护": 3, "脑苷肌肽": 2, "胞磷胆碱": 2,
        "神经修复": 2,
    },
    "rehabilitation": {
        "康复训练": 3, "康复治疗": 3, "运动疗法": 3, "物理治疗": 3,
        "作业治疗": 3, "语言训练": 3, "吞咽训练": 3, "康复": 2,
        "功能锻炼": 3, "早期康复": 3,
    },
    "nutrition_support": {
        "营养支持": 3, "肠内营养": 3, "肠外营养": 3, "鼻饲": 3,
        "营养评估": 3, "吞咽评估": 2, "营养治疗": 3, "管饲": 3,
    },
    "temperature_oxygen": {
        "亚低温": 3, "降温": 2, "体温管理": 3, "氧疗": 3, "呼吸支持": 3,
        "机械通气": 3, "气道管理": 3, "低氧": 2, "血氧": 2, "目标温度": 3,
    },
}

# 干预别名归一表：别名 → 标准干预名（Query Translator 与标签共用）
INTERVENTION_ALIASES: Dict[str, str] = {
    "rt-pa": "iv_thrombolysis", "rtpa": "iv_thrombolysis", "tpa": "iv_thrombolysis",
    "rt-pa静脉溶栓": "iv_thrombolysis", "阿替普酶": "iv_thrombolysis",
    "替奈普酶": "iv_thrombolysis", "alteplase": "iv_thrombolysis",
    "溶栓": "iv_thrombolysis", "静脉溶栓": "iv_thrombolysis",
    "取栓": "mechanical_thrombectomy", "机械取栓": "mechanical_thrombectomy",
    "支架取栓": "mechanical_thrombectomy", "抽吸取栓": "mechanical_thrombectomy",
    "血栓切除": "mechanical_thrombectomy", "thrombectomy": "mechanical_thrombectomy",
    "动脉溶栓": "intraarterial_thrombolysis",
    "阿司匹林": "antiplatelet", "氯吡格雷": "antiplatelet",
    "替格瑞洛": "antiplatelet", "抗血小板": "antiplatelet",
    "双联抗血小板": "antiplatelet", "aspirin": "antiplatelet",
    "华法林": "anticoagulation", "达比加群": "anticoagulation",
    "利伐沙班": "anticoagulation", "新型口服抗凝药": "anticoagulation",
    "抗凝": "anticoagulation", "warfarin": "anticoagulation",
    "他汀": "lipid_lowering", "阿托伐他汀": "lipid_lowering",
    "瑞舒伐他汀": "lipid_lowering", "降脂": "lipid_lowering",
    "降压": "blood_pressure_control", "硝普钠": "blood_pressure_control",
    "拉贝洛尔": "blood_pressure_control", "尼卡地平": "blood_pressure_control",
    "乌拉地尔": "blood_pressure_control",
    "胰岛素": "glucose_control", "降糖": "glucose_control",
    "去骨瓣": "decompressive_craniectomy", "去骨瓣减压": "decompressive_craniectomy",
    "支架": "stenting_angioplasty", "血管成形": "stenting_angioplasty",
    "颈动脉支架": "stenting_angioplasty",
    "依达拉奉": "neuroprotection", "丁苯酞": "neuroprotection",
    "尤瑞克林": "neuroprotection", "神经保护": "neuroprotection",
    "康复训练": "rehabilitation", "康复": "rehabilitation",
    "物理治疗": "rehabilitation", "作业治疗": "rehabilitation",
    "语言训练": "rehabilitation", "吞咽训练": "rehabilitation",
    "肠内营养": "nutrition_support", "肠外营养": "nutrition_support",
    "鼻饲": "nutrition_support", "营养支持": "nutrition_support",
    "亚低温": "temperature_oxygen", "氧疗": "temperature_oxygen",
    "机械通气": "temperature_oxygen",
}

# ═══════════════════════════════════════════════════════════════
# 4. 临床决策节点（Clinical Decision Planner 共用）
# ═══════════════════════════════════════════════════════════════

DECISION_NODES: tuple = (
    "reperfusion",           # 再灌注治疗（时间窗内溶栓/取栓决策）
    "lvo",                   # 大血管闭塞评估（是否适合取栓）
    "blood_pressure",        # 血压管理（急性期/二级预防）
    "etiology",              # 病因评估（TOAST 分型）
    "secondary_prevention",  # 二级预防（抗血小板/他汀/降压/抗凝）
)
DECISION_NODE_NAMES_CN = {
    "reperfusion": "再灌注治疗",
    "lvo": "大血管闭塞(LVO)评估",
    "blood_pressure": "血压管理",
    "etiology": "病因评估",
    "secondary_prevention": "二级预防",
}

DECISION_NODE_KEYWORDS: Dict[str, Dict[str, int]] = {
    "reperfusion": {
        "溶栓": 3, "取栓": 2, "阿替普酶": 3, "rt-pa": 3, "替奈普酶": 3,
        "时间窗": 3, "4.5小时": 3, "6小时": 2, "血管内治疗": 2, "再灌注": 3,
        "静脉溶栓": 3, "动脉溶栓": 3, "桥接": 2, "rtpa": 3, "tpa": 3,
    },
    "lvo": {
        "大血管闭塞": 3, "lvo": 3, "机械取栓": 3, "取栓": 2, "闭塞": 2,
        "颈内动脉": 1, "大脑中动脉m1": 2, "m1段": 2, "前循环大血管": 3,
        "后循环闭塞": 3, "血管再通": 2, "血栓负荷": 2, "取栓适应证": 3,
        "取栓时间窗": 3, "24小时": 1,
    },
    "blood_pressure": {
        "血压": 3, "收缩压": 3, "舒张压": 3, "降压": 3, "高血压": 2,
        "目标血压": 3, "血压管理": 3, "硝普钠": 3, "拉贝洛尔": 3,
        "尼卡地平": 3, "乌拉地尔": 3, "低血压": 2, "血压变异性": 2,
    },
    "etiology": {
        "病因": 3, "发病机制": 2, "房颤": 3, "心房颤动": 3, "心源性": 3,
        "动脉粥样硬化": 3, "栓塞": 2, "toast": 3, "病因分型": 3,
        "危险因素": 2, "卵圆孔未闭": 3, "夹层": 2, "高凝": 2, "感染性心内膜炎": 3,
    },
    "secondary_prevention": {
        "二级预防": 3, "预防": 2, "抗血小板": 3, "他汀": 3, "降脂": 3,
        "抗凝": 3, "复发": 3, "再发": 3, "生活方式": 2, "戒烟": 2,
        "随访": 2, "血压控制": 2, "血糖控制": 2, "危险因素管理": 3,
        "防复发": 3, "长期管理": 2,
    },
}

# ═══════════════════════════════════════════════════════════════
# 5. 年份 / 权威 提取
# ═══════════════════════════════════════════════════════════════

_YEAR_PATTERN = re.compile(r"(19\d{2}|20\d{2})")

# 权威等级：指南/规范/共识 > 教材 > 其他
AUTHORITY_GUIDELINE = "guideline"
AUTHORITY_TEXTBOOK = "textbook"
AUTHORITY_GENERIC = "generic"
AUTHORITY_RANK = {
    AUTHORITY_GUIDELINE: 1.0,
    AUTHORITY_TEXTBOOK: 0.8,
    AUTHORITY_GENERIC: 0.5,
}

_GUIDELINE_HINTS = (
    "指南", "共识", "规范", "防治", "guideline", "consensus",
)
_TEXTBOOK_HINTS = (
    "教材", "neuroanatomy", "textbook", "blumenfeld", "临床病例",
    "through clinical cases", "解剖",
)


def extract_year(source: str) -> Optional[int]:
    """从文件名/来源字符串提取发布年份；无则 None。"""
    if not source:
        return None
    matches = _YEAR_PATTERN.findall(source)
    if not matches:
        return None
    years = [int(y) for y in matches]
    return max(years)


def extract_authority(source: str) -> str:
    """从文件名判断文献权威等级：guideline / textbook / generic。"""
    if not source:
        return AUTHORITY_GENERIC
    lowered = source.lower()
    if any(hint.lower() in lowered for hint in _GUIDELINE_HINTS):
        return AUTHORITY_GUIDELINE
    if any(hint.lower() in lowered for hint in _TEXTBOOK_HINTS):
        return AUTHORITY_TEXTBOOK
    return AUTHORITY_GENERIC


# ═══════════════════════════════════════════════════════════════
# 6. 证据级别 / 时间窗 提取
# ═══════════════════════════════════════════════════════════════

# 匹配 "证据级别：A" / "推荐级别：I" / "推荐意见：Ⅰ级推荐，A级证据" 等
_EVIDENCE_LEVEL_PATTERN = re.compile(
    r"(?:证据级别|证据等级|推荐级别|推荐等级|推荐强度)"
    r"[：:、\s]*"
    r"([AIⅠ-Ⅳa-d一二三四1234]{1,2}级?)",
    re.IGNORECASE,
)
_TIME_WINDOW_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(小时|h|hr|hours|分钟|min|mins|天|d)(?![a-z])",
    re.IGNORECASE,
)


def detect_evidence_level(text: str) -> Optional[str]:
    """提取证据级别/推荐级别字符串；无则 None。"""
    if not text:
        return None
    match = _EVIDENCE_LEVEL_PATTERN.search(text)
    return match.group(1).upper() if match else None


def detect_time_window(text: str) -> Optional[str]:
    """提取治疗时间窗（如 '4.5小时'、'6h'）；无则 None。"""
    if not text:
        return None
    match = _TIME_WINDOW_PATTERN.search(text)
    if not match:
        return None
    value, unit = match.group(1), match.group(2).lower()
    unit_cn = {"小时": "小时", "h": "小时", "hr": "小时", "hours": "小时",
               "分钟": "分钟", "min": "分钟", "mins": "分钟",
               "天": "天", "d": "天"}.get(unit, unit)
    return f"{value}{unit_cn}"


# ═══════════════════════════════════════════════════════════════
# 7. 分类主函数
# ═══════════════════════════════════════════════════════════════


def classify_subtopic(text: str, source: str = "") -> str:
    """
    对 chunk 文本做 12 类 subtopic 分类（关键词加权打分）。

    - 文档先验（解剖教材 → anatomy 加分）用于弱化单句误分类。
    - 返回 subtopic key，见 SUBTOPICS。
    """
    if not text:
        return "diagnosis"  # 兜底默认
    lowered = text.lower()

    scores: Dict[str, int] = {}
    for subtopic, keywords in _SUBTOPIC_KEYWORDS.items():
        score = 0
        for keyword, weight in keywords.items():
            if keyword.lower() in lowered:
                score += weight
        if score > 0:
            scores[subtopic] = score

    # 文档级先验：整篇文档主题倾向
    source_lower = (source or "").lower()
    prior_scores = {
        "anatomy": 0, "pathophysiology": 0, "etiology": 0, "clinical": 0,
        "diagnosis": 0, "imaging": 0, "reperfusion": 0, "medication": 0,
        "intervention": 0, "complication": 0, "prevention": 0, "rehabilitation": 0,
    }
    for collection, hints in _SOURCE_PRIOR.items():
        hint_score = 0
        for hint, weight in hints.items():
            if hint.lower() in source_lower:
                hint_score += weight
        if hint_score:
            # 文档先验 → 该 collection 下的 subtopic 共享加分
            for subtopic, col in SUBTOPIC_COLLECTION.items():
                if col == collection:
                    prior_scores[subtopic] = hint_score

    for subtopic in scores:
        scores[subtopic] += prior_scores.get(subtopic, 0)

    if not scores:
        # 无关键词命中：用文档先验决定
        best_prior = max(prior_scores, key=prior_scores.get)
        if prior_scores[best_prior] > 0:
            return best_prior
        return "diagnosis"

    best = max(scores, key=lambda k: (scores[k], _SUBTOPIC_TIE_ORDER(k)))
    return best


def _SUBTOPIC_TIE_ORDER(key: str) -> int:
    """同分时的稳定优先级（更特异的主题优先，避免药物治疗抢占二级预防等）。"""
    order = {
        "reperfusion": 0, "intervention": 1, "medication": 2,
        "prevention": 3, "rehabilitation": 4, "complication": 5,
        "etiology": 6, "pathophysiology": 7, "imaging": 8,
        "diagnosis": 9, "clinical": 10, "anatomy": 11,
    }
    return order.get(key, 12)


def extract_interventions(text: str) -> List[str]:
    """
    提取 chunk 中命中的干预类别（14 类），按命中强度排序去重。

    返回标准干预 key 列表，如 ["iv_thrombolysis", "antiplatelet"]。
    """
    if not text:
        return []
    lowered = text.lower()
    hits: Dict[str, int] = {}
    for intervention, keywords in INTERVENTION_KEYWORDS.items():
        score = 0
        for keyword, weight in keywords.items():
            if keyword.lower() in lowered:
                score += weight
        if score > 0:
            hits[intervention] = score
    return [k for k, _ in sorted(hits.items(), key=lambda item: item[1], reverse=True)]


def assign_decision_node(text: str) -> List[str]:
    """
    分配 chunk 对应的临床决策节点（按临床优先级顺序返回命中的节点）。

    优先级：再灌注 → LVO → 血压 → 病因 → 二级预防。
    """
    if not text:
        return []
    lowered = text.lower()
    hits = []
    for node in DECISION_NODES:
        score = 0
        for keyword, weight in DECISION_NODE_KEYWORDS[node].items():
            if keyword.lower() in lowered:
                score += weight
        if score > 0:
            hits.append(node)
    return hits


def _meta_safe(value):
    """
    chromadb 安全序列化：metadata 值必须是 str/int/float/bool 或非空 list。
    - None → ""；空 list → ""（chromadb 拒绝空 list）；非空 list 保持。
    """
    if value is None:
        return ""
    if isinstance(value, list):
        return value if value else ""
    return value


def tag_chunk(
    text: str,
    metadata: Optional[Dict] = None,
) -> Dict:
    """
    统一标签入口：对一段 chunk 文本生成全部结构化标签。

    参数:
        text: chunk 正文
        metadata: 已有 metadata（含 source / page 等），会被原地增强

    返回:
        metadata 字典（新增 subtopic/collection/interventions/decision_node/... 字段）。
        注意：返回的是 metadata 的副本（dict(metadata or {})），调用方需接收返回值
        并写回 chunk.metadata，否则标签丢失。
    """
    metadata = dict(metadata or {})
    source = metadata.get("source", "")

    subtopic = classify_subtopic(text, source=source)
    collection = SUBTOPIC_COLLECTION.get(subtopic, "guideline")
    interventions = extract_interventions(text)
    decision_nodes = assign_decision_node(text)

    year = extract_year(str(source))
    authority = extract_authority(str(source))

    metadata.update({
        "subtopic": subtopic,
        "subtopic_name": SUBTOPIC_NAMES_CN.get(subtopic, subtopic),
        "collection": collection,
        "interventions": _meta_safe(interventions),
        "decision_node": _meta_safe(decision_nodes),
        "time_window": _meta_safe(detect_time_window(text)),
        "evidence_level": _meta_safe(detect_evidence_level(text)),
        "year": _meta_safe(year),
        "authority": authority,
        "authority_level": AUTHORITY_RANK.get(authority, 0.5),
    })
    return metadata


def partition_chunks_by_collection(chunks) -> Dict[str, list]:
    """
    为每个 chunk 打结构化标签并按 collection 物理分库（纯函数，可单测）。

    接受任意带 .page_content 与 .metadata 属性的对象（如 langchain Document）。
    注意：tag_chunk 返回 metadata 副本，此处必须接收返回值并写回 chunk，
    否则标签丢失、所有 chunk 都会落进默认的 guideline 库，物理隔离失效。

    返回:
        {collection_name: [chunk, ...]}，collection 见 COLLECTIONS。
    """
    collection_chunks: Dict[str, list] = {c: [] for c in COLLECTIONS}
    for chunk in chunks:
        try:
            chunk.metadata = tag_chunk(chunk.page_content, chunk.metadata)
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning(f"⚠️ chunk 打标签失败，默认 guideline 库: {exc}")
            chunk.metadata.setdefault("collection", "guideline")
        collection = chunk.metadata.get("collection", "guideline")
        if collection not in collection_chunks:
            collection = "guideline"
        collection_chunks[collection].append(chunk)
    return collection_chunks
