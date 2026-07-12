import asyncio
import concurrent.futures
import logging
import os
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from langchain_openai import ChatOpenAI

from app.agents.assistant import LearningAssistant
from app.agents.core.shared_memory import SharedMemorySystem
from app.agents.orchestrators.qwen_agent import LearningAgent
from app.config.config_loader import (
    get_expert_manager,
    get_limits_manager,
    get_prompt_manager,
    get_report_manager,
    get_shared_memory_manager,
    get_validation_manager,
)
from app.rag.retrieve import CONFIG, UnifiedSearchEngine
from app.routers import admin, evaluation, medical, profile, stream
from app.runtime import resources
from app.agents.orchestrators.nodes.vision_node import VisionAnalysisNode
from app.services.medical_ocr_service import MedicalOCRService
from app.services.medical_vision_service import MedicalVisionService
from app.services.vision_rag_bridge import VisionRAGBridge
from app.services.vision_service import VisionAnalysisService
from app.utils.context_summary import ConversationSummaryService
from app.utils.naming_model import NamingModel

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

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


def init_all_resources():
    start_time = time.time()
    logger.info("=" * 80)
    logger.info("🚀 开始初始化系统资源")
    logger.info("=" * 80)

    logger.info("📋 [1/8] 加载配置管理器...")
    prompt_mgr = get_prompt_manager()
    report_mgr = get_report_manager()
    expert_mgr = get_expert_manager()
    validation_mgr = get_validation_manager()
    limits_mgr = get_limits_manager()
    shared_memory_mgr = get_shared_memory_manager()

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
    logger.info(f"  ✅ 共享记忆配置: 自动存储={shared_memory_mgr.is_auto_store_enabled()}")

    logger.info("🤖 [2/8] 初始化大语言模型...")
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

    logger.info("💬 [3/8] 初始化上下文摘要服务...")
    context_summary = ConversationSummaryService(
        llm=llm_turbo,
        prompt_manager=prompt_mgr
    )
    logger.info("  ✅ 上下文摘要服务初始化完成")

    logger.info("🔍 [4/8] 初始化向量检索引擎...")
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

    logger.info("📚 [5/8] 初始化学习助手...")
    learning_assistant = LearningAssistant(
        llm_main=llm_max,
        llm_fast=llm_plus,
        retriever=retriever,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr
    )
    logger.info("  ✅ 学习助手初始化完成")

    logger.info("🧠 [6/8] 初始化共享记忆系统...")
    shared_memory_config = {
        "store": shared_memory_mgr.get_store_config(),
        "consensus": shared_memory_mgr.get_consensus_config(),
    }
    shared_memory_system = SharedMemorySystem(shared_memory_config)
    logger.info("  ✅ 共享记忆系统初始化完成")
    stats = shared_memory_system.store.get_stats()
    logger.info(f"     - 已有记忆: {stats.get('total', 0)} 条")
    rep_scores = shared_memory_system.consensus.reputation_store.get_all_scores()
    if rep_scores:
        logger.info(f"     - 信誉数据: {len(rep_scores)} 个智能体")

    logger.info("🧠 [7/10] 初始化医学多模态服务...")
    medical_vision_service = MedicalVisionService(prompt_manager=prompt_mgr)
    medical_ocr_service = MedicalOCRService(prompt_manager=prompt_mgr)
    vision_rag_bridge = VisionRAGBridge(
        unified_search_engine=retriever,
    )
    logger.info("  ✅ 医学影像分析服务初始化完成")
    logger.info("  ✅ 医学OCR服务初始化完成")
    logger.info("  ✅ Vision-RAG桥接服务初始化完成（本地知识库循证）")

    logger.info("🧠 [8/10] 初始化医学影像分析节点...")
    vision_node = VisionAnalysisNode(
        medical_vision_service=medical_vision_service,
        vision_rag_bridge=vision_rag_bridge,
        llm_fast=llm_plus,
    )
    logger.info("  ✅ VisionAnalysisNode 初始化完成")

    logger.info("🧠 [9/10] 初始化学习推理智能体...")
    agent = LearningAgent(
        llm_proposer=llm_max,
        llm_critic=llm_plus,
        learning_assistant=learning_assistant,
        prompt_manager=prompt_mgr,
        report_manager=report_mgr,
        llm_turbo=llm_turbo,
        shared_memory_system=shared_memory_system,
        vision_node=vision_node,
    )
    logger.info("  ✅ 学习推理智能体初始化完成（已集成医学多模态节点）")

    logger.info("🔧 [10/10] 初始化其他服务...")
    vision_service = VisionAnalysisService(prompt_manager=prompt_mgr)
    naming_model = NamingModel()
    logger.info("  ✅ 影像识别服务初始化完成")
    logger.info("  ✅ 命名模型初始化完成")

    init_time = time.time() - start_time
    logger.info("=" * 80)
    logger.info(f"🎉 系统初始化完成！耗时: {init_time:.2f}秒")
    logger.info("=" * 80)

    return agent, naming_model, context_summary, vision_service, medical_vision_service, medical_ocr_service, vision_rag_bridge, llm_turbo, learning_assistant


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info(">>> 正在初始化资源及加载模型...")
    resources["executor"] = concurrent.futures.ThreadPoolExecutor(max_workers=10)
    loop = asyncio.get_running_loop()

    try:
        agent, naming, context_summary, vision_service, medical_vision_service, medical_ocr_service, vision_rag_bridge, llm_turbo, learning_assistant = await loop.run_in_executor(
            resources["executor"], init_all_resources
        )
        resources["model"] = agent
        resources["naming_model"] = naming
        resources["context_summary"] = context_summary
        resources["vision_service"] = vision_service
        resources["medical_vision_service"] = medical_vision_service
        resources["medical_ocr_service"] = medical_ocr_service
        resources["vision_rag_bridge"] = vision_rag_bridge
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

app.include_router(stream.router)
app.include_router(profile.router)
app.include_router(evaluation.router)
app.include_router(admin.router)
app.include_router(medical.router)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
