"""
医学多模态功能单元测试 — Medical Multimodal Unit Tests

测试覆盖：
- 医学影像类型分类准确率
- 结构化影像发现 JSON 解析
- DICOM 元数据提取
- Vision → 检索查询生成
- 多图对比模式检测
- MedicalImageFindings 模型验证
"""

import sys
import os
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.medical_image import (
    MEDICAL_IMAGE_TYPES,
    MedicalImageFindings,
    Abnormality,
    MultiImageComparison,
    LabReport,
    LabValue,
    DICOMMetadata,
)
from app.services.medical_vision_service import (
    _classify_medical_image,
    _parse_medical_findings_json,
    _get_image_type_name,
)
from app.services.vision_rag_bridge import VisionRAGBridge


# ============================================================
# 1. 医学影像类型分类测试
# ============================================================

class TestMedicalImageClassification:
    """测试医学影像类型自动分类"""

    def test_ct_classification(self):
        """CT 影像关键词应正确分类"""
        assert _classify_medical_image("请分析这张头部CT平扫") == "neuroimaging_ct"
        assert _classify_medical_image("帮我看看这个脑CT有没有出血") == "neuroimaging_ct"
        assert _classify_medical_image("This is a non-contrast CT scan") == "neuroimaging_ct"
        assert _classify_medical_image("头颅CT显示左侧基底节区高密度影") == "neuroimaging_ct"

    def test_mri_classification(self):
        """MRI 影像关键词应正确分类"""
        assert _classify_medical_image("分析DWI序列") == "neuroimaging_mri"
        assert _classify_medical_image("T2 FLAIR像显示") == "neuroimaging_mri"
        assert _classify_medical_image("这个MRI是什么问题") == "neuroimaging_mri"
        assert _classify_medical_image("磁共振T1WI加权像") == "neuroimaging_mri"

    def test_angiography_classification(self):
        """血管造影关键词应正确分类"""
        assert _classify_medical_image("CTA显示大脑中动脉闭塞") == "neuroimaging_angiography"
        assert _classify_medical_image("MRA检查结果") == "neuroimaging_angiography"
        assert _classify_medical_image("DSA血管造影") == "neuroimaging_angiography"

    def test_pathology_classification(self):
        """病理切片关键词应正确分类"""
        assert _classify_medical_image("病理切片HE染色") == "pathology_slide"
        assert _classify_medical_image("免疫组化结果") == "pathology_slide"
        assert _classify_medical_image("脑组织活检") == "pathology_slide"

    def test_ecg_classification(self):
        """心电图关键词应正确分类"""
        assert _classify_medical_image("这份心电图显示房颤") == "ecg_waveform"
        assert _classify_medical_image("ECG波形分析") == "ecg_waveform"
        assert _classify_medical_image("脑电图异常放电") == "ecg_waveform"

    def test_clinical_photo_classification(self):
        """临床照片关键词应正确分类"""
        assert _classify_medical_image("皮肤伤口照片") == "clinical_photo"
        assert _classify_medical_image("眼底照片检查") == "clinical_photo"

    def test_lab_report_classification(self):
        """检验报告关键词应正确分类"""
        assert _classify_medical_image("化验单怎么看") == "lab_report"
        assert _classify_medical_image("血常规检查结果") == "lab_report"
        assert _classify_medical_image("凝血功能报告") == "lab_report"

    def test_radiology_report_classification(self):
        """影像报告关键词应正确分类"""
        assert _classify_medical_image("这是放射报告") == "radiology_report"
        assert _classify_medical_image("超声报告单解读") == "radiology_report"

    def test_medical_illustration_classification(self):
        """医学图解关键词应正确分类"""
        assert _classify_medical_image("脑血管解剖图") == "medical_illustration"
        assert _classify_medical_image("手术示意图分析") == "medical_illustration"

    def test_courseware_default(self):
        """默认分类应为课件资料"""
        assert _classify_medical_image("分析这张图片") == "courseware_image"
        assert _classify_medical_image("") == "courseware_image"
        assert _classify_medical_image("帮我看看") == "courseware_image"

    def test_priority_matching(self):
        """高优先级关键词应覆盖低优先级"""
        # "CT血管造影" 同时匹配 CT 和 angiography，应该返回 angiography（更高优先级）
        result = _classify_medical_image("CTA血管造影提示大脑中动脉M1段闭塞")
        assert result == "neuroimaging_angiography"


# ============================================================
# 2. 结构化结果解析测试
# ============================================================

class TestStructuredFindingsParsing:
    """测试 VL 模型输出的结构化 JSON 解析"""

    def test_parse_valid_json(self):
        """有效的 JSON 应正确解析"""
        valid_json = json.dumps({
            "image_type": "neuroimaging_ct",
            "anatomical_region": "左侧基底节区",
            "key_findings": ["左侧基底节区高密度影", "中线结构居中"],
            "abnormalities": [
                {
                    "location": "左侧基底节",
                    "description": "类圆形高密度影，边界清晰",
                    "significance": "提示急性脑出血可能",
                    "measurement": "约2.5×2.0cm",
                    "confidence": 0.9,
                }
            ],
            "normal_structures": ["脑室系统形态正常"],
            "differential_diagnosis": ["高血压性脑出血", "脑淀粉样血管病相关出血"],
            "recommended_confirmatory_tests": ["头颅MRI-SWI", "脑血管CTA"],
            "urgency_level": "urgent",
            "confidence": 0.85,
            "limitations": "AI分析，需放射科医生确认",
        })

        findings = _parse_medical_findings_json(valid_json, "neuroimaging_ct")

        assert findings.image_type == "neuroimaging_ct"
        assert findings.anatomical_region == "左侧基底节区"
        assert len(findings.key_findings) == 2
        assert len(findings.abnormalities) == 1
        assert findings.abnormalities[0].location == "左侧基底节"
        assert findings.abnormalities[0].confidence == 0.9
        assert findings.urgency_level == "urgent"
        assert len(findings.differential_diagnosis) == 2
        assert len(findings.recommended_confirmatory_tests) == 2
        assert findings.confidence == 0.85

    def test_parse_json_with_markdown_wrapper(self):
        """被 markdown 代码块包裹的 JSON 应正确解析"""
        text = """这是影像分析结果...
```json
{
  "image_type": "neuroimaging_mri",
  "anatomical_region": "右侧大脑半球",
  "key_findings": ["DWI高信号，ADC低信号"],
  "abnormalities": [],
  "normal_structures": [],
  "differential_diagnosis": ["急性脑梗死"],
  "recommended_confirmatory_tests": [],
  "urgency_level": "urgent",
  "confidence": 0.9,
  "limitations": ""
}
```
以上就是分析结果。"""

        findings = _parse_medical_findings_json(text, "neuroimaging_mri")
        assert findings.image_type == "neuroimaging_mri"
        assert "急性脑梗死" in findings.differential_diagnosis

    def test_parse_json_embedded_in_text(self):
        """嵌在文本中的 JSON 应正确提取"""
        text = """分析完成。

{
  "image_type": "neuroimaging_ct",
  "anatomical_region": "脑干",
  "key_findings": ["脑干密度正常"],
  "abnormalities": [],
  "normal_structures": ["脑干", "小脑"],
  "differential_diagnosis": [],
  "recommended_confirmatory_tests": [],
  "urgency_level": "routine",
  "confidence": 0.7,
  "limitations": "图像质量一般"
}

请参考以上分析。"""

        findings = _parse_medical_findings_json(text, "neuroimaging_ct")
        assert findings.anatomical_region == "脑干"
        assert findings.urgency_level == "routine"

    def test_parse_fallback_for_unparseable_text(self):
        """无法解析的文本应回退到原始文本存储"""
        text = "这是一段无法解析为JSON的纯文本分析结果。"
        findings = _parse_medical_findings_json(text, "neuroimaging_ct")

        assert len(findings.key_findings) == 1
        assert findings.key_findings[0] == text[:500]
        assert findings.confidence == 0.3
        assert "无法" in findings.limitations or "提取" in findings.limitations

    def test_parse_empty_abnormalities(self):
        """无异常的影像应正确处理空列表"""
        text = json.dumps({
            "image_type": "neuroimaging_ct",
            "anatomical_region": "大脑",
            "key_findings": ["未见明显异常"],
            "abnormalities": [],
            "differential_diagnosis": [],
            "urgency_level": "routine",
            "confidence": 0.8,
            "limitations": "",
        })
        findings = _parse_medical_findings_json(text, "neuroimaging_ct")
        assert len(findings.abnormalities) == 0
        assert findings.urgency_level == "routine"


# ============================================================
# 3. Vision → RAG 查询生成测试
# ============================================================

class TestVisionRAGBridge:
    """测试影像发现到检索查询的转换"""

    def setup_method(self):
        self.bridge = VisionRAGBridge()

    def test_format_evidence_text(self):
        """应正确格式化证据文本"""
        findings = MedicalImageFindings(
            image_type="neuroimaging_ct",
            anatomical_region="左侧大脑中动脉供血区",
            key_findings=["低密度影，灰白质分界模糊"],
            urgency_level="urgent",
            confidence=0.85,
            limitations="图像有运动伪影",
        )
        local = [{"content": "急性脑梗死CT表现：早期征象包括...", "metadata": {"source": "急性缺血性脑卒中诊治指南"}}]

        text = self.bridge.format_evidence_for_agent(findings, local)

        assert "医学影像分析结果" in text
        assert "左侧大脑中动脉供血区" in text
        assert "本地卒中指南参考" in text
        assert "AI辅助教育说明" in text


# ============================================================
# 4. 数据模型测试
# ============================================================

class TestMedicalSchemas:
    """测试 Pydantic 数据模型"""

    def test_medical_image_findings_defaults(self):
        """MedicalImageFindings 应有正确的默认值"""
        findings = MedicalImageFindings()
        assert findings.image_type == ""
        assert findings.key_findings == []
        assert findings.abnormalities == []
        assert findings.urgency_level == "routine"
        assert findings.confidence == 0.0

    def test_abnormality_validation(self):
        """Abnormality 置信度应在 0-1 范围内（Pydantic 会验证）"""
        # 有效值
        ab = Abnormality(location="test", description="test", confidence=0.85)
        assert ab.location == "test"
        assert ab.confidence == 0.85
        # 无效值应触发验证错误
        with pytest.raises(Exception):
            Abnormality(location="test", description="test", confidence=1.5)

    def test_multi_image_comparison(self):
        """MultiImageComparison 应正确存储"""
        comparison = MultiImageComparison(
            image_count=2,
            image_types=["neuroimaging_ct", "neuroimaging_ct"],
            comparison_mode="progression",
            key_changes=["出血量减少"],
            per_image_findings=[
                MedicalImageFindings(image_type="neuroimaging_ct"),
                MedicalImageFindings(image_type="neuroimaging_ct"),
            ],
        )
        assert comparison.image_count == 2
        assert comparison.comparison_mode == "progression"
        assert len(comparison.key_changes) == 1

    def test_lab_report(self):
        """LabReport 应正确存储检验值"""
        lab = LabReport(
            report_type="血常规",
            lab_values=[
                LabValue(
                    item_name="INR",
                    value="3.5",
                    unit="",
                    reference_range="0.8-1.2",
                    is_abnormal=True,
                    abnormality_direction="critical_high",
                )
            ],
        )
        assert len(lab.lab_values) == 1
        assert lab.lab_values[0].is_abnormal is True

    def test_dicom_metadata(self):
        """DICOMMetadata 应有正确的默认值"""
        meta = DICOMMetadata()
        assert meta.has_phi_stripped is True
        assert meta.rows == 0
        assert meta.columns == 0

    def test_image_type_config(self):
        """MEDICAL_IMAGE_TYPES 应包含所有10种类型"""
        assert len(MEDICAL_IMAGE_TYPES) == 10
        for img_type in [
            "neuroimaging_ct", "neuroimaging_mri", "neuroimaging_angiography",
            "pathology_slide", "ecg_waveform", "clinical_photo",
            "lab_report", "radiology_report", "medical_illustration", "courseware_image",
        ]:
            assert img_type in MEDICAL_IMAGE_TYPES
            assert "name" in MEDICAL_IMAGE_TYPES[img_type]
            assert "keywords" in MEDICAL_IMAGE_TYPES[img_type]


# ============================================================
# 5. 工具函数测试
# ============================================================

class TestUtilityFunctions:
    """测试工具函数"""

    def test_get_image_type_name_known(self):
        """已知类型应返回中文名称"""
        assert _get_image_type_name("neuroimaging_ct") == "头部CT"
        assert _get_image_type_name("neuroimaging_mri") == "头部MRI"

    def test_get_image_type_name_unknown(self):
        """未知类型应返回原始值"""
        assert _get_image_type_name("unknown_type") == "unknown_type"
