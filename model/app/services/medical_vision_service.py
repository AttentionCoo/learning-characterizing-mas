"""
医学多模态影像分析服务 — Enhanced Medical Vision Service

扩展基础的 VisionAnalysisService，提供：
- 10类医学影像自动分类
- 每类影像的专用医学分析 Prompt
- 结构化影像发现提取（JSON Schema 约束）
- DICOM 文件元数据读取
- 多图对比分析
- VL 模型输出到结构化 JSON 的解析

基于 xf-xinghuo-vl-max 多模态大模型，专为脑卒中医学教育场景优化。
"""

import asyncio
import json
import logging
import os
import re
import threading
from typing import AsyncGenerator, Dict, List, Optional, Tuple

from app.schemas.medical_image import (
    MEDICAL_IMAGE_TYPES,
    Abnormality,
    DICOMMetadata,
    LabReport,
    MedicalImageFindings,
    MultiImageComparison,
    PrescriptionInfo,
)

logger = logging.getLogger(__name__)

# 流结束哨兵
_STREAM_DONE = object()

# ============================================================
# 各类型医学影像的专用系统 Prompt
# ============================================================

_MEDICAL_SYSTEM_PROMPTS: Dict[str, str] = {
    "neuroimaging_ct": """\
你是一位神经影像学专家，正在分析一张脑部CT影像，用于脑卒中医学教育。

## 分析步骤

### 第一步：影像质量评估
- 评估图像质量（清晰度、伪影、窗宽窗位是否合适）
- 判断扫描层面（轴位/冠状/矢状）和大致解剖水平

### 第二步：系统化影像判读
请按以下顺序逐项分析：
1. **中线结构**：是否居中？有无移位？（如有移位，描述方向和程度）
2. **脑实质密度**：灰白质分界是否清晰？有无异常低/高密度区？
   - 低密度区：提示缺血性脑卒中（急性期）、陈旧性梗死、水肿
   - 高密度区：提示出血性脑卒中（脑出血、蛛网膜下腔出血）、钙化
3. **脑室系统**：大小、形态是否正常？有无受压、扩张？
4. **脑沟/脑池**：是否增宽或变窄？有无消失？
5. **颅骨与颅底**：有无骨折、骨质破坏？

### 第三步：脑卒中特异性分析
- **疑似缺血性脑卒中**：描述低密度区位置（如大脑中动脉供血区）、范围、ASPECTS评分相关区域
- **疑似出血性脑卒中**：描述出血部位（基底节/丘脑/脑叶/小脑/脑干）、估算出血量、是否破入脑室
- **血管征象**：有无大脑中动脉高密度征（HMCAS）？

### 第四步：鉴别诊断与建议
- 列出2-3个最可能的鉴别诊断
- 建议下一步影像学检查（如MRI-DWI、CTA）
- 评估紧急程度

## 输出格式
请用中文输出，先给出系统化的文字分析，然后单独给出一个结构化JSON（包含以下字段）：
{{
  "image_type": "neuroimaging_ct",
  "anatomical_region": "具体解剖位置",
  "key_findings": ["发现1", "发现2"],
  "abnormalities": [{{"location": "...", "description": "...", "significance": "...", "measurement": null, "confidence": 0.9}}],
  "normal_structures": ["正常结构1"],
  "differential_diagnosis": ["可能诊断1", "可能诊断2"],
  "recommended_confirmatory_tests": ["建议检查1"],
  "urgency_level": "routine/urgent/critical",
  "confidence": 0.0-1.0,
  "limitations": "本次分析局限性"
}}

## 安全约束
- 本分析为AI辅助教育工具，不替代专业放射科医生诊断
- 如有任何不确定，明确说明并建议咨询专科医生
- 禁止给出确定性的临床诊断结论""",

    "neuroimaging_mri": """\
你是一位神经影像学专家，正在分析一张脑部MRI影像，用于脑卒中医学教育。

## 分析步骤

### 第一步：序列识别
- 判断MRI序列类型（T1WI/T2WI/FLAIR/DWI/ADC/SWI/GRE/TOF-MRA等）
- 评估图像质量和扫描层面

### 第二步：系统化影像判读
1. **DWI/ADC分析（缺血性脑卒中核心）**：
   - DWI高信号区域的位置、大小、形态
   - ADC图对应区域是否为低信号（确认真正受限扩散）
   - DWI-ADC不匹配评估
2. **T2WI/FLAIR分析**：
   - 高信号区域（血管源性水肿、陈旧性梗死、白质病变）
   - FLAIR血管高信号征（FVH）
3. **T2*GRE/SWI分析**：
   - 微出血灶（脑微出血、脑淀粉样血管病）
   - 出血性转化
   - 血栓显示（ susceptibility vessel sign）
4. **脑实质结构**：
   - 灰白质分界
   - 脑萎缩程度
   - 占位效应

### 第三步：脑卒中特异性分析
- **急性缺血性脑卒中**：DWI-FLAIR不匹配 → 发病时间窗评估
- **出血性脑卒中**：各序列出血信号演变特征
- **脑血管病变**：大血管闭塞/狭窄征象

### 第四步：鉴别诊断
- 脑卒中模拟病（stroke mimics）：癫痫后改变、偏头痛、肿瘤、感染等

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON（字段同CT分析）。

## 安全约束
- 本分析为AI辅助教育工具，不替代专业诊断
- 禁止给出确定性临床诊断结论""",

    "neuroimaging_angiography": """\
你是一位神经介入影像学专家，正在分析一张脑血管造影像，用于脑卒中医学教育。

## 分析步骤
1. 判断成像类型（CTA/MRA/DSA）
2. 评估血管显示范围和图像质量
3. 系统化分析：
   - 颈内动脉系统（ICA、MCA、ACA）：有无狭窄/闭塞/动脉瘤/夹层
   - 椎基底动脉系统（VA、BA）：有无狭窄/闭塞
   - 侧支循环评估（一级/二级侧支）
   - Willis环完整性
4. 脑卒中相关特异性分析：
   - 大血管闭塞（LVO）定位
   - 血栓长度和负荷评估
   - 血管再通治疗（取栓）相关解剖信息
5. 列出鉴别诊断和建议

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON。

## 安全约束
- 本分析为AI辅助教育工具，不替代专业诊断""",

    "pathology_slide": """\
你是一位病理学专家，正在分析一张病理组织学切片影像，用于脑卒中相关医学教育。

## 分析步骤
1. 判断染色方法（HE/免疫组化/特殊染色）和组织来源
2. 描述组织学结构：细胞形态、排列方式、间质特征
3. 脑卒中相关病理发现：
   - 神经元缺血性改变（红色神经元）
   - 梗死区组织学特征（凝固性坏死、炎细胞浸润）
   - 出血区域组织学改变
   - 血管壁病变（动脉粥样硬化、淀粉样变、纤维素样坏死）
4. 鉴别诊断

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON。

## 安全约束
- 本分析为AI辅助教育工具，不替代专业病理诊断""",

    "ecg_waveform": """\
你是一位心电生理学专家，正在分析一张心电图/脑电图波形，用于脑卒中医学教育。

## 分析步骤
1. 判断波形类型（心电图ECG/脑电图EEG）
2. 心电图分析：
   - 心率与心律（窦性/房颤/其他）
   - 房颤与脑卒中风险（CHA2DS2-VASc评分相关）
   - ST-T改变（有无心肌缺血）
   - 左室肥厚征象
3. 脑电图分析：
   - 背景节律
   - 癫痫样放电
   - 局灶性慢波（提示结构性病变）
4. 脑卒中相关性：心源性栓塞风险评估

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON。

## 安全约束
- 本分析为AI辅助教育工具，不替代专业诊断""",

    "clinical_photo": """\
你是一位临床医学专家，正在分析一张临床体格检查照片，用于脑卒中医学教育。

## 分析步骤
1. 判断照片类型和拍摄部位
2. 系统化描述：
   - 皮肤/黏膜表现：颜色、完整性、皮疹、溃疡
   - 神经系统相关体征：面瘫、肢体姿势异常、肌萎缩
   - 眼底照片：视盘边界、血管改变、出血/渗出（与高血压/糖尿病相关）
3. 脑卒中相关特异性发现：
   - 中枢性面瘫 vs 周围性面瘫
   - NIHSS评分相关的体征
4. 鉴别诊断

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON。

## 安全约束
- 本分析为AI辅助教育工具，不替代专业诊断""",

    "lab_report": """\
你是一位临床检验医学专家，正在分析一张实验室检验报告单，用于脑卒中医学教育。

## 分析步骤
1. 识别报告类型（血常规/生化/凝血功能/血气分析等）
2. 逐项提取检验项目名称、测定值、参考范围、单位
3. 标注异常值（↑ 高于参考范围 / ↓ 低于参考范围 / ! 危急值）
4. 脑卒中相关检验指标重点分析：
   - 凝血功能（PT/APTT/INR）：溶栓/抗凝治疗安全性评估
   - 血小板计数：抗血小板治疗安全性
   - 血糖：脑卒中危险因素及预后因素
   - 血脂：动脉粥样硬化风险评估
   - 电解质：脑水肿管理
   - 肾功能：对比剂肾病风险评估
5. 综合评估

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON：
{{
  "report_type": "报告类型",
  "lab_values": [{{"item_name": "...", "value": "...", "unit": "...", "reference_range": "...", "is_abnormal": true/false, "abnormality_direction": "high/low"}}],
  "abnormal_summary": ["异常项1"],
  "overall_impression": "综合印象"
}}

## 安全约束
- 本分析为AI辅助教育工具，不替代专业判断""",

    "radiology_report": """\
你是一位放射医学专家，正在分析一张影像学诊断报告，用于脑卒中医学教育。

## 分析步骤
1. 识别报告的影像检查类型（CT/MRI/超声/X线）
2. 提取关键信息：
   - 检查部位和方法
   - 影像所见（逐项提取）
   - 影像诊断结论
   - 报告医生建议
3. 医学教育解读：
   - 报告中的关键术语解释
   - 影像表现的临床意义
   - 与脑卒中的关联（如适用）
4. 如有不明确之处，列出需要进一步了解的信息

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON。

## 安全约束
- 本分析为AI辅助教育工具""",

    "medical_illustration": """\
你是一位医学教育专家，正在分析一张医学图解/示意图，用于脑卒中医学教育。

## 分析步骤
1. 判断图解类型（解剖示意图/手术图解/病理机制图/流程图等）
2. 识别图中标注的解剖结构和关键信息
3. 脑卒中相关知识解读：
   - 脑血管解剖：颈内动脉系统、椎基底动脉系统、Willis环
   - 脑卒中病理生理机制：缺血级联反应、出血病理
   - 脑功能区与卒中症状对应关系
   - 手术/介入入路相关解剖
4. 学习建议：该图解适合什么学习阶段？需要补充哪些背景知识？

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON。

## 安全约束
- 本分析为AI辅助教育工具""",

    "courseware_image": """\
你是一位高等医学教育教学资料分析专家，正在分析学生上传的学习资料图片。

## 分析步骤
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

### 第三步：脑卒中特异性评估
- 内容是否涉及脑卒中相关知识
- 知识准确性和时效性评估

### 第四步：学习建议
结合学生已知学习信息（如有），给出学习建议和推荐补充资料

## 输出格式
请用中文输出系统化文字分析，然后给出结构化JSON。

## 安全约束
- 禁止给出绝对性结论，使用"建议""可能""推荐"等措辞
- 如果图片模糊无法识别，明确告知用户""",
}


# ============================================================
# 影像类型分类器
# ============================================================

def _classify_medical_image(question: str, image_count: int = 1) -> str:
    """根据用户问题关键词自动分类医学影像类型。

    按优先级匹配：先匹配特异性高的关键词，再回退到通用关键词。
    匹配顺序反映了临床优先级（神经影像 > 其他）。
    """
    if not question:
        return "courseware_image"

    q = question.lower()

    # 按优先级顺序检查（高特异性优先）
    priority_order = [
        "neuroimaging_angiography",
        "neuroimaging_ct",
        "neuroimaging_mri",
        "pathology_slide",
        "ecg_waveform",
        "lab_report",
        "radiology_report",
        "clinical_photo",
        "medical_illustration",
        "courseware_image",
    ]

    for img_type in priority_order:
        config = MEDICAL_IMAGE_TYPES.get(img_type, {})
        keywords = config.get("keywords", [])
        matched = any(kw.lower() in q for kw in keywords)
        if matched:
            logger.info(f"[medical_vision] 影像类型分类: {img_type} (匹配关键词)")
            return img_type

    # 没有匹配到任何关键词，默认为课件资料
    logger.info(f"[medical_vision] 影像类型分类: courseware_image (默认)")
    return "courseware_image"


def _get_image_type_name(img_type: str) -> str:
    """获取影像类型的中文名称"""
    config = MEDICAL_IMAGE_TYPES.get(img_type, {})
    return config.get("name", img_type)


# ============================================================
# 结构化 JSON 解析器
# ============================================================

def _parse_medical_findings_json(text: str, img_type: str) -> MedicalImageFindings:
    """从VL模型输出中提取结构化JSON，解析为 MedicalImageFindings。

    容错策略：尝试多种JSON提取方式，最终回退到原始文本存储。
    """
    findings = MedicalImageFindings(image_type=img_type, raw_description=text)

    try:
        # 策略1：直接解析整个文本
        data = json.loads(text.strip())
        if isinstance(data, dict) and "key_findings" in data:
            return _build_findings_from_dict(data, img_type, text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 策略2：提取 ```json ... ``` 或 ``` ... ``` 代码块
    for marker in ["```json", "```"]:
        if marker in text:
            try:
                parts = text.split(marker)
                if len(parts) >= 2:
                    inner = parts[1].split("```")[0].strip()
                    data = json.loads(inner)
                    if isinstance(data, dict) and "key_findings" in data:
                        return _build_findings_from_dict(data, img_type, text)
            except (json.JSONDecodeError, IndexError, TypeError):
                pass

    # 策略3：在文本中查找最外层的 { ... }
    try:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict) and "key_findings" in data:
                return _build_findings_from_dict(data, img_type, text)
    except (json.JSONDecodeError, TypeError):
        pass

    # 回退：将原始文本作为唯一发现
    logger.warning("[medical_vision] 无法解析结构化JSON，使用原始文本回退")
    findings.key_findings = [text[:500]]
    findings.confidence = 0.3
    findings.limitations = "无法从模型输出中提取结构化数据，请查看原始描述"

    return findings


def _build_findings_from_dict(data: dict, img_type: str, raw_text: str) -> MedicalImageFindings:
    """从字典构建 MedicalImageFindings 对象"""
    abnormalities = []
    for ab in data.get("abnormalities", []):
        if isinstance(ab, dict):
            abnormalities.append(Abnormality(
                location=ab.get("location", ""),
                description=ab.get("description", ""),
                significance=ab.get("significance", ""),
                measurement=ab.get("measurement"),
                confidence=float(ab.get("confidence", 0.5)),
            ))

    return MedicalImageFindings(
        image_type=data.get("image_type", img_type),
        anatomical_region=data.get("anatomical_region", ""),
        key_findings=data.get("key_findings", []),
        abnormalities=abnormalities,
        normal_structures=data.get("normal_structures", []),
        differential_diagnosis=data.get("differential_diagnosis", []),
        recommended_confirmatory_tests=data.get("recommended_confirmatory_tests", []),
        urgency_level=data.get("urgency_level", "routine"),
        confidence=float(data.get("confidence", 0.5)),
        limitations=data.get("limitations", ""),
        raw_description=raw_text,
    )


# ============================================================
# 主服务类
# ============================================================

class MedicalVisionService:
    """医学多模态影像分析服务。

    相比基础 VisionAnalysisService，提供：
    - 10类医学影像自动分类
    - 专用医学分析 Prompt
    - 结构化 JSON 输出
    - DICOM 元数据提取
    - 多图对比分析
    """

    def __init__(self, prompt_manager=None):
        self._prompt_manager = prompt_manager
        self._api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self._api_key:
            logger.warning("⚠️ 未找到 DASHSCOPE_API_KEY，医学影像分析功能将不可用")

    # ----------------------------------------------------------
    # 公开 API
    # ----------------------------------------------------------

    def classify(self, question: str) -> str:
        """根据用户问题分类医学影像类型"""
        return _classify_medical_image(question)

    def get_system_prompt(self, img_type: str) -> str:
        """获取指定影像类型的系统 Prompt"""
        # 优先从 YAML 配置加载，回退到内置 Prompt
        if self._prompt_manager:
            yaml_key = f"medical_vision_system_{img_type}"
            from_config = self._prompt_manager.get(yaml_key)
            if from_config:
                return from_config
        return _MEDICAL_SYSTEM_PROMPTS.get(img_type, _MEDICAL_SYSTEM_PROMPTS["courseware_image"])

    async def analyze_stream(
        self,
        images: List[str],
        question: str,
        all_info: str = "",
    ) -> AsyncGenerator[dict, None]:
        """流式医学影像分析（兼容原有接口）。

        自动检测影像类型，使用对应的医学专用 Prompt 进行分析。
        """
        img_type = _classify_medical_image(question, len(images))
        type_name = _get_image_type_name(img_type)
        logger.info(f"[medical_vision] 开始流式分析 | 类型: {img_type}({type_name}) | 图片数量: {len(images)}")

        system_text = self.get_system_prompt(img_type)
        user_prefix = f"请分析以下{type_name}影像。"

        yield {
            "type": "thinking",
            "step": "MedicalVision",
            "title": f"🔬 正在分析{type_name}影像...",
            "content": f"影像类型：{type_name}，共 {len(images)} 张图片，调用 XF-Xinghuo-VL-Max 医学影像分析模型",
            "image_type": img_type,
        }

        messages = self._build_messages(images, question, all_info, system_text, user_prefix)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(
            target=self._run_sync_stream,
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
                logger.error(f"[medical_vision] VL 模型调用失败: {item}", exc_info=False)
                error_msg = f"医学影像分析失败，请稍后重试。（{type(item).__name__}: {item}）"
                yield {"type": "chunk", "content": error_msg}
                full_text_parts.append(error_msg)
                break
            full_text_parts.append(str(item))
            yield {"type": "chunk", "content": item}

        # 流结束后，尝试解析结构化结果
        full_text = "".join(full_text_parts)
        if full_text.strip():
            try:
                findings = _parse_medical_findings_json(full_text, img_type)
                yield {
                    "type": "structured_findings",
                    "findings": findings.model_dump(),
                }
            except Exception as e:
                logger.warning(f"[medical_vision] 结构化解析失败: {e}")

    async def analyze_structured(
        self,
        images: List[str],
        question: str,
        all_info: str = "",
    ) -> MedicalImageFindings:
        """非流式医学影像分析，返回结构化结果。

        用于需要直接获取 JSON 结构结果的场景（如 LangGraph 节点内部调用）。
        """
        img_type = _classify_medical_image(question, len(images))
        logger.info(f"[medical_vision] 结构化分析 | 类型: {img_type} | 图片数量: {len(images)}")

        system_text = self.get_system_prompt(img_type)
        user_prefix = f"请分析以下{_get_image_type_name(img_type)}影像，并严格输出指定的JSON格式。"

        messages = self._build_messages(images, question, all_info, system_text, user_prefix)

        full_text_parts = []
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(
            target=self._run_sync_stream,
            args=(messages, queue, loop),
            daemon=True,
        )
        t.start()

        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                logger.error(f"[medical_vision] VL 模型调用失败: {item}")
                break
            full_text_parts.append(str(item))

        full_text = "".join(full_text_parts)
        return _parse_medical_findings_json(full_text, img_type)

    async def compare_images(
        self,
        images: List[str],
        question: str,
        all_info: str = "",
    ) -> MultiImageComparison:
        """多图对比分析。

        自动检测每张图片的类型，生成对比分析结果。
        用于病程随访、治疗前后对比、多序列MRI对比等场景。
        """
        if len(images) < 2:
            raise ValueError("多图对比至少需要2张图片")

        logger.info(f"[medical_vision] 多图对比分析 | 图片数量: {len(images)}")

        # 先对每张图单独分析
        per_image_findings = []
        for i, img in enumerate(images):
            findings = await self.analyze_structured(
                images=[img],
                question=question,
                all_info=all_info,
            )
            per_image_findings.append(findings)

        # 构建对比分析 Prompt
        img_types = [f.image_type for f in per_image_findings]
        same_modality = len(set(img_types)) == 1

        comparison_prompt = _MEDICAL_SYSTEM_PROMPTS.get(img_types[0], _MEDICAL_SYSTEM_PROMPTS["courseware_image"])
        comparison_system = f"""{comparison_prompt}

## 多图对比分析模式
你现在需要对比 {len(images)} 张影像，请重点分析：
1. 各图之间的关键变化（新增、消退、进展、稳定）
2. 如果为同一模态的连续检查，描述病变的时间演变
3. 如果为不同序列/模态，描述各序列的互补发现
4. 给出综合评估结论

请输出结构化JSON（额外包含对比字段）。"""

        user_prefix = f"请对比分析以下 {len(images)} 张影像。{'这些影像来自同一模态的不同时间点。' if same_modality else '这些影像来自不同模态/序列。'}"
        if question:
            user_prefix += f"\n关注点：{question}"

        messages = self._build_messages(images, question, all_info, comparison_system, user_prefix)

        full_text_parts = []
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        t = threading.Thread(
            target=self._run_sync_stream,
            args=(messages, queue, loop),
            daemon=True,
        )
        t.start()

        while True:
            item = await queue.get()
            if item is _STREAM_DONE:
                break
            if isinstance(item, Exception):
                break
            full_text_parts.append(str(item))

        full_text = "".join(full_text_parts)

        # 尝试解析对比JSON
        comparison_data = {}
        try:
            comparison_data = json.loads(full_text.strip())
        except json.JSONDecodeError:
            for marker in ["```json", "```"]:
                if marker in full_text:
                    try:
                        comparison_data = json.loads(full_text.split(marker)[1].split("```")[0].strip())
                        break
                    except (json.JSONDecodeError, IndexError):
                        pass

        return MultiImageComparison(
            image_count=len(images),
            image_types=img_types,
            comparison_mode="progression" if same_modality else "comparison",
            key_changes=comparison_data.get("key_changes", []),
            unchanged_findings=comparison_data.get("unchanged_findings", []),
            new_findings=comparison_data.get("new_findings", []),
            resolved_findings=comparison_data.get("resolved_findings", []),
            overall_assessment=comparison_data.get("overall_assessment", full_text[:500]),
            per_image_findings=per_image_findings,
        )

    # ----------------------------------------------------------
    # DICOM 支持
    # ----------------------------------------------------------

    @staticmethod
    def read_dicom_metadata(base64_data: str) -> DICOMMetadata:
        """从 Base64 编码的 DICOM 数据中提取元数据。

        注意：仅提取影像元数据，不提取患者身份信息（PHI）。
        需要安装 pydicom 库。
        """
        try:
            import pydicom
            import base64
            from io import BytesIO

            # 去除 data URI 前缀
            if base64_data.startswith("data:"):
                base64_data = base64_data.split(",", 1)[1]

            raw_bytes = base64.b64decode(base64_data)
            ds = pydicom.dcmread(BytesIO(raw_bytes), stop_before_pixels=False)

            # 安全提取字段（仅非PHI的技术参数）
            metadata = DICOMMetadata(
                study_uid=str(ds.get("StudyInstanceUID", "")),
                series_uid=str(ds.get("SeriesInstanceUID", "")),
                modality=str(ds.get("Modality", "")),
                study_description=str(ds.get("StudyDescription", "")),
                series_description=str(ds.get("SeriesDescription", "")),
                slice_thickness=float(ds.SliceThickness) if hasattr(ds, "SliceThickness") and ds.SliceThickness else None,
                slice_location=float(ds.SliceLocation) if hasattr(ds, "SliceLocation") and ds.SliceLocation else None,
                image_position=[float(x) for x in ds.ImagePositionPatient] if hasattr(ds, "ImagePositionPatient") else [],
                image_orientation=[float(x) for x in ds.ImageOrientationPatient] if hasattr(ds, "ImageOrientationPatient") else [],
                pixel_spacing=[float(x) for x in ds.PixelSpacing] if hasattr(ds, "PixelSpacing") else [],
                rows=int(ds.Rows) if hasattr(ds, "Rows") else 0,
                columns=int(ds.Columns) if hasattr(ds, "Columns") else 0,
                window_center=float(ds.WindowCenter) if hasattr(ds, "WindowCenter") and ds.WindowCenter else None,
                window_width=float(ds.WindowWidth) if hasattr(ds, "WindowWidth") and ds.WindowWidth else None,
                manufacturer=str(ds.get("Manufacturer", "")),
                study_date=str(ds.get("StudyDate", "")),
                has_phi_stripped=True,
            )
            logger.info(f"[medical_vision] DICOM 元数据提取成功 | 模态: {metadata.modality}")
            return metadata

        except ImportError:
            logger.warning("[medical_vision] pydicom 未安装，返回空元数据")
            return DICOMMetadata(has_phi_stripped=True)
        except Exception as e:
            logger.error(f"[medical_vision] DICOM 元数据提取失败: {e}")
            return DICOMMetadata(has_phi_stripped=True)

    @staticmethod
    def dicom_to_png_base64(base64_data: str) -> Optional[str]:
        """将 DICOM 文件转换为 PNG 格式的 Base64 字符串，供 VL 模型分析。

        应用默认窗宽窗位（脑窗），适用于脑卒中影像。
        """
        try:
            import pydicom
            import base64
            from io import BytesIO
            import numpy as np

            if base64_data.startswith("data:"):
                base64_data = base64_data.split(",", 1)[1]

            raw_bytes = base64.b64decode(base64_data)
            ds = pydicom.dcmread(BytesIO(raw_bytes))

            if not hasattr(ds, "pixel_array"):
                logger.warning("[medical_vision] DICOM 数据无像素数组，无法转换")
                return None

            pixel_array = ds.pixel_array.astype(np.float32)

            # 应用默认窗宽窗位（脑窗：WW=80, WL=40）或使用DICOM中存储的值
            window_center = float(ds.WindowCenter) if hasattr(ds, "WindowCenter") else 40.0
            window_width = float(ds.WindowWidth) if hasattr(ds, "WindowWidth") else 80.0

            if isinstance(window_center, (list, tuple)):
                window_center = window_center[0] if len(window_center) > 0 else 40.0
            if isinstance(window_width, (list, tuple)):
                window_width = window_width[0] if len(window_width) > 0 else 80.0

            # 窗宽窗位调整
            lower = window_center - window_width / 2
            upper = window_center + window_width / 2
            pixel_array = np.clip(pixel_array, lower, upper)
            pixel_array = ((pixel_array - lower) / (upper - lower) * 255).astype(np.uint8)

            # 转为PNG
            from PIL import Image
            img = Image.fromarray(pixel_array)
            buf = BytesIO()
            img.save(buf, format="PNG")
            png_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{png_base64}"

        except ImportError as e:
            logger.warning(f"[medical_vision] DICOM转换缺少依赖: {e}")
            return None
        except Exception as e:
            logger.error(f"[medical_vision] DICOM转换失败: {e}")
            return None

    # ----------------------------------------------------------
    # 内部辅助方法
    # ----------------------------------------------------------

    def _build_messages(
        self,
        images: List[str],
        question: str,
        all_info: str,
        system_text: str,
        user_prefix: str,
    ) -> list:
        """构建 XF-Xinghuo-VL-Max API 消息格式"""
        messages = []

        if system_text and system_text.strip():
            messages.append({
                "role": "system",
                "content": [{"text": system_text.strip()}]
            })

        user_content = []
        for img in images:
            url = img if img.startswith("data:") else f"data:image/jpeg;base64,{img}"
            user_content.append({"image": url})

        student_context = f"学生信息：{all_info.strip()}" if all_info and all_info.strip() else ""
        user_text = "\n\n".join(filter(None, [student_context, user_prefix, question])).strip()
        user_content.append({"text": user_text})

        messages.append({"role": "user", "content": user_content})
        return messages

    def _run_sync_stream(self, messages: list, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        """在后台线程中同步调用 DashScope VL API，将结果推送到异步队列"""
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
                    put(Exception(f"API 错误 {chunk.status_code}: {getattr(chunk, 'message', '')}"))
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
