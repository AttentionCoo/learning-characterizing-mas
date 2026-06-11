"""统一数据模型 — 高等教育个性化学习系统"""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class LearningContext(BaseModel):
    """学习上下文"""
    基本信息: Dict = Field(default_factory=dict)
    学习需求: str = ""
    主要问题: List[str] = Field(default_factory=list)
    知识水平评估: Dict = Field(default_factory=dict)
    认知风格: str = ""
    学习目标: List[str] = Field(default_factory=list)
    易错点: List[str] = Field(default_factory=list)
    学习节奏: Dict = Field(default_factory=dict)
    资源偏好: List[str] = Field(default_factory=list)


class LearningState(TypedDict):
    """学习系统状态（用于 LangGraph）"""
    case_text: str
    all_info: str
    report_mode: str
    intent_type: str
    context: Dict
    learning_questions: List[str]
    key_risks: List[str]
    complexity: str
    evidence: str
    proposal: str
    critique: str
    user_questions: List[str]
    report: str
    expert_advices: Dict
    validation_passed: bool
    validation_feedback: str
    reflection_count: int