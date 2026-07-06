"""医学多模态影像数据模型 — Medical Multimodal Imaging Data Schemas"""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


# ============================================================
# 医学影像类型枚举
# ============================================================

MEDICAL_IMAGE_TYPES = {
    "neuroimaging_ct": {
        "name": "头部CT",
        "keywords": ["CT", "计算机断层扫描", "脑CT", "头颅CT", "平扫", "ct scan", "computed tomography", "non-contrast ct", "ncct"],
        "description": "脑部计算机断层扫描影像",
    },
    "neuroimaging_mri": {
        "name": "头部MRI",
        "keywords": ["MRI", "磁共振", "核磁共振", "DWI", "T1", "T2", "FLAIR", "SWI", "GRE", "T1WI", "T2WI", "mri", "magnetic resonance", "diffusion weighted"],
        "description": "脑部磁共振成像",
    },
    "neuroimaging_angiography": {
        "name": "脑血管造影",
        "keywords": ["CTA", "MRA", "DSA", "血管造影", "angiography", "ct angiography", "mr angiography", "digital subtraction"],
        "description": "脑血管造影影像（CTA/MRA/DSA）",
    },
    "pathology_slide": {
        "name": "病理切片",
        "keywords": ["病理", "切片", "组织学", "细胞学", "HE染色", "免疫组化", "pathology", "histology", "slide", "biopsy", "活检"],
        "description": "病理组织学切片影像",
    },
    "ecg_waveform": {
        "name": "心电图/脑电图",
        "keywords": ["心电图", "ECG", "EKG", "脑电图", "EEG", "波形", "waveform", "心电", "electrocardiogram", "electroencephalogram"],
        "description": "心电图或脑电图波形",
    },
    "clinical_photo": {
        "name": "临床照片",
        "keywords": ["皮肤", "眼底", "眼底照片", "伤口", "皮疹", "溃疡", "skin", "fundus", "retina", "wound", "lesion", "rash", "临床照片"],
        "description": "临床体格检查照片",
    },
    "lab_report": {
        "name": "检验报告",
        "keywords": ["化验单", "检验报告", "实验室", "血常规", "生化", "凝血", "lab", "laboratory", "blood test", "report", "化验", "检查结果"],
        "description": "实验室检验报告单",
    },
    "radiology_report": {
        "name": "影像报告",
        "keywords": ["影像报告", "放射报告", "超声报告", "radiology report", "ultrasound report", "x-ray report", "报告单", "诊断报告"],
        "description": "影像学诊断报告文本",
    },
    "medical_illustration": {
        "name": "医学图解",
        "keywords": ["解剖图", "手术图解", "示意图", "anatomy", "surgical", "diagram", "illustration", "解剖", "图示"],
        "description": "医学解剖或手术图解",
    },
    "courseware_image": {
        "name": "课件资料",
        "keywords": ["课件", "笔记", "教材", "习题", "作业", "考试", "成绩", "报告", "学习资料", "PPT", "幻灯片", "讲义"],
        "description": "教学课件或学习资料图片",
    },
}


# ============================================================
# 结构化影像分析结果
# ============================================================

class Abnormality(BaseModel):
    """异常发现"""
    location: str = Field(default="", description="异常所在的解剖位置")
    description: str = Field(default="", description="异常表现的详细描述")
    significance: str = Field(default="", description="临床意义评估（如：急性期/慢性期、良性/恶性提示）")
    measurement: Optional[str] = Field(default=None, description="测量值（如大小、密度、信号强度）")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="AI对该异常判断的置信度")


class MedicalImageFindings(BaseModel):
    """医学影像结构化分析结果"""
    image_type: str = Field(default="", description="影像类型，如 neuroimaging_ct")
    anatomical_region: str = Field(default="", description="解剖区域，如 大脑/小脑/脑干")
    key_findings: List[str] = Field(default_factory=list, description="关键发现（中文列表）")
    abnormalities: List[Abnormality] = Field(default_factory=list, description="异常发现详情列表")
    normal_structures: List[str] = Field(default_factory=list, description="确认正常的结构")
    differential_diagnosis: List[str] = Field(default_factory=list, description="鉴别诊断列表（按可能性排序）")
    recommended_confirmatory_tests: List[str] = Field(default_factory=list, description="建议的确认性检查")
    urgency_level: str = Field(default="routine", description="紧急程度: routine/urgent/critical")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="整体分析置信度")
    limitations: str = Field(default="", description="本次分析的局限性说明")
    raw_description: str = Field(default="", description="VL模型的原始描述文本")


class MultiImageComparison(BaseModel):
    """多图对比分析结果"""
    image_count: int = Field(default=0, description="对比图片数量")
    image_types: List[str] = Field(default_factory=list, description="各图片类型")
    comparison_mode: str = Field(default="", description="对比模式: progression/comparison/series")
    key_changes: List[str] = Field(default_factory=list, description="关键变化/差异")
    unchanged_findings: List[str] = Field(default_factory=list, description="保持不变的表现")
    new_findings: List[str] = Field(default_factory=list, description="新发现")
    resolved_findings: List[str] = Field(default_factory=list, description="已消退的表现")
    overall_assessment: str = Field(default="", description="总体评估")
    per_image_findings: List[MedicalImageFindings] = Field(default_factory=list, description="每张图单独的分析结果")


# ============================================================
# 检验报告结构化数据
# ============================================================

class LabValue(BaseModel):
    """单个检验项目"""
    item_name: str = Field(default="", description="检验项目名称")
    value: str = Field(default="", description="检验值")
    unit: str = Field(default="", description="单位")
    reference_range: str = Field(default="", description="参考范围")
    is_abnormal: bool = Field(default=False, description="是否异常")
    abnormality_direction: str = Field(default="", description="异常方向: high/low/critical_high/critical_low")


class LabReport(BaseModel):
    """检验报告结构化提取结果"""
    report_type: str = Field(default="", description="报告类型（血常规/生化/凝血等）")
    patient_info: Dict[str, str] = Field(default_factory=dict, description="患者信息（脱敏后）")
    collection_time: str = Field(default="", description="采样时间")
    lab_values: List[LabValue] = Field(default_factory=list, description="检验项目列表")
    abnormal_summary: List[str] = Field(default_factory=list, description="异常项目摘要")
    overall_impression: str = Field(default="", description="总体印象")


class PrescriptionInfo(BaseModel):
    """处方信息提取结果"""
    drug_name: str = Field(default="", description="药品名称（通用名）")
    brand_name: str = Field(default="", description="商品名")
    dosage: str = Field(default="", description="剂量")
    frequency: str = Field(default="", description="用药频率")
    route: str = Field(default="", description="给药途径")
    duration: str = Field(default="", description="用药时长")
    notes: str = Field(default="", description="备注/注意事项")


# ============================================================
# DICOM 元数据
# ============================================================

class DICOMMetadata(BaseModel):
    """DICOM文件元数据"""
    study_uid: str = Field(default="", description="Study Instance UID")
    series_uid: str = Field(default="", description="Series Instance UID")
    modality: str = Field(default="", description="成像模态（CT/MR/CR/DX等）")
    study_description: str = Field(default="", description="检查描述")
    series_description: str = Field(default="", description="序列描述")
    slice_thickness: Optional[float] = Field(default=None, description="层厚(mm)")
    slice_location: Optional[float] = Field(default=None, description="层面位置")
    image_position: List[float] = Field(default_factory=list, description="图像位置坐标")
    image_orientation: List[float] = Field(default_factory=list, description="图像方向向量")
    pixel_spacing: List[float] = Field(default_factory=list, description="像素间距")
    rows: int = Field(default=0, description="图像行数")
    columns: int = Field(default=0, description="图像列数")
    window_center: Optional[float] = Field(default=None, description="窗位")
    window_width: Optional[float] = Field(default=None, description="窗宽")
    manufacturer: str = Field(default="", description="设备制造商")
    study_date: str = Field(default="", description="检查日期")
    has_phi_stripped: bool = Field(default=True, description="是否已移除受保护健康信息")


# ============================================================
# API 请求/响应模型
# ============================================================

class MedicalImageAnalysisRequest(BaseModel):
    """医学影像分析请求"""
    images: List[str] = Field(default_factory=list, description="Base64编码的图片列表")
    question: str = Field(default="", description="用户问题")
    all_info: str = Field(default="", description="学生画像信息")
    expected_image_type: Optional[str] = Field(default=None, description="期望的影像类型（为空则自动检测）")


class MedicalImageAnalysisResponse(BaseModel):
    """医学影像分析响应"""
    findings: MedicalImageFindings = Field(default_factory=MedicalImageFindings)
    pubmed_evidence: List[Dict[str, Any]] = Field(default_factory=list, description="相关PubMed文献")
    local_evidence: List[Dict[str, Any]] = Field(default_factory=list, description="本地知识库相关文献")
    analysis_text: str = Field(default="", description="完整的分析文本")


class MedicalCaseAnalysisRequest(BaseModel):
    """多模态病例分析请求"""
    talkId: Optional[str] = None
    message: str = Field(..., min_length=1, description="病例描述文本")
    images: List[str] = Field(default_factory=list, description="Base64编码的医学图片")
    case_type: str = Field(default="general", description="病例类型: stroke/neuro/general")
    include_evidence: bool = Field(default=True, description="是否检索循证证据")


class CompareImagesRequest(BaseModel):
    """多图对比请求"""
    images: List[str] = Field(..., min_length=2, description="至少2张Base64编码的图片")
    question: str = Field(default="", description="对比分析的问题/关注点")
    all_info: str = Field(default="", description="学生画像信息")


class DICOMMetadataRequest(BaseModel):
    """DICOM元数据提取请求"""
    image: str = Field(..., description="Base64编码的DICOM文件数据")
