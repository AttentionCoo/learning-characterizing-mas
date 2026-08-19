"""统一数据模型 — 高等教育个性化学习系统"""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class LearningContext(BaseModel):
    """学习上下文"""
    basic_info: Dict = Field(default_factory=dict)
    learning_needs: str = ""
    main_problems: List[str] = Field(default_factory=list)
    knowledge_level: Dict = Field(default_factory=dict)
    cognitive_style: str = ""
    learning_goals: List[str] = Field(default_factory=list)
    weak_points: List[str] = Field(default_factory=list)
    learning_pace: Dict = Field(default_factory=dict)
    resource_preferences: List[str] = Field(default_factory=list)


class LearningState(TypedDict):
    """学习系统状态（用于 LangGraph）"""
    case_text: str
    all_info: str
    report_mode: str
    intent_type: str
    input_rejection_message: str
    context: Dict
    learning_questions: List[str]
    key_risks: List[str]
    complexity: str
    difficulty_score: float
    evidence: str
    retrieval_sources: List[Dict]
    proposal: str
    critique: str
    user_questions: List[str]
    report: str
    expert_advices: Dict
    validation_passed: bool
    validation_feedback: str
    reflection_count: int
    agent_weights: Dict
    rejection_categories: List[str]
    debate_history: List[Dict]
    arbitration_result: str
    active_experts: List[str]
    motivational_feedback: str
    profile_summary: str
    shared_memory_hits: List[Dict]
    memory_entropy_scores: Dict
    consensus_result: Dict
    # 医学多模态影像字段
    images: List[str]
    vision_findings: Optional[Dict]
    vision_evidence: str
    has_medical_images: bool
    # Planner/Supervisor 架构字段
    plan: Dict
    plan_rationale: str
    plan_results: List[Dict]
    supervisor_trace: List[Dict]
    supervisor_roles: List[str]
    supervisor_reason: str
    expert_advices: List[Dict]
