import logging
import sys
import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
import os
import json
import uuid
import jwt
import time

from fastapi import FastAPI, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from sse_starlette.sse import EventSourceResponse
import uvicorn

from app.agents.assistant import LearningAssistant
from app.services.pubmed_service import PubMedService
from app.agents.orchestrators.qwen_agent import LearningAgent
from app.utils.error_codes import build_error_event, format_error_log
from app.utils.naming_model import NamingModel
from app.rag.retrieve import UnifiedSearchEngine, CONFIG
from app.config.config_loader import (
    get_prompt_manager,
    get_report_manager,
    get_expert_manager,
    get_validation_manager,
    get_limits_manager
)
from app.services.vision_service import VisionAnalysisService

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from app.utils.context_summary import ConversationSummaryService


os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

logger = logging.getLogger(__name__)
performance_logger = logging.getLogger("performance")
performance_logger.setLevel(logging.INFO)

resources = {"model": None, "naming_model": None, "executor": None, "context_summary": None, "vision_service": None, "llm_turbo": None, "learning_assistant": None}


# ============================================================
# 请求/响应模型
# ============================================================

class ProfileConversationRequest(BaseModel):
    talkId: Optional[str] = None
    message: str
    images: List[str] = Field(default_factory=list)


class ResourceGenerateRequest(BaseModel):
    talkId: Optional[str] = None
    message: str
    resourceTypes: List[str] = Field(default_factory=lambda: ["document"])
    courseName: str = ""
    knowledgePoints: List[str] = Field(default_factory=list)
    difficulty: str = "intermediate"
    images: List[str] = Field(default_factory=list)


class SingleDocumentRequest(BaseModel):
    courseName: str
    knowledgePoints: List[str] = Field(default_factory=list)
    difficulty: str = "intermediate"
    style: str = "detailed"
    profileAware: bool = True


class SingleMindmapRequest(BaseModel):
    courseName: str
    knowledgePoints: List[str] = Field(default_factory=list)
    format: str = "mermaid"
    depth: int = 3


class SingleQuizRequest(BaseModel):
    courseName: str
    knowledgePoints: List[str] = Field(default_factory=list)
    difficulty: str = "intermediate"
    quizTypes: List[str] = Field(default_factory=lambda: ["choice", "short_answer"])
    count: int = 10
    includeAnswer: bool = True


class SingleReadingRequest(BaseModel):
    courseName: str
    knowledgePoints: List[str] = Field(default_factory=list)
    readingType: str = "paper"
    language: str = "zh"
    count: int = 5


class SingleVideoScriptRequest(BaseModel):
    courseName: str
    knowledgePoints: List[str] = Field(default_factory=list)
    duration: str = "5min"
    style: str = "animation"
    includeNarration: bool = True
    includeVisual: bool = True


class SingleCodePracticeRequest(BaseModel):
    courseName: str
    knowledgePoints: List[str] = Field(default_factory=list)
    language: str = "python"
    projectType: str = "notebook"
    difficulty: str = "intermediate"
    includeTest: bool = True
    includeExplanation: bool = True


class TutorAskRequest(BaseModel):
    talkId: Optional[str] = None
    question: str
    context: Optional[Dict[str, Any]] = None
    preferredAnswerFormat: List[str] = Field(default_factory=lambda: ["text"])
    images: List[str] = Field(default_factory=list)


class LearningPathGenerateRequest(BaseModel):
    courseName: str
    goalDescription: str = ""
    deadline: Optional[str] = None
    weeklyHours: Optional[int] = None
    existingKnowledge: List[str] = Field(default_factory=list)
    targetKnowledge: List[str] = Field(default_factory=list)


class StepProgressRequest(BaseModel):
    status: str
    actualHours: Optional[int] = None
    feedback: Optional[str] = None
    selfRating: Optional[int] = None


class ResourceRecommendRequest(BaseModel):
    pathId: int
    currentStepId: int
    context: str = ""
    preferredTypes: List[str] = Field(default_factory=list)
    count: int = 5


class PathAdjustRequest(BaseModel):
    reason: str
    adjustmentData: Optional[Dict[str, Any]] = None


class BehaviorSubmitRequest(BaseModel):
    pathId: int
    stepId: int
    behaviors: List[Dict[str, Any]] = Field(default_factory=list)


class QuizSubmitRequest(BaseModel):
    answers: List[Dict[str, Any]] = Field(default_factory=list)


class EvaluationOptimizeRequest(BaseModel):
    pathId: int
    triggerReason: str = "auto"
    evaluationData: Optional[Dict[str, Any]] = None


class ProfileDimensionUpdateRequest(BaseModel):
    knowledgeBase: Optional[Dict[str, Any]] = None
    cognitiveStyle: Optional[Dict[str, Any]] = None
    learningGoal: Optional[Dict[str, Any]] = None
    errorPattern: Optional[Dict[str, Any]] = None
    learningPace: Optional[Dict[str, Any]] = None
    resourcePreference: Optional[Dict[str, Any]] = None


class PubMedSearchRequest(BaseModel):
    query: str
    max_results: int = 5


class LegacyQueryRequest(BaseModel):
    question: str
    round: int = 2
    all_info: str = ""
    token: str
    report_mode: str = "emergency"
    show_thinking: bool = True
    images: List[str] = Field(default_factory=list)


class QuickAnalyzeRequest(BaseModel):
    question: str = Field(..., min_length=1)
    token: str


# ============================================================
# 初始化
# ============================================================

def init_all_resources():
    start_time = time.time()
    logger.info("=" * 80)
    logger.info("🚀 开始初始化系统资源")
    logger.info("=" * 80)

    logger.info("📋 [1/7] 加载配置管理器...")
    prompt_mgr = get_prompt_manager()
    report_mgr = get_report_manager()
    expert_mgr = get_expert_manager()
    validation_mgr = get_validation_manager()
    limits_mgr = get_limits_manager()

    logger.info(f"  ✅ Prompt管理器: 已加载 {len(prompt_mgr._prompts)} 个prompt模板")
    logger.info(f"  ✅ 报告管理器: 可用模式 {report_mgr.list_modes()}")

    experts = expert_mgr.get_experts()
    logger.info(f"  ✅ 专家配置: 已加载 {len(experts)} 位专家")
    for expert in experts:
        logger.info(f"     - {expert.get('role')} (优先级: {expert.get('priority')})")

    rules = validation_mgr.get_contraindication_rules()
    logger.info(f"  ✅ 校验配置: {len(rules)} 个质量规则")
    logger.info(f"     - 最大反思次数: {validation_mgr.get_max_reflection_count()}")
    logger.info(f"     - 规则引擎: {'启用' if validation_mgr.is_rule_engine_enabled() else '禁用'}")
    logger.info(f"     - LLM反思: {'启用' if validation_mgr.is_llm_reflection_enabled() else '禁用'}")

    logger.info(f"  ✅ 参数限制:")
    logger.info(f"     - 最大子问题数: {limits_mgr.get_max_sub_questions()}")
    logger.info(f"     - 最大证据字符数: {limits_mgr.get_max_evidence_chars()}")

    logger.info("🤖 [2/7] 初始化大语言模型...")
    _dashscope_base = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    _dashscope_key = os.getenv("DASHSCOPE_API_KEY")

    if not _dashscope_key:
        logger.error("  ❌ 错误: DASHSCOPE_API_KEY 未设置")
        raise ValueError("DASHSCOPE_API_KEY 环境变量未设置")

    logger.info(f"  ✅ API密钥: {_dashscope_key[:10]}...{_dashscope_key[-4:]}")

    llm_max = ChatOpenAI(model="qwen-max", base_url=_dashscope_base, api_key=_dashscope_key, extra_body={"enable_thinking": False})
    llm_plus = ChatOpenAI(model="qwen-plus", base_url=_dashscope_base, api_key=_dashscope_key, extra_body={"enable_thinking": False})
    llm_turbo = ChatOpenAI(model="qwen-turbo", base_url=_dashscope_base, api_key=_dashscope_key, extra_body={"enable_thinking": False})

    logger.info("  ✅ 模型加载完成: qwen-max, qwen-plus, qwen-turbo")

    logger.info("💬 [3/7] 初始化上下文摘要服务...")
    context_summary = ConversationSummaryService(
        llm=llm_turbo,
        prompt_manager=prompt_mgr
    )
    logger.info("  ✅ 上下文摘要服务初始化完成")

    logger.info("🔍 [4/7] 初始化向量检索引擎...")
    retriever = UnifiedSearchEngine(
        persist_dir=CONFIG.get("persist_dir", "./chroma_db_unified"),
        top_k=CONFIG.get("top_k_final", 3)
    )

    if retriever.chunks:
        _loaded_doc_names = sorted(set(
            chunk.metadata["source"].removesuffix(".pdf").removesuffix(".PDF")
            for chunk in retriever.chunks
            if chunk.metadata.get("source")
        ))
        report_mgr.update_doc_list(_loaded_doc_names)
        logger.info(f"  ✅ 检索引擎初始化完成")
        logger.info(f"     - 文档数量: {len(retriever.chunks)} 个片段")
        logger.info(f"     - 文献数量: {len(_loaded_doc_names)} 篇")
    else:
        logger.warning("  ⚠️  本地文档为空，system_role 使用 YAML 静态列表")

    logger.info("📚 [5/7] 初始化学习助手...")
    learning_assistant = LearningAssistant(
        llm_main=llm_max,
        llm_fast=llm_plus,
        retriever=retriever,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr
    )
    logger.info("  ✅ 学习助手初始化完成")

    logger.info("🧠 [6/7] 初始化学习推理智能体...")
    agent = LearningAgent(
        llm_proposer=llm_max,
        llm_critic=llm_plus,
        learning_assistant=learning_assistant,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr,
        llm_turbo=llm_turbo,
    )
    logger.info("  ✅ 学习推理智能体初始化完成")

    logger.info("🔧 [7/7] 初始化其他服务...")
    vision_service = VisionAnalysisService(prompt_manager=prompt_mgr)
    naming_model = NamingModel()
    logger.info("  ✅ 影像识别服务初始化完成")
    logger.info("  ✅ 命名模型初始化完成")

    init_time = time.time() - start_time
    logger.info("=" * 80)
    logger.info(f"🎉 系统初始化完成！耗时: {init_time:.2f}秒")
    logger.info("=" * 80)

    return agent, naming_model, context_summary, vision_service, llm_turbo, learning_assistant


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info(">>> 正在初始化资源及加载模型...")
    resources["executor"] = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    loop = asyncio.get_running_loop()

    try:
        agent, naming, context_summary, vision_service, llm_turbo, learning_assistant = await loop.run_in_executor(
            resources["executor"], init_all_resources
        )
        resources["model"] = agent
        resources["naming_model"] = naming
        resources["context_summary"] = context_summary
        resources["vision_service"] = vision_service
        resources["llm_turbo"] = llm_turbo
        resources["learning_assistant"] = learning_assistant
        logging.info(">>> 所有模型组装完成，服务已就绪")
    except Exception as e:
        logging.error(f"!!! 模型初始化严重失败: {e}")
        import traceback
        logging.error(traceback.format_exc())
        raise

    yield

    logging.info("<<< 正在释放资源...")
    if resources["executor"]:
        resources["executor"].shutdown()


app = FastAPI(lifespan=lifespan)


def verify_token(token: str):
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


# ============================================================
# 3. 对话式学习画像模块
# ============================================================

@app.post("/model/profile/conversation")
async def profile_conversation(request: ProfileConversationRequest):
    """对话式画像构建（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        req_id = uuid.uuid4().hex[:12]
        start_time = time.time()
        talk_id = request.talkId or str(uuid.uuid4().int % 100000)
        new_talk = request.talkId is None

        try:
            logger.info(f"[profile] 请求 {req_id} 开始画像对话, talkId={talk_id}")
            yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": new_talk}, ensure_ascii=False)

            loop = asyncio.get_running_loop()
            final_answer_parts = []
            node_start_time = {}
            current_node = None

            naming_future = None
            if new_talk and resources.get("naming_model"):
                naming_future = loop.run_in_executor(
                    resources["executor"],
                    resources["naming_model"].run_naming,
                    request.message,
                )

            if request.images:
                vision_svc = resources.get("vision_service")
                if vision_svc:
                    async for event in vision_svc.analyze_stream(
                        images=request.images,
                        question=request.message,
                        all_info="",
                    ):
                        if event.get("type") == "thinking":
                            yield json.dumps({
                                "type": "node_start",
                                "node": "vision",
                                "label": event.get("title", "正在分析图片..."),
                            }, ensure_ascii=False)
                        elif event.get("type") == "chunk":
                            content_str = str(event.get("content", ""))
                            if content_str:
                                final_answer_parts.append(content_str)
                                yield json.dumps({"type": "token", "content": content_str}, ensure_ascii=False)

            node_start_time["reasoning"] = time.time()

            async for event in agent.run_learning_reasoning(
                case_text=request.message,
                all_info="",
                report_mode="profile_build",
                show_thinking=True,
            ):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "error":
                    yield json.dumps(event, ensure_ascii=False)
                    return
                if event.get("type") == "node_start":
                    current_node = event.get("node")
                if event.get("type") == "token":
                    content_str = str(event.get("content", ""))
                    if content_str:
                        final_answer_parts.append(content_str)
                yield json.dumps(event, ensure_ascii=False)

            generated_name = "学习画像构建"
            if naming_future:
                try:
                    generated_name = await naming_future or "学习画像构建"
                except Exception:
                    pass

            answer_text = "".join(final_answer_parts).strip()
            updated_all_info = ""
            if answer_text and resources.get("context_summary"):
                try:
                    summary_result = await loop.run_in_executor(
                        resources["executor"],
                        resources["context_summary"].update_all_info,
                        "",
                        request.message,
                        answer_text,
                    )
                    updated_all_info = summary_result.get("updated_all_info", "")
                except Exception:
                    pass

            yield json.dumps({
                "type": "done",
                "talkId": talk_id,
                "title": generated_name,
                "all_info": updated_all_info,
            }, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[profile] 请求 {req_id} 失败: {e}")
            yield json.dumps(build_error_event(e, talk_id=talk_id), ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.get("/model/profile")
async def get_profile():
    """获取当前学习画像"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")
    return {"code": 1, "msg": "success", "data": {"profileId": None, "userId": None, "dimensions": {}, "rawConversationSummary": "", "updateTime": "", "createTime": ""}}


@app.put("/model/profile/dimensions")
async def update_profile_dimensions(request: ProfileDimensionUpdateRequest):
    """手动更新画像维度"""
    return {"code": 1, "msg": "success", "data": None}


@app.get("/model/profile/conversation/{talk_id}")
async def get_profile_conversation(talk_id: str = Path(...)):
    """获取画像对话历史"""
    return {"code": 1, "msg": "success", "data": []}


@app.get("/model/profile/conversations")
async def list_profile_conversations():
    """获取画像对话列表"""
    return {"code": 1, "msg": "success", "data": []}


@app.delete("/model/profile/conversation/{talk_id}")
async def delete_profile_conversation(talk_id: str = Path(...)):
    """删除画像对话"""
    return {"code": 1, "msg": "success", "data": None}


# ============================================================
# 4. 多智能体协同资源生成模块
# ============================================================

@app.post("/model/resources/generate")
async def resources_generate(request: ResourceGenerateRequest):
    """综合资源生成（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        req_id = uuid.uuid4().hex[:12]
        talk_id = request.talkId or str(uuid.uuid4().int % 100000)
        new_talk = request.talkId is None

        try:
            logger.info(f"[resource] 请求 {req_id} 开始资源生成, talkId={talk_id}")
            yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": new_talk}, ensure_ascii=False)

            loop = asyncio.get_running_loop()
            final_answer_parts = []
            current_node = None

            naming_future = None
            if new_talk and resources.get("naming_model"):
                naming_future = loop.run_in_executor(
                    resources["executor"],
                    resources["naming_model"].run_naming,
                    request.message,
                )

            resource_context = f"课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n难度：{request.difficulty}\n资源类型：{', '.join(request.resourceTypes)}"
            combined_message = f"{request.message}\n\n【资源生成参数】\n{resource_context}"

            if request.images:
                vision_svc = resources.get("vision_service")
                if vision_svc:
                    async for event in vision_svc.analyze_stream(
                        images=request.images,
                        question=request.message,
                        all_info="",
                    ):
                        if event.get("type") == "thinking":
                            yield json.dumps({
                                "type": "node_start",
                                "node": "vision",
                                "label": event.get("title", "正在分析图片..."),
                            }, ensure_ascii=False)
                        elif event.get("type") == "chunk":
                            content_str = str(event.get("content", ""))
                            if content_str:
                                final_answer_parts.append(content_str)
                                yield json.dumps({"type": "token", "content": content_str}, ensure_ascii=False)

            async for event in agent.run_learning_reasoning(
                case_text=combined_message,
                all_info="",
                report_mode="resource_generate",
                show_thinking=True,
            ):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "error":
                    yield json.dumps(event, ensure_ascii=False)
                    return
                if event.get("type") == "node_start":
                    current_node = event.get("node")
                if event.get("type") == "token":
                    content_str = str(event.get("content", ""))
                    if content_str:
                        final_answer_parts.append(content_str)
                yield json.dumps(event, ensure_ascii=False)

            generated_name = "资源生成完成"
            if naming_future:
                try:
                    generated_name = await naming_future or "资源生成完成"
                except Exception:
                    pass

            yield json.dumps({
                "type": "done",
                "talkId": talk_id,
                "title": generated_name,
            }, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[resource] 请求 {req_id} 失败: {e}")
            yield json.dumps(build_error_event(e, talk_id=talk_id), ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.post("/model/resources/generate/document")
async def generate_document(request: SingleDocumentRequest):
    """生成课程讲解文档（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        talk_id = str(uuid.uuid4().int % 100000)
        yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": True}, ensure_ascii=False)

        combined_message = f"请生成课程讲解文档。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n难度：{request.difficulty}\n风格：{request.style}"

        async for event in agent.run_learning_reasoning(
            case_text=combined_message,
            all_info="",
            report_mode="resource_generate",
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                yield json.dumps(event, ensure_ascii=False)
                return
            yield json.dumps(event, ensure_ascii=False)

        yield json.dumps({"type": "done", "talkId": talk_id, "title": "课程讲解文档生成完成"}, ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.post("/model/resources/generate/mindmap")
async def generate_mindmap(request: SingleMindmapRequest):
    """生成知识点思维导图（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        talk_id = str(uuid.uuid4().int % 100000)
        yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": True}, ensure_ascii=False)

        combined_message = f"请生成知识点思维导图。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n格式：{request.format}\n展开层级：{request.depth}"

        async for event in agent.run_learning_reasoning(
            case_text=combined_message,
            all_info="",
            report_mode="resource_generate",
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                yield json.dumps(event, ensure_ascii=False)
                return
            yield json.dumps(event, ensure_ascii=False)

        yield json.dumps({"type": "done", "talkId": talk_id, "title": "思维导图生成完成"}, ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.post("/model/resources/generate/quiz")
async def generate_quiz(request: SingleQuizRequest):
    """生成练习题目（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        talk_id = str(uuid.uuid4().int % 100000)
        yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": True}, ensure_ascii=False)

        combined_message = f"请生成练习题目。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n难度：{request.difficulty}\n题目类型：{', '.join(request.quizTypes)}\n数量：{request.count}\n{'包含参考答案' if request.includeAnswer else '不包含参考答案'}"

        async for event in agent.run_learning_reasoning(
            case_text=combined_message,
            all_info="",
            report_mode="resource_generate",
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                yield json.dumps(event, ensure_ascii=False)
                return
            yield json.dumps(event, ensure_ascii=False)

        yield json.dumps({"type": "done", "talkId": talk_id, "title": "练习题目生成完成"}, ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.post("/model/resources/generate/reading")
async def generate_reading(request: SingleReadingRequest):
    """生成拓展阅读材料（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        talk_id = str(uuid.uuid4().int % 100000)
        yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": True}, ensure_ascii=False)

        combined_message = f"请生成拓展阅读材料。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n类型：{request.readingType}\n语言：{request.language}\n数量：{request.count}"

        async for event in agent.run_learning_reasoning(
            case_text=combined_message,
            all_info="",
            report_mode="resource_generate",
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                yield json.dumps(event, ensure_ascii=False)
                return
            yield json.dumps(event, ensure_ascii=False)

        yield json.dumps({"type": "done", "talkId": talk_id, "title": "拓展阅读材料生成完成"}, ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.post("/model/resources/generate/video-script")
async def generate_video_script(request: SingleVideoScriptRequest):
    """生成教学视频/动画脚本（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        talk_id = str(uuid.uuid4().int % 100000)
        yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": True}, ensure_ascii=False)

        combined_message = f"请生成教学视频/动画脚本。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n预期时长：{request.duration}\n风格：{request.style}\n{'包含旁白脚本' if request.includeNarration else '不包含旁白脚本'}\n{'包含画面描述' if request.includeVisual else '不包含画面描述'}"

        async for event in agent.run_learning_reasoning(
            case_text=combined_message,
            all_info="",
            report_mode="resource_generate",
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                yield json.dumps(event, ensure_ascii=False)
                return
            yield json.dumps(event, ensure_ascii=False)

        yield json.dumps({"type": "done", "talkId": talk_id, "title": "视频脚本生成完成"}, ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.post("/model/resources/generate/code-practice")
async def generate_code_practice(request: SingleCodePracticeRequest):
    """生成代码实操案例（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        talk_id = str(uuid.uuid4().int % 100000)
        yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": True}, ensure_ascii=False)

        combined_message = f"请生成代码实操案例。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n编程语言：{request.language}\n项目类型：{request.projectType}\n难度：{request.difficulty}\n{'包含测试用例' if request.includeTest else '不包含测试用例'}\n{'包含代码注释说明' if request.includeExplanation else '不包含代码注释说明'}"

        async for event in agent.run_learning_reasoning(
            case_text=combined_message,
            all_info="",
            report_mode="resource_generate",
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                yield json.dumps(event, ensure_ascii=False)
                return
            yield json.dumps(event, ensure_ascii=False)

        yield json.dumps({"type": "done", "talkId": talk_id, "title": "代码实操案例生成完成"}, ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.get("/model/resources")
async def list_resources(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    type: Optional[str] = None,
    courseName: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    """获取资源列表"""
    return {"code": 1, "msg": "success", "data": {"total": 0, "records": []}}


@app.get("/model/resources/{resource_id}")
async def get_resource(resource_id: int = Path(...)):
    """获取资源详情"""
    return {"code": 1, "msg": "success", "data": {"resourceId": resource_id, "title": "", "type": "", "courseName": "", "difficulty": "", "knowledgePoints": [], "content": "", "fileUrl": None, "metadata": {}, "createTime": "", "updateTime": ""}}


@app.get("/model/resources/{resource_id}/download")
async def download_resource(resource_id: int = Path(...)):
    """下载资源文件"""
    return {"code": 1, "msg": "success", "data": {"resourceId": resource_id, "previewUrl": "", "downloadUrl": ""}}


@app.delete("/model/resources/{resource_id}")
async def delete_resource(resource_id: int = Path(...)):
    """删除资源"""
    return {"code": 1, "msg": "success", "data": None}


@app.get("/model/resources/conversation/{talk_id}")
async def get_resource_conversation(talk_id: str = Path(...)):
    """获取资源对话历史"""
    return {"code": 1, "msg": "success", "data": []}


@app.get("/model/resources/conversations")
async def list_resource_conversations():
    """获取资源对话列表"""
    return {"code": 1, "msg": "success", "data": []}


# ============================================================
# 5. 个性化学习路径模块
# ============================================================

@app.post("/model/learning-path/generate")
async def generate_learning_path(request: LearningPathGenerateRequest):
    """生成个性化学习路径"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    start_time = time.time()
    req_id = uuid.uuid4().hex[:12]

    try:
        logger.info(f"[learning-path] 请求 {req_id} 开始生成学习路径")

        llm_turbo = resources.get("llm_turbo")
        if not llm_turbo:
            raise HTTPException(status_code=503, detail="LLM service not ready")

        existing_knowledge_str = "、".join(request.existingKnowledge) if request.existingKnowledge else "从画像读取"
        target_knowledge_str = "、".join(request.targetKnowledge) if request.targetKnowledge else "AI自动规划"

        prompt = f"""你是高等教育个性化学习路径规划专家。请为以下学生规划学习路径。

课程：{request.courseName}
学习目标：{request.goalDescription}
{'截止日期：' + request.deadline if request.deadline else ''}
{'每周可投入时长：' + str(request.weeklyHours) + '小时' if request.weeklyHours else ''}
已掌握知识点：{existing_knowledge_str}
目标知识点：{target_knowledge_str}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "pathId": null,
    "courseName": "{request.courseName}",
    "goalDescription": "{request.goalDescription}",
    "totalSteps": 0,
    "estimatedDays": 0,
    "status": "active",
    "steps": [
        {{
            "stepId": 1,
            "title": "步骤标题",
            "description": "步骤描述",
            "knowledgePoints": ["知识点1"],
            "estimatedHours": 6,
            "difficulty": "beginner/intermediate/advanced",
            "status": "not_started",
            "orderIndex": 1,
            "resources": [],
            "prerequisites": []
        }}
    ]
}}

要求：
- 步骤数量根据课程复杂度合理设定（5-15步）
- 每步包含2-5个知识点
- 难度循序渐进
- prerequisites 填写前置步骤的 stepId 列表
- estimatedHours 根据知识点数量和难度合理估算"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = _parse_json(content)
        if not result:
            result = {
                "pathId": None,
                "courseName": request.courseName,
                "goalDescription": request.goalDescription,
                "totalSteps": 0,
                "estimatedDays": 0,
                "status": "active",
                "steps": []
            }

        analysis_time = time.time() - start_time
        logger.info(f"[learning-path] 请求 {req_id} 完成 - 耗时: {analysis_time:.2f}秒")

        return {"code": 1, "msg": "success", "data": result}

    except Exception as e:
        logger.error(f"[learning-path] 请求 {req_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/model/learning-path")
async def list_learning_paths(
    courseName: Optional[str] = None,
    status: Optional[str] = None,
):
    """获取学习路径列表"""
    return {"code": 1, "msg": "success", "data": {"total": 0, "records": []}}


@app.get("/model/learning-path/{path_id}")
async def get_learning_path(path_id: int = Path(...)):
    """获取学习路径详情"""
    return {"code": 1, "msg": "success", "data": {"pathId": path_id, "courseName": "", "totalSteps": 0, "steps": []}}


@app.put("/model/learning-path/{path_id}/steps/{step_id}/progress")
async def update_step_progress(
    path_id: int = Path(...),
    step_id: int = Path(...),
    request: StepProgressRequest = ...,
):
    """更新学习步骤进度"""
    return {"code": 1, "msg": "success", "data": {"pathId": path_id, "completedSteps": 0, "progress": 0.0, "suggestedAdjustments": ""}}


@app.post("/model/learning-path/recommend")
async def recommend_resources(request: ResourceRecommendRequest):
    """个性化资源推送"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    llm_turbo = resources.get("llm_turbo")
    if not llm_turbo:
        raise HTTPException(status_code=503, detail="LLM service not ready")

    try:
        prompt = f"""你是高等教育个性化学习资源推荐专家。请基于以下信息推荐学习资源。

学习路径ID：{request.pathId}
当前步骤ID：{request.currentStepId}
学习上下文：{request.context}
偏好资源类型：{', '.join(request.preferredTypes) if request.preferredTypes else '不限'}
推荐数量：{request.count}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "recommendations": [
        {{
            "resourceId": null,
            "title": "资源标题",
            "type": "document/mindmap/quiz/reading/video_script/code_practice",
            "relevance": 0.95,
            "reason": "推荐理由",
            "difficulty": "beginner/intermediate/advanced"
        }}
    ],
    "profileInsight": "基于画像的分析洞察"
}}"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = _parse_json(content)
        if not result:
            result = {"recommendations": [], "profileInsight": ""}

        return {"code": 1, "msg": "success", "data": result}

    except Exception as e:
        logger.error(f"[recommend] 资源推荐失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/model/learning-path/{path_id}/adjust")
async def adjust_learning_path(
    path_id: int = Path(...),
    request: PathAdjustRequest = ...,
):
    """动态调整学习路径"""
    llm_turbo = resources.get("llm_turbo")
    if not llm_turbo:
        raise HTTPException(status_code=503, detail="LLM service not ready")

    try:
        adjustment_str = json.dumps(request.adjustmentData, ensure_ascii=False) if request.adjustmentData else "无"

        prompt = f"""你是高等教育个性化学习路径调整专家。请根据以下信息调整学习路径。

学习路径ID：{path_id}
调整原因：{request.reason}
调整数据：{adjustment_str}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "pathId": {path_id},
    "adjustments": [
        {{
            "type": "insert_step/update_resource/adjust_difficulty",
            "description": "调整描述",
            "afterStepId": null,
            "stepId": null
        }}
    ],
    "newTotalSteps": 0,
    "newEstimatedDays": 0
}}"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = _parse_json(content)
        if not result:
            result = {"pathId": path_id, "adjustments": [], "newTotalSteps": 0, "newEstimatedDays": 0}

        return {"code": 1, "msg": "success", "data": result}

    except Exception as e:
        logger.error(f"[adjust] 路径调整失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 6. 智能辅导模块
# ============================================================

@app.post("/model/tutor/ask")
async def tutor_ask(request: TutorAskRequest):
    """智能辅导问答（SSE 流式）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        req_id = uuid.uuid4().hex[:12]
        talk_id = request.talkId or str(uuid.uuid4().int % 100000)
        new_talk = request.talkId is None

        try:
            logger.info(f"[tutor] 请求 {req_id} 开始智能辅导, talkId={talk_id}")
            yield json.dumps({"type": "init", "talkId": talk_id, "newTalk": new_talk}, ensure_ascii=False)

            loop = asyncio.get_running_loop()
            final_answer_parts = []
            current_node = None

            naming_future = None
            if new_talk and resources.get("naming_model"):
                naming_future = loop.run_in_executor(
                    resources["executor"],
                    resources["naming_model"].run_naming,
                    request.question,
                )

            context_parts = []
            if request.context:
                if request.context.get("courseName"):
                    context_parts.append(f"课程：{request.context['courseName']}")
                if request.context.get("currentKnowledgePoint"):
                    context_parts.append(f"当前知识点：{request.context['currentKnowledgePoint']}")
                if request.context.get("pathId"):
                    context_parts.append(f"学习路径ID：{request.context['pathId']}")
                if request.context.get("stepId"):
                    context_parts.append(f"步骤ID：{request.context['stepId']}")

            context_str = "\n".join(context_parts)
            format_str = f"期望回答形式：{', '.join(request.preferredAnswerFormat)}" if request.preferredAnswerFormat else ""

            combined_message = f"{request.question}"
            if context_str:
                combined_message += f"\n\n【学习上下文】\n{context_str}"
            if format_str:
                combined_message += f"\n{format_str}"

            if request.images:
                vision_svc = resources.get("vision_service")
                if vision_svc:
                    async for event in vision_svc.analyze_stream(
                        images=request.images,
                        question=request.question,
                        all_info="",
                    ):
                        if event.get("type") == "thinking":
                            yield json.dumps({
                                "type": "node_start",
                                "node": "vision",
                                "label": event.get("title", "正在分析图片..."),
                            }, ensure_ascii=False)
                        elif event.get("type") == "chunk":
                            content_str = str(event.get("content", ""))
                            if content_str:
                                final_answer_parts.append(content_str)
                                yield json.dumps({"type": "token", "content": content_str}, ensure_ascii=False)

            async for event in agent.run_learning_reasoning(
                case_text=combined_message,
                all_info="",
                report_mode="tutor",
                show_thinking=True,
            ):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "error":
                    yield json.dumps(event, ensure_ascii=False)
                    return
                if event.get("type") == "node_start":
                    current_node = event.get("node")
                if event.get("type") == "token":
                    content_str = str(event.get("content", ""))
                    if content_str:
                        final_answer_parts.append(content_str)
                yield json.dumps(event, ensure_ascii=False)

            generated_name = "智能辅导"
            if naming_future:
                try:
                    generated_name = await naming_future or "智能辅导"
                except Exception:
                    pass

            yield json.dumps({
                "type": "done",
                "talkId": talk_id,
                "title": generated_name,
            }, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[tutor] 请求 {req_id} 失败: {e}")
            yield json.dumps(build_error_event(e, talk_id=talk_id), ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.get("/model/tutor/conversation/{talk_id}")
async def get_tutor_conversation(talk_id: str = Path(...)):
    """获取辅导对话历史"""
    return {"code": 1, "msg": "success", "data": []}


@app.get("/model/tutor/conversations")
async def list_tutor_conversations():
    """获取辅导对话列表"""
    return {"code": 1, "msg": "success", "data": []}


@app.delete("/model/tutor/conversation/{talk_id}")
async def delete_tutor_conversation(talk_id: str = Path(...)):
    """删除辅导对话"""
    return {"code": 1, "msg": "success", "data": None}


# ============================================================
# 7. 学习效果评估模块
# ============================================================

@app.post("/model/evaluation/behavior")
async def submit_behavior(request: BehaviorSubmitRequest):
    """提交学习行为数据"""
    return {"code": 1, "msg": "success", "data": {"received": len(request.behaviors), "processed": len(request.behaviors)}}


@app.get("/model/evaluation/report")
async def get_evaluation_report(
    pathId: Optional[int] = None,
    period: str = "all",
):
    """获取学习效果评估报告"""
    llm_turbo = resources.get("llm_turbo")
    if not llm_turbo:
        raise HTTPException(status_code=503, detail="LLM service not ready")

    try:
        path_info = f"学习路径ID：{pathId}" if pathId else "所有学习路径"
        prompt = f"""你是高等教育学习效果评估专家。请生成一份学习效果评估报告。

{path_info}
统计周期：{period}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "overallScore": 70,
    "level": "good",
    "period": "{period}",
    "dimensions": {{
        "knowledgeMastery": {{"score": 70, "level": "good", "details": {{"mastered": [], "partiallyMastered": [], "notMastered": []}}}},
        "learningEfficiency": {{"score": 70, "level": "good", "details": {{"averageStudyTimePerDay": "1h", "resourceCompletionRate": 0.8, "quizAverageScore": 0.75}}}},
        "skillApplication": {{"score": 70, "level": "good", "details": {{"codePracticePassRate": 0.8, "projectCompletionRate": 0.6}}}},
        "learningConsistency": {{"score": 70, "level": "good", "details": {{"studyDaysThisWeek": 4, "averageSessionDuration": "45min", "breakPattern": "偶尔中断"}}}},
        "progressAlignment": {{"score": 70, "level": "good", "details": {{"plannedProgress": 0.3, "actualProgress": 0.25, "deviation": "略慢于计划"}}}}
    }},
    "strengths": ["优势1"],
    "weaknesses": ["不足1"],
    "suggestions": ["建议1"],
    "generateTime": "2026-06-10 17:00:00"
}}"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = _parse_json(content)
        if not result:
            result = {"overallScore": 0, "level": "moderate", "period": period, "dimensions": {}, "strengths": [], "weaknesses": [], "suggestions": [], "generateTime": ""}

        return {"code": 1, "msg": "success", "data": result}

    except Exception as e:
        logger.error(f"[evaluation] 评估报告生成失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/model/evaluation/quiz/{quiz_id}/submit")
async def submit_quiz(quiz_id: int = Path(...), request: QuizSubmitRequest = ...):
    """提交练习/测验答案"""
    return {"code": 1, "msg": "success", "data": {"quizId": quiz_id, "totalQuestions": 0, "correctCount": 0, "score": 0.0, "details": [], "knowledgeGapAnalysis": {"weakPoints": [], "suggestedResources": []}}}


@app.get("/model/evaluation/mastery-heatmap")
async def get_mastery_heatmap(courseName: Optional[str] = None):
    """获取知识点掌握度热力图"""
    return {"code": 1, "msg": "success", "data": {"courseName": courseName or "", "knowledgeTree": {}, "legend": {"0.0-0.3": "未掌握", "0.3-0.6": "初步了解", "0.6-0.8": "基本掌握", "0.8-1.0": "熟练掌握"}}}


@app.post("/model/evaluation/optimize")
async def optimize_learning(request: EvaluationOptimizeRequest):
    """触发学习方案动态优化"""
    llm_turbo = resources.get("llm_turbo")
    if not llm_turbo:
        raise HTTPException(status_code=503, detail="LLM service not ready")

    try:
        evaluation_str = json.dumps(request.evaluationData, ensure_ascii=False) if request.evaluationData else "使用系统最新数据"

        prompt = f"""你是高等教育学习方案优化专家。请根据以下信息优化学习方案。

学习路径ID：{request.pathId}
触发原因：{request.triggerReason}
评估数据：{evaluation_str}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "pathId": {request.pathId},
    "optimizationApplied": true,
    "changes": [
        {{
            "type": "insert_step/update_resource/adjust_difficulty",
            "description": "调整描述",
            "reason": "调整原因"
        }}
    ],
    "newEstimatedDays": 0,
    "profileUpdated": false,
    "profileChanges": {{}}
}}"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = _parse_json(content)
        if not result:
            result = {"pathId": request.pathId, "optimizationApplied": False, "changes": [], "newEstimatedDays": 0, "profileUpdated": False, "profileChanges": {}}

        return {"code": 1, "msg": "success", "data": result}

    except Exception as e:
        logger.error(f"[optimize] 学习方案优化失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 8. 课程与知识库模块
# ============================================================

@app.get("/model/courses")
async def list_courses(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    category: Optional[str] = None,
):
    """获取课程列表"""
    return {"code": 1, "msg": "success", "data": {"total": 0, "records": []}}


@app.get("/model/courses/{course_id}/knowledge-tree")
async def get_knowledge_tree(course_id: int = Path(...)):
    """获取课程知识体系"""
    return {"code": 1, "msg": "success", "data": {"courseId": course_id, "name": "", "tree": {}}}


@app.post("/model/pubmed/search")
async def pubmed_search(request: PubMedSearchRequest):
    """学术文献检索接口"""
    query = request.query.strip()
    if not query:
        return {"code": 1, "msg": "success", "data": {"papers": []}}

    svc = PubMedService()
    try:
        papers = await svc.search_papers(query, max_results=request.max_results)
    except Exception:
        papers = []

    return {"code": 1, "msg": "success", "data": {"papers": papers}}


# ============================================================
# 兼容旧接口
# ============================================================

@app.post("/model/get_result")
async def get_model_result(request: LegacyQueryRequest):
    """兼容旧版临床推理接口"""
    verify_token(request.token)

    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    async def generate():
        req_id = uuid.uuid4().hex[:12]
        start_time = time.time()

        try:
            logger.info(f"[legacy] 请求 {req_id} 开始处理")
            loop = asyncio.get_running_loop()
            final_answer_parts = []
            node_start_time = {}
            node_count = 0

            if request.images:
                vision_svc = resources.get("vision_service")
                if not vision_svc:
                    yield json.dumps({"type": "token", "content": "影像识别服务未就绪，请稍后重试。"}, ensure_ascii=False)
                else:
                    async for event in vision_svc.analyze_stream(
                        images=request.images,
                        question=request.question,
                        all_info=request.all_info,
                    ):
                        if event.get("type") == "thinking":
                            yield json.dumps({
                                "type": "node_start",
                                "node": "vision",
                                "label": event.get("title", "正在分析图片..."),
                            }, ensure_ascii=False)
                        elif event.get("type") == "chunk":
                            content_str = str(event.get("content", ""))
                            if content_str:
                                final_answer_parts.append(content_str)
                                yield json.dumps({"type": "token", "content": content_str}, ensure_ascii=False)

                    yield json.dumps({
                        "type": "done",
                        "request_id": req_id,
                        "name": "影像分析",
                        "all_info": request.all_info,
                    }, ensure_ascii=False)
                    return

            naming_future = None
            if not request.all_info and resources.get("naming_model"):
                naming_future = loop.run_in_executor(
                    resources["executor"],
                    resources["naming_model"].run_naming,
                    request.question,
                )

            current_node = None

            async for event in agent.run_learning_reasoning(
                case_text=request.question,
                all_info=request.all_info,
                report_mode=request.report_mode,
                show_thinking=request.show_thinking,
            ):
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "error":
                    yield json.dumps(event, ensure_ascii=False)
                    return
                if event.get("type") == "node_start":
                    node_count += 1
                    current_node = event.get("node")
                if event.get("type") == "token":
                    content_str = str(event.get("content", ""))
                    if content_str:
                        final_answer_parts.append(content_str)
                yield json.dumps(event, ensure_ascii=False)

            generated_name = "学习咨询"
            if naming_future:
                try:
                    generated_name = await naming_future or "学习咨询"
                except Exception:
                    pass

            answer_text = "".join(final_answer_parts).strip()
            updated_all_info = request.all_info

            if answer_text and resources.get("context_summary"):
                try:
                    summary_result = await loop.run_in_executor(
                        resources["executor"],
                        resources["context_summary"].update_all_info,
                        request.all_info,
                        request.question,
                        answer_text,
                        0.4,
                    )
                    updated_all_info = summary_result.get("updated_all_info", request.all_info)
                except Exception:
                    pass

            yield json.dumps({
                "type": "done",
                "request_id": req_id,
                "name": generated_name,
                "all_info": updated_all_info,
            }, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[legacy] 请求 {req_id} 失败: {e}")
            yield json.dumps(build_error_event(e, talk_id=None), ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@app.post("/ai/analyze")
async def analyze_learning_risk(request: QuickAnalyzeRequest):
    """学习风险快速分析接口"""
    verify_token(request.token)
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question cannot be empty")

    start_time = time.time()
    req_id = uuid.uuid4().hex[:12]

    try:
        llm_turbo = resources.get("llm_turbo")
        if not llm_turbo:
            raise HTTPException(status_code=503, detail="LLM service not ready")

        prompt = f"""你是高等教育学习风险评估专家。请快速分析以下学习问题，给出简洁专业的意见。

问题：
{question}

请直接输出 JSON（不要用 markdown 代码块包裹）：
{{
    "quickOpinion": "快速专业意见（100字以内）",
    "keyPoints": ["关键点1", "关键点2", "关键点3"],
    "riskLevel": "低风险/中风险/高风险"
}}

要求：
- quickOpinion: 简洁专业，禁止绝对性结论
- keyPoints: 3-5个关键点，每点20字以内
- riskLevel: 基于问题内容判断风险等级"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = _parse_json(content)
        if not result:
            result = {
                "quickOpinion": "建议结合学习情况进一步评估。",
                "keyPoints": ["需进一步分析", "结合实际判断", "持续关注"],
                "riskLevel": "中风险"
            }

        analysis_time = time.time() - start_time
        logger.info(f"[analyze] 请求 {req_id} 完成 - 耗时: {analysis_time:.2f}秒")

        return {"code": 1, "msg": "success", "data": result}

    except Exception as e:
        logger.error(f"[analyze] 请求 {req_id} 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 管理接口
# ============================================================

@app.post("/admin/reload_config")
async def reload_config():
    """配置热更新接口"""
    try:
        get_prompt_manager().reload()
        get_report_manager().reload()
        get_expert_manager().reload()
        get_validation_manager().reload()
        get_limits_manager().reload()
        return {"status": "ok", "message": "配置已热更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/report_modes")
async def list_report_modes():
    """获取可用报告模式接口"""
    mgr = get_report_manager()
    modes = mgr.list_modes()
    return {
        "modes": [
            {"key": m, "name": mgr.get_template_name(m)}
            for m in modes
        ]
    }


def _parse_json(text: str) -> dict:
    content = (text or "").strip()
    try:
        return json.loads(content)
    except Exception:
        pass
    for marker in ["```json", "```"]:
        if marker in content:
            try:
                s = content.split(marker)[1].split("```")[0].strip()
                return json.loads(s)
            except Exception:
                pass
    for sc, ec in [("{", "}"), ("[", "]")]:
        si, ei = content.find(sc), content.rfind(ec)
        if si != -1 and ei > si:
            try:
                return json.loads(content[si:ei + 1])
            except Exception:
                pass
    return {}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)