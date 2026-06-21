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
from app.utils.task_manager import AsyncTaskManager


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

resources = {"model": None, "naming_model": None, "executor": None, "context_summary": None, "vision_service": None, "llm_turbo": None, "learning_assistant": None, "task_manager": AsyncTaskManager()}


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
    pathInfo: Optional[Dict[str, Any]] = None
    steps: Optional[List[Dict[str, Any]]] = None


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
# 后台任务辅助函数
# ============================================================

async def _stream_task_events(task_id: str, task_mgr: AsyncTaskManager, init_event: dict = None):
    if init_event:
        yield json.dumps(init_event, ensure_ascii=False)
    event_index = 0
    while True:
        task = task_mgr.get_task(task_id)
        if not task:
            yield json.dumps({"type": "error", "content": "Task not found"}, ensure_ascii=False)
            return
        while event_index < len(task.events):
            yield json.dumps(task.events[event_index], ensure_ascii=False)
            event_index += 1
        if task.status in ("completed", "failed"):
            return
        await task.wait_for_new_event(event_index, timeout=2.0)


async def _run_agent_background(
    task_id: str,
    agent,
    case_text: str,
    all_info: str,
    report_mode: str,
    task_mgr: AsyncTaskManager,
    naming_model=None,
    executor=None,
    naming_input: str = None,
    images: List[str] = None,
    image_question: str = None,
    update_all_info: bool = False,
    original_all_info: str = "",
):
    try:
        loop = asyncio.get_running_loop()
        final_parts = []

        naming_future = None
        if naming_model and executor and naming_input:
            naming_future = loop.run_in_executor(executor, naming_model.run_naming, naming_input)

        if images:
            vision_svc = resources.get("vision_service")
            if vision_svc:
                async for event in vision_svc.analyze_stream(
                    images=images,
                    question=image_question or "",
                    all_info="",
                ):
                    if event.get("type") == "thinking":
                        task_mgr.add_event(task_id, {
                            "type": "node_start",
                            "node": "vision",
                            "label": event.get("title", "正在分析图片..."),
                        })
                    elif event.get("type") == "chunk":
                        content_str = str(event.get("content", ""))
                        if content_str:
                            final_parts.append(content_str)
                            task_mgr.add_event(task_id, {"type": "token", "content": content_str})

        async for event in agent.run_learning_reasoning(
            case_text=case_text,
            all_info=all_info,
            report_mode=report_mode,
            show_thinking=True,
        ):
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error":
                task_mgr.add_event(task_id, event)
                task_mgr.fail_task(task_id, event.get("content", "Unknown error"))
                return
            if event.get("type") == "token":
                content_str = str(event.get("content", ""))
                if content_str:
                    final_parts.append(content_str)
            task_mgr.add_event(task_id, event)

        result_text = "".join(final_parts).strip()

        generated_name = None
        if naming_future:
            try:
                generated_name = await naming_future
            except Exception:
                pass

        done_event = {
            "type": "done",
            "taskId": task_id,
            "title": generated_name or "生成完成",
        }

        if update_all_info and result_text and resources.get("context_summary") and executor:
            try:
                summary_result = await loop.run_in_executor(
                    executor,
                    resources["context_summary"].update_all_info,
                    original_all_info,
                    case_text,
                    result_text,
                    0.4,
                )
                done_event["all_info"] = summary_result.get("updated_all_info", original_all_info)
            except Exception:
                done_event["all_info"] = original_all_info

        if report_mode == "profile_build" and result_text and resources.get("llm_turbo") and executor:
            try:
                logger.info(f"[background] 检测到画像构建模式，自动提取学习画像维度...")
                conversation_for_extract = f"用户: {case_text}\n助手: {result_text}"

                extract_result = await loop.run_in_executor(
                    executor,
                    _extract_profile_from_conversation,
                    conversation_for_extract,
                )

                if extract_result:
                    logger.info(f"[background] 画像维度提取成功: {list(extract_result.keys())}")
                    done_event["profile_dimensions"] = extract_result
                else:
                    logger.warning(f"[background] 画像维度提取失败或为空")
            except Exception as e:
                logger.error(f"[background] 自动提取画像异常: {e}", exc_info=True)

        task_mgr.add_event(task_id, done_event)
        task_mgr.complete_task(task_id, result=result_text)
    except Exception as e:
        logger.error(f"[background] 任务 {task_id} 失败: {e}")
        task_mgr.add_event(task_id, build_error_event(e, talk_id=None))
        task_mgr.fail_task(task_id, str(e))


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

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = request.talkId or str(uuid.uuid4().int % 100000)
    new_talk = request.talkId is None

    task_mgr.create_task(task_id, "profile_conversation", {"talkId": talk_id})

    asyncio.create_task(_run_agent_background(
        task_id=task_id,
        agent=agent,
        case_text=request.message,
        all_info="",
        report_mode="profile_build",
        task_mgr=task_mgr,
        naming_model=resources.get("naming_model") if new_talk else None,
        executor=resources.get("executor"),
        naming_input=request.message if new_talk else None,
        images=request.images if request.images else None,
        image_question=request.message,
        update_all_info=True,
        original_all_info="",
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": new_talk}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


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


class ProfileExtractRequest(BaseModel):
    conversation: str
    userId: Optional[int] = None


@app.post("/model/profile/extract")
async def extract_profile_dimensions(request: ProfileExtractRequest):
    """从对话内容中抽取画像维度"""
    llm = resources.get("llm_turbo")
    if not llm:
        raise HTTPException(status_code=503, detail="Model service not ready")

    extract_prompt = f"""你是一位专业的学习画像分析专家。请从以下师生对话内容中，自动抽取学生的结构化学习画像维度。

对话内容：
{request.conversation}

请严格按以下 JSON 格式输出，不要输出任何其他内容，不要使用 markdown 代码块：

{{
  "knowledgeBase": {{
    "level": "beginner/intermediate/advanced",
    "description": "用1-2句话概括该学生的知识基础水平，要具体、有信息量",
    "masteredTopics": ["已掌握知识点1", "已掌握知识点2"],
    "weakTopics": ["薄弱知识点1", "薄弱知识点2"]
  }},
  "cognitiveStyle": {{
    "type": "visual/auditory/kinesthetic/reading",
    "description": "用1-2句话描述该学生的认知风格特征",
    "preferences": ["偏好1", "偏好2"]
  }},
  "learningGoal": {{
    "shortTerm": "短期目标",
    "longTerm": "长期目标",
    "currentCourse": "当前课程"
  }},
  "errorPattern": {{
    "description": "用1-2句话描述该学生的易错模式",
    "frequentErrors": ["高频错误1", "高频错误2"],
    "errorType": "conceptual/careful/procedural"
  }},
  "learningPace": {{
    "speed": "slow/moderate/fast",
    "description": "用1-2句话描述该学生的学习节奏",
    "weeklyHours": 0
  }},
  "resourcePreference": {{
    "preferences": ["video", "document", "quiz"],
    "description": "用1-2句话描述该学生的资源偏好"
  }},
  "clinicalExperience": {{
    "level": "none/basic/moderate/extensive",
    "description": "用1-2句话描述该学生的临床经验"
  }},
  "emotionState": {{
    "status": "motivated/anxious/confident/overwhelmed",
    "description": "用1-2句话描述该学生当前的情绪状态"
  }}
}}

注意：
1. 只输出 JSON，不要任何解释文字
2. description 必须具体、有信息量，不要写"根据对话推断""暂无信息""信息不足"等无意义的话；如果某维度确实无法判断，description 留空字符串
3. masteredTopics/weakTopics/frequentErrors/preferences 列表中的元素要具体，不要写"待补充"等占位文字；如果无法提取则留空列表
4. level/speed/errorType 等枚举值必须从给定选项中选择"""

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content="你是一位专业的学习画像分析专家，只输出 JSON 格式的画像维度数据。"),
            HumanMessage(content=extract_prompt),
        ]
        response = await llm.ainvoke(messages)
        content = getattr(response, "content", "")

        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        import json as _json
        dimensions = _json.loads(content)

        return {"code": 1, "msg": "success", "data": {"dimensions": dimensions}}
    except Exception as e:
        logger.error(f"[profile_extract] 画像维度抽取失败: {e}")
        raise HTTPException(status_code=500, detail=f"画像维度抽取失败: {str(e)}")


def _extract_profile_from_conversation(conversation: str) -> dict:
    """从对话内容中提取画像维度（同步版本，供后台任务调用）"""
    llm = resources.get("llm_turbo")
    if not llm:
        logger.warning("[profile_extract] LLM未就绪，无法提取画像")
        return None

    extract_prompt = f"""你是一位专业的学习画像分析专家。请从以下师生对话内容中，自动抽取学生的结构化学习画像维度。

对话内容：
{conversation}

请严格按以下 JSON 格式输出，不要输出任何其他内容，不要使用 markdown 代码块：

{{
  "knowledgeBase": {{
    "level": "beginner/intermediate/advanced",
    "description": "用1-2句话概括该学生的知识基础水平，要具体、有信息量",
    "masteredTopics": ["已掌握知识点1", "已掌握知识点2"],
    "weakTopics": ["薄弱知识点1", "薄弱知识点2"]
  }},
  "cognitiveStyle": {{
    "type": "visual/auditory/kinesthetic/reading",
    "description": "用1-2句话描述该学生的认知风格特征",
    "preferences": ["偏好1", "偏好2"]
  }},
  "learningGoal": {{
    "shortTerm": "短期目标",
    "longTerm": "长期目标",
    "currentCourse": "当前课程"
  }},
  "errorPattern": {{
    "description": "用1-2句话描述该学生的易错模式",
    "frequentErrors": ["高频错误1", "高频错误2"],
    "errorType": "conceptual/careful/procedural"
  }},
  "learningPace": {{
    "speed": "slow/moderate/fast",
    "description": "用1-2句话描述该学生的学习节奏",
    "weeklyHours": 0
  }},
  "resourcePreference": {{
    "preferences": ["video", "document", "quiz"],
    "description": "用1-2句话描述该学生的资源偏好"
  }},
  "clinicalExperience": {{
    "level": "none/basic/moderate/extensive",
    "description": "用1-2句话描述该学生的临床经验"
  }},
  "emotionState": {{
    "status": "motivated/anxious/confident/overwhelmed",
    "description": "用1-2句话描述该学生当前的情绪状态"
  }}
}}

注意：
1. 只输出 JSON，不要任何解释文字
2. description 必须具体、有信息量，不要写"根据对话推断""暂无信息""信息不足"等无意义的话；如果某维度确实无法判断，description 留空字符串
3. masteredTopics/weakTopics/frequentErrors/preferences 列表中的元素要具体，不要写"待补充"等占位文字；如果无法提取则留空列表
4. level/speed/errorType 等枚举值必须从给定选项中选择"""

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        import json as _json
        import asyncio
        import threading

        result_container = [None]

        def _run_sync():
            loop = asyncio.new_event_loop()
            try:
                messages = [
                    SystemMessage(content="你是一位专业的学习画像分析专家，只输出 JSON 格式的画像维度数据。"),
                    HumanMessage(content=extract_prompt),
                ]
                response = loop.run_until_complete(llm.ainvoke(messages))
                content = getattr(response, "content", "")

                content = content.strip()
                if content.startswith("```json"):
                    content = content[7:]
                if content.startswith("```"):
                    content = content[3:]
                if content.endswith("```"):
                    content = content[:-3]
                content = content.strip()

                result_container[0] = _json.loads(content)
            finally:
                loop.close()

        thread = threading.Thread(target=_run_sync)
        thread.start()
        thread.join(timeout=30)

        if thread.is_alive():
            logger.error("[profile_extract] 画像提取超时(30s)")
            return None

        result = result_container[0]
        if result and isinstance(result, dict) and len(result) > 0:
            logger.info(f"[profile_extract] 成功提取 {len(result)} 个画像维度")
            return result
        else:
            logger.warning("[profile_extract] 提取结果为空或格式错误")
            return None

    except Exception as e:
        logger.error(f"[profile_extract] 画像提取异常: {e}", exc_info=True)
        return None


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
    """综合资源生成（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = request.talkId or str(uuid.uuid4().int % 100000)
    new_talk = request.talkId is None

    resource_context = f"【课程信息】\n"
    if request.courseName:
        resource_context += f"- 课程名称：{request.courseName}\n"
    if request.knowledgePoints:
        resource_context += f"- 目标知识点：{', '.join(request.knowledgePoints)}\n"
    if request.difficulty:
        resource_context += f"- 难度级别：{request.difficulty}\n"
    if request.resourceTypes:
        resource_context += f"- 资源格式要求：{', '.join(request.resourceTypes)}\n"

    output_requirements = """【输出要求】
1. 生成具体的知识内容，包括定义、要点、临床应用等
2. 提供详细的知识点讲解（每个知识点200-300字）
3. 包含典型案例和实践应用
4. 给出自测检查点和拓展阅读材料
5. 使用通俗易懂的语言，适合医学生学习"""

    combined_message = f"【任务类型：学习资源内容生成】\n请为以下学习需求生成具体的教学内容和知识点讲解。\n\n{request.message}\n\n{resource_context}\n{output_requirements}"

    task_mgr.create_task(task_id, "resource_generate", {"talkId": talk_id})

    asyncio.create_task(_run_agent_background(
        task_id=task_id,
        agent=agent,
        case_text=combined_message,
        all_info="",
        report_mode="resource_generate",
        task_mgr=task_mgr,
        naming_model=resources.get("naming_model") if new_talk else None,
        executor=resources.get("executor"),
        naming_input=request.message if new_talk else None,
        images=request.images if request.images else None,
        image_question=request.message,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": new_talk}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


@app.post("/model/resources/generate/document")
async def generate_document(request: SingleDocumentRequest):
    """生成课程讲解文档（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = str(uuid.uuid4().int % 100000)
    combined_message = f"请生成课程讲解文档。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n难度：{request.difficulty}\n风格：{request.style}"

    task_mgr.create_task(task_id, "document_generate", {"talkId": talk_id})
    asyncio.create_task(_run_agent_background(
        task_id=task_id, agent=agent, case_text=combined_message, all_info="",
        report_mode="resource_generate", task_mgr=task_mgr,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": True}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


@app.post("/model/resources/generate/mindmap")
async def generate_mindmap(request: SingleMindmapRequest):
    """生成知识点思维导图（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = str(uuid.uuid4().int % 100000)
    combined_message = f"请生成知识点思维导图。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n格式：{request.format}\n展开层级：{request.depth}"

    task_mgr.create_task(task_id, "mindmap_generate", {"talkId": talk_id})
    asyncio.create_task(_run_agent_background(
        task_id=task_id, agent=agent, case_text=combined_message, all_info="",
        report_mode="resource_generate", task_mgr=task_mgr,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": True}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


@app.post("/model/resources/generate/quiz")
async def generate_quiz(request: SingleQuizRequest):
    """生成练习题目（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = str(uuid.uuid4().int % 100000)
    combined_message = f"请生成练习题目。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n难度：{request.difficulty}\n题目类型：{', '.join(request.quizTypes)}\n数量：{request.count}\n{'包含参考答案' if request.includeAnswer else '不包含参考答案'}"

    task_mgr.create_task(task_id, "quiz_generate", {"talkId": talk_id})
    asyncio.create_task(_run_agent_background(
        task_id=task_id, agent=agent, case_text=combined_message, all_info="",
        report_mode="resource_generate", task_mgr=task_mgr,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": True}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


@app.post("/model/resources/generate/reading")
async def generate_reading(request: SingleReadingRequest):
    """生成拓展阅读材料（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = str(uuid.uuid4().int % 100000)
    combined_message = f"请生成拓展阅读材料。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n类型：{request.readingType}\n语言：{request.language}\n数量：{request.count}"

    task_mgr.create_task(task_id, "reading_generate", {"talkId": talk_id})
    asyncio.create_task(_run_agent_background(
        task_id=task_id, agent=agent, case_text=combined_message, all_info="",
        report_mode="resource_generate", task_mgr=task_mgr,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": True}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


@app.post("/model/resources/generate/video-script")
async def generate_video_script(request: SingleVideoScriptRequest):
    """生成教学视频/动画脚本（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = str(uuid.uuid4().int % 100000)
    combined_message = f"请生成教学视频/动画脚本。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n预期时长：{request.duration}\n风格：{request.style}\n{'包含旁白脚本' if request.includeNarration else '不包含旁白脚本'}\n{'包含画面描述' if request.includeVisual else '不包含画面描述'}"

    task_mgr.create_task(task_id, "video_script_generate", {"talkId": talk_id})
    asyncio.create_task(_run_agent_background(
        task_id=task_id, agent=agent, case_text=combined_message, all_info="",
        report_mode="resource_generate", task_mgr=task_mgr,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": True}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


@app.post("/model/resources/generate/code-practice")
async def generate_code_practice(request: SingleCodePracticeRequest):
    """生成代码实操案例（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = str(uuid.uuid4().int % 100000)
    combined_message = f"请生成代码实操案例。\n课程：{request.courseName}\n知识点：{', '.join(request.knowledgePoints)}\n编程语言：{request.language}\n项目类型：{request.projectType}\n难度：{request.difficulty}\n{'包含测试用例' if request.includeTest else '不包含测试用例'}\n{'包含代码注释说明' if request.includeExplanation else '不包含代码注释说明'}"

    task_mgr.create_task(task_id, "code_practice_generate", {"talkId": talk_id})
    asyncio.create_task(_run_agent_background(
        task_id=task_id, agent=agent, case_text=combined_message, all_info="",
        report_mode="resource_generate", task_mgr=task_mgr,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": True}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


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
    """智能辅导问答（SSE 流式 + 后台持久化）"""
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = request.talkId or str(uuid.uuid4().int % 100000)
    new_talk = request.talkId is None

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

    task_mgr.create_task(task_id, "tutor_ask", {"talkId": talk_id})

    asyncio.create_task(_run_agent_background(
        task_id=task_id,
        agent=agent,
        case_text=combined_message,
        all_info="",
        report_mode="tutor",
        task_mgr=task_mgr,
        naming_model=resources.get("naming_model") if new_talk else None,
        executor=resources.get("executor"),
        naming_input=request.question if new_talk else None,
        images=request.images if request.images else None,
        image_question=request.question,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": new_talk}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


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
    return {"code": 1, "msg": "success", "data": {"overallScore": 0, "level": "unknown", "period": period, "dimensions": {}, "strengths": [], "weaknesses": [], "suggestions": [], "generateTime": ""}}


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
        evaluation_str = json.dumps(request.evaluationData, ensure_ascii=False) if request.evaluationData else "无评估数据"
        path_info_str = json.dumps(request.pathInfo, ensure_ascii=False) if request.pathInfo else "无路径信息"
        steps_str = json.dumps(request.steps, ensure_ascii=False) if request.steps else "无步骤信息"

        completed_count = sum(1 for s in (request.steps or []) if s.get("status") == "completed")
        not_started_count = sum(1 for s in (request.steps or []) if s.get("status") == "not_started")
        overall_score = 0
        if request.evaluationData and isinstance(request.evaluationData, dict):
            overall_score = request.evaluationData.get("overallScore", 0)

        prompt = f"""你是高等教育学习方案优化专家。请根据以下评估数据和学习路径信息，给出具体的优化方案。

学习路径ID：{request.pathId}
触发原因：{request.triggerReason}
综合评分：{overall_score}

学习路径信息：{path_info_str}

学习步骤详情：{steps_str}

完成情况：已完成{completed_count}步，未开始{not_started_count}步

评估数据：{evaluation_str}

请分析评估数据中的薄弱点，结合学习步骤的实际完成情况，给出优化方案。

重要规则：
- 如果综合评分>=80且无明显薄弱点，设置optimizationApplied为false
- 对于未完成且难度偏高的步骤，降低难度（adjust_difficulty）
- 对于薄弱知识点，可以插入补充步骤（insert_step）
- adjust_difficulty必须使用steps中真实的stepId
- insert_step的description写步骤标题，reason写插入原因

请直接输出JSON（不要用markdown代码块包裹）：
{{
    "pathId": {request.pathId},
    "optimizationApplied": true,
    "changes": [
        {{
            "type": "adjust_difficulty",
            "stepId": 真实步骤ID,
            "newDifficulty": "beginner或intermediate或advanced",
            "description": "调整描述",
            "reason": "调整原因"
        }}
    ],
    "newEstimatedDays": 30,
    "profileUpdated": false,
    "profileChanges": {{}}
}}"""

        response = await llm_turbo.ainvoke([HumanMessage(content=prompt)])
        content = getattr(response, "content", "")

        result = _parse_json(content)
        if not result:
            result = {"pathId": request.pathId, "optimizationApplied": False, "changes": [], "newEstimatedDays": 0, "profileUpdated": False, "profileChanges": {}}

        if "pathId" not in result:
            result["pathId"] = request.pathId
        if "optimizationApplied" not in result:
            result["optimizationApplied"] = False
        if "changes" not in result:
            result["changes"] = []

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
    """兼容旧版临床推理接口（SSE 流式 + 后台持久化）"""
    verify_token(request.token)

    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex

    if request.images:
        vision_svc = resources.get("vision_service")
        if not vision_svc:
            return EventSourceResponse(iter([json.dumps({"type": "token", "content": "影像识别服务未就绪，请稍后重试。"}, ensure_ascii=False)]), ping=15)

        task_mgr.create_task(task_id, "legacy_vision", {})

        async def _run_vision():
            try:
                final_parts = []
                async for event in vision_svc.analyze_stream(
                    images=request.images,
                    question=request.question,
                    all_info=request.all_info,
                ):
                    if event.get("type") == "thinking":
                        task_mgr.add_event(task_id, {"type": "node_start", "node": "vision", "label": event.get("title", "正在分析图片...")})
                    elif event.get("type") == "chunk":
                        content_str = str(event.get("content", ""))
                        if content_str:
                            final_parts.append(content_str)
                            task_mgr.add_event(task_id, {"type": "token", "content": content_str})

                task_mgr.add_event(task_id, {"type": "done", "taskId": task_id, "request_id": task_id, "name": "影像分析", "all_info": request.all_info})
                task_mgr.complete_task(task_id, result="".join(final_parts))
            except Exception as e:
                task_mgr.add_event(task_id, build_error_event(e, talk_id=None))
                task_mgr.fail_task(task_id, str(e))

        asyncio.create_task(_run_vision())
        init_event = {"type": "init", "taskId": task_id}
        return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)

    task_mgr.create_task(task_id, "legacy_query", {})

    asyncio.create_task(_run_agent_background(
        task_id=task_id,
        agent=agent,
        case_text=request.question,
        all_info=request.all_info,
        report_mode=request.report_mode,
        task_mgr=task_mgr,
        naming_model=resources.get("naming_model") if not request.all_info else None,
        executor=resources.get("executor"),
        naming_input=request.question if not request.all_info else None,
        update_all_info=True,
        original_all_info=request.all_info,
    ))

    init_event = {"type": "init", "taskId": task_id}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


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
# 后台任务查询与重连接口
# ============================================================

@app.get("/model/tasks/{task_id}")
async def get_task_status(task_id: str = Path(...)):
    """查询后台任务状态与结果（切换页面后轮询此接口获取结果）"""
    task_mgr = resources["task_manager"]
    task = task_mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    token_events = []
    for e in task.events:
        if e.get("type") == "token":
            token_events.append(e.get("content", ""))

    return {
        "taskId": task.task_id,
        "taskType": task.task_type,
        "status": task.status,
        "result": task.result,
        "content": "".join(token_events),
        "events": task.events,
        "metadata": task.metadata,
        "createdAt": task.created_at,
        "completedAt": task.completed_at,
    }


@app.get("/model/tasks/{task_id}/stream")
async def stream_task_result(
    task_id: str = Path(...),
    last_event_index: int = Query(0, ge=0, description="上次接收到的最后事件索引"),
):
    """重连后台任务的 SSE 流（切换页面后用此接口继续接收事件）"""
    task_mgr = resources["task_manager"]
    task = task_mgr.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def generate():
        event_index = last_event_index
        while True:
            task = task_mgr.get_task(task_id)
            if not task:
                yield json.dumps({"type": "error", "content": "Task not found"}, ensure_ascii=False)
                return
            while event_index < len(task.events):
                yield json.dumps(task.events[event_index], ensure_ascii=False)
                event_index += 1
            if task.status in ("completed", "failed"):
                return
            await task.wait_for_new_event(event_index, timeout=2.0)

    return EventSourceResponse(generate(), ping=15)


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