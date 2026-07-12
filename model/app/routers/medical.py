"""医学多模态影像接口：影像分析 / 病例综合分析 / DICOM / OCR。

医学影像子系统（MedicalVisionService + OCR + VisionRAGBridge + VisionAnalysisNode）
由 main.py lifespan 初始化后注入 runtime.resources。
"""
import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.runtime import resources
from app.services.agent_runner import run_agent_background as _run_agent_background
from app.services.agent_runner import stream_task_events as _stream_task_events
from app.services.medical_vision_service import MedicalVisionService
from app.schemas.medical_image import (
    MedicalImageAnalysisRequest,
    MedicalImageAnalysisResponse,
    MedicalCaseAnalysisRequest,
    CompareImagesRequest,
    DICOMMetadataRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/model/medical/analyze-image")
async def medical_analyze_image(request: MedicalImageAnalysisRequest):
    """医学影像结构化分析接口（非流式，返回结构化 JSON）

    支持：CT/MRI/DSA/病理/心电图/临床照片/检验报告/影像报告/医学图解/课件资料
    """
    medical_vision = resources.get("medical_vision_service")
    if not medical_vision:
        raise HTTPException(status_code=503, detail="Medical vision service not ready")

    if not request.images:
        raise HTTPException(status_code=422, detail="至少需要一张医学影像")

    try:
        # 结构化分析
        findings = await medical_vision.analyze_structured(
            images=request.images,
            question=request.question,
            all_info=request.all_info,
        )

        # Vision → PubMed 桥接
        pubmed_evidence = []
        local_evidence = []
        bridge = resources.get("vision_rag_bridge")
        if bridge:
            import asyncio
            pubmed_task = asyncio.create_task(
                bridge.search_pubmed_from_findings(findings, max_results=3)
            )
            local_evidence = bridge.search_local_knowledge(findings, top_k=3)
            try:
                pubmed_evidence = await pubmed_task
            except Exception as e:
                logger.warning(f"[medical/analyze-image] PubMed检索失败: {e}")

        return {
            "code": 1,
            "msg": "success",
            "data": MedicalImageAnalysisResponse(
                findings=findings,
                pubmed_evidence=pubmed_evidence,
                local_evidence=local_evidence,
                analysis_text=findings.raw_description,
            ).model_dump(),
        }

    except Exception as e:
        logger.error(f"[medical/analyze-image] 分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model/medical/analyze-case")
async def medical_analyze_case(request: MedicalCaseAnalysisRequest):
    """多模态病例综合分析接口（SSE 流式）

    同时处理文本+医学影像，影像分析结果自动融入多智能体推理流程。
    工作流：intent → vision → retrieve → reason → validate → report
    """
    agent = resources.get("model")
    if not agent:
        raise HTTPException(status_code=503, detail="Model service not ready")

    task_mgr = resources["task_manager"]
    task_id = uuid.uuid4().hex
    talk_id = request.talkId or str(uuid.uuid4().int % 100000)
    new_talk = request.talkId is None

    # 构建病例分析Prompt
    case_prefix = f"【多模态病例分析 - {request.case_type}】\n"
    if request.include_evidence:
        case_prefix += "请结合医学影像分析结果和循证医学证据，进行综合分析。\n"

    combined_message = f"{case_prefix}{request.message}"

    task_mgr.create_task(task_id, "medical_case_analysis", {"talkId": talk_id})

    asyncio.create_task(_run_agent_background(
        task_id=task_id,
        agent=agent,
        case_text=combined_message,
        all_info="",
        report_mode="tutor",  # 使用 tutor 模式以启用多智能体推理
        task_mgr=task_mgr,
        naming_model=resources.get("naming_model") if new_talk else None,
        executor=resources.get("executor"),
        naming_input=request.message if new_talk else None,
        images=request.images if request.images else None,
        image_question=request.message,
    ))

    init_event = {"type": "init", "taskId": task_id, "talkId": talk_id, "newTalk": new_talk, "mode": "medical_case_analysis"}
    return EventSourceResponse(_stream_task_events(task_id, task_mgr, init_event), ping=15)


@router.post("/model/medical/compare-images")
async def medical_compare_images(request: CompareImagesRequest):
    """多图对比分析接口

    支持同一模态的不同时间点对比（如治疗前后CT）或不同模态对比（CT vs MRI）。
    """
    medical_vision = resources.get("medical_vision_service")
    if not medical_vision:
        raise HTTPException(status_code=503, detail="Medical vision service not ready")

    if len(request.images) < 2:
        raise HTTPException(status_code=422, detail="至少需要2张图片进行对比分析")

    try:
        comparison = await medical_vision.compare_images(
            images=request.images,
            question=request.question,
            all_info=request.all_info,
        )
        return {"code": 1, "msg": "success", "data": comparison.model_dump()}

    except Exception as e:
        logger.error(f"[medical/compare-images] 对比分析失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model/medical/dicom-metadata")
async def medical_dicom_metadata(request: DICOMMetadataRequest):
    """DICOM文件元数据提取接口

    从DICOM文件中提取技术参数（不提取患者身份信息）。
    """
    try:
        metadata = MedicalVisionService.read_dicom_metadata(request.image)
        return {"code": 1, "msg": "success", "data": metadata.model_dump()}

    except Exception as e:
        logger.error(f"[medical/dicom-metadata] 提取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model/medical/ocr/lab-report")
async def medical_ocr_lab_report(request: MedicalImageAnalysisRequest):
    """检验报告OCR结构化提取接口"""
    ocr_service = resources.get("medical_ocr_service")
    if not ocr_service:
        raise HTTPException(status_code=503, detail="Medical OCR service not ready")

    if not request.images:
        raise HTTPException(status_code=422, detail="需要一张检验报告图片")

    try:
        lab_report = await ocr_service.extract_lab_report(
            image_base64=request.images[0],
            all_info=request.all_info,
        )
        return {"code": 1, "msg": "success", "data": lab_report.model_dump()}

    except Exception as e:
        logger.error(f"[medical/ocr/lab-report] 提取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model/medical/ocr/prescription")
async def medical_ocr_prescription(request: MedicalImageAnalysisRequest):
    """处方OCR结构化提取接口"""
    ocr_service = resources.get("medical_ocr_service")
    if not ocr_service:
        raise HTTPException(status_code=503, detail="Medical OCR service not ready")

    if not request.images:
        raise HTTPException(status_code=422, detail="需要一张处方图片")

    try:
        prescriptions = await ocr_service.extract_prescription(
            image_base64=request.images[0],
        )
        return {"code": 1, "msg": "success", "data": [p.model_dump() for p in prescriptions]}

    except Exception as e:
        logger.error(f"[medical/ocr/prescription] 提取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/model/medical/ocr/text")
async def medical_ocr_text(request: MedicalImageAnalysisRequest):
    """通用医学文档OCR流式识别接口"""
    ocr_service = resources.get("medical_ocr_service")
    if not ocr_service:
        raise HTTPException(status_code=503, detail="Medical OCR service not ready")

    if not request.images:
        raise HTTPException(status_code=422, detail="需要一张文档图片")

    async def generate():
        async for event in ocr_service.extract_text_stream(
            image_base64=request.images[0],
            document_type=request.expected_image_type or "general",
        ):
            yield json.dumps(event, ensure_ascii=False)

    return EventSourceResponse(generate(), ping=15)


@router.post("/model/medical/dicom-to-png")
async def medical_dicom_to_png(request: DICOMMetadataRequest):
    """DICOM 文件转 PNG 预览接口

    将 DICOM 文件（Base64编码）转换为 PNG 格式用于前端预览。
    应用默认脑窗窗宽窗位（WW=80, WL=40）。
    """
    try:
        png_base64 = MedicalVisionService.dicom_to_png_base64(request.image)
        if not png_base64:
            raise HTTPException(status_code=400, detail="DICOM 转换失败：无法读取像素数据，请确认文件为有效 DICOM 格式")
        return {"code": 1, "msg": "success", "data": {"image": png_base64}}
    except Exception as e:
        logger.error(f"[medical/dicom-to-png] 转换失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

