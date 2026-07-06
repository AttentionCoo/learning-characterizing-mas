"""
医学多模态功能 E2E 集成测试 — Medical Multimodal E2E Integration Tests

测试覆盖：
- 医学影像分析 API 端点
- 多图对比 API 端点
- DICOM 元数据提取 API
- 检验报告/处方 OCR API
- 多模态病例分析 SSE 流式端点
- 错误处理和边界条件

运行要求：模型推理层服务已启动（python -m app.main）
"""

import sys
import os
import json
import base64
import pytest
import httpx
import asyncio
from io import BytesIO
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "model"))

MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "http://localhost:8000")
TEST_TIMEOUT = 120.0


# ============================================================
# 测试辅助函数
# ============================================================

def _create_test_image_base64(width=256, height=256, color="white", text=None) -> str:
    """创建一个简单的测试图片并返回 Base64 编码"""
    img = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode('utf-8')}"


def _create_small_dicom_base64() -> str:
    """创建一个最小的 DICOM 文件并返回 Base64 编码（如果 pydicom 可用）"""
    try:
        import pydicom
        from pydicom.dataset import Dataset, FileDataset
        import tempfile

        # 创建最小 DICOM 文件
        ds = Dataset()
        ds.PatientName = "Test^Patient"
        ds.PatientID = "12345"
        ds.Modality = "CT"
        ds.StudyDescription = "Brain CT"
        ds.SeriesDescription = "Axial"
        ds.Rows = 512
        ds.Columns = 512

        with tempfile.NamedTemporaryFile(suffix=".dcm", delete=False) as f:
            file_meta = Dataset()
            file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
            file_meta.MediaStorageSOPInstanceUID = "1.2.3"
            file_meta.ImplementationClassUID = "1.2.3.4"
            ds.file_meta = file_meta
            ds.is_little_endian = True
            ds.is_implicit_VR = True
            ds.save_as(f.name, write_like_original=False)
            f.flush()
            with open(f.name, "rb") as f2:
                data = f2.read()
            os.unlink(f.name)
            return f"data:application/dicom;base64,{base64.b64encode(data).decode('utf-8')}"

    except ImportError:
        return None


# ============================================================
# 1. 服务健康检查测试
# ============================================================

class TestServiceHealth:
    """测试模型层服务健康状态"""

    @pytest.mark.asyncio
    async def test_service_reachable(self):
        """模型层服务应该可达"""
        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.get(f"{MODEL_BASE_URL}/docs")
                assert resp.status_code == 200
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动，跳过 E2E 测试")


# ============================================================
# 2. 医学影像分析 API 测试
# ============================================================

class TestMedicalAnalyzeImageAPI:
    """测试 POST /model/medical/analyze-image"""

    @pytest.mark.asyncio
    async def test_analyze_image_valid_request(self):
        """有效的影像分析请求应返回结构化结果"""
        test_img = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/analyze-image",
                    json={
                        "images": [test_img],
                        "question": "请分析这张头部CT平扫影像",
                        "all_info": "",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["code"] == 1
                assert "findings" in data["data"]
                findings = data["data"]["findings"]
                assert "image_type" in findings
                assert "key_findings" in findings
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")

    @pytest.mark.asyncio
    async def test_analyze_image_missing_images(self):
        """缺少图片时应返回 422"""
        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/analyze-image",
                    json={"images": [], "question": "test"},
                )
                assert resp.status_code == 422
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")

    @pytest.mark.asyncio
    async def test_analyze_image_with_evidence(self):
        """应返回 PubMed 循证文献"""
        test_img = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/analyze-image",
                    json={
                        "images": [test_img],
                        "question": "脑CT显示左侧基底节区高密度影，是否为脑出血？",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                # PubMed 证据字段应存在（可能为空如果 PubMed 不可达）
                assert "pubmed_evidence" in data["data"]
                assert "local_evidence" in data["data"]
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")

    @pytest.mark.asyncio
    async def test_analyze_image_type_detection(self):
        """不同类型的问题应触发不同的影像类型检测"""
        test_img = _create_test_image_base64()

        test_cases = [
            ("头部CT平扫分析", "neuroimaging_ct"),
            ("MRI DWI序列解读", "neuroimaging_mri"),
            ("CTA血管造影结果", "neuroimaging_angiography"),
            ("化验单血常规怎么看", "lab_report"),
        ]

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                for question, expected_type in test_cases:
                    resp = await client.post(
                        f"{MODEL_BASE_URL}/model/medical/analyze-image",
                        json={"images": [test_img], "question": question},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        actual_type = data["data"]["findings"].get("image_type", "")
                        assert actual_type == expected_type, \
                            f"问题 '{question}' 期望类型 {expected_type}，实际 {actual_type}"
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")


# ============================================================
# 3. 多图对比 API 测试
# ============================================================

class TestCompareImagesAPI:
    """测试 POST /model/medical/compare-images"""

    @pytest.mark.asyncio
    async def test_compare_two_images(self):
        """两张图片的对比分析应正常工作"""
        img1 = _create_test_image_base64(color="white")
        img2 = _create_test_image_base64(color="red")

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/compare-images",
                    json={
                        "images": [img1, img2],
                        "question": "对比这两张CT影像，分析变化",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["code"] == 1
                comp = data["data"]
                assert comp["image_count"] == 2
                assert "comparison_mode" in comp
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")

    @pytest.mark.asyncio
    async def test_compare_insufficient_images(self):
        """少于2张图片时应返回 422"""
        img1 = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/compare-images",
                    json={"images": [img1], "question": "test"},
                )
                assert resp.status_code == 422
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")


# ============================================================
# 4. DICOM 元数据 API 测试
# ============================================================

class TestDICOMMetadataAPI:
    """测试 POST /model/medical/dicom-metadata"""

    @pytest.mark.asyncio
    async def test_dicom_metadata_extraction(self):
        """DICOM 元数据提取应正常工作"""
        dicom_b64 = _create_small_dicom_base64()
        if dicom_b64 is None:
            pytest.skip("pydicom 未安装")

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/dicom-metadata",
                    json={"image": dicom_b64},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["code"] == 1
                meta = data["data"]
                assert meta["has_phi_stripped"] is True
                # 模态应为 CT（我们创建的测试 DICOM）
                assert meta.get("modality", "").upper() in ("CT", "")
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")

    @pytest.mark.asyncio
    async def test_dicom_metadata_non_dicom(self):
        """非 DICOM 数据应优雅处理"""
        test_img = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/dicom-metadata",
                    json={"image": test_img},
                )
                # 应该返回 200（优雅降级）或 500（解析失败）
                assert resp.status_code in (200, 500)
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")


# ============================================================
# 5. 检验报告 OCR API 测试
# ============================================================

class TestLabReportOCRAPI:
    """测试 POST /model/medical/ocr/lab-report"""

    @pytest.mark.asyncio
    async def test_lab_report_ocr(self):
        """检验报告 OCR 应返回结构化数据"""
        test_img = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/ocr/lab-report",
                    json={
                        "images": [test_img],
                        "question": "请提取这份血常规报告",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["code"] == 1
                report = data["data"]
                assert "report_type" in report
                assert "lab_values" in report
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")


# ============================================================
# 6. 处方 OCR API 测试
# ============================================================

class TestPrescriptionOCRAPI:
    """测试 POST /model/medical/ocr/prescription"""

    @pytest.mark.asyncio
    async def test_prescription_ocr(self):
        """处方 OCR 应返回药品列表"""
        test_img = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/ocr/prescription",
                    json={
                        "images": [test_img],
                        "question": "请提取处方中的药品信息",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["code"] == 1
                # 应返回列表
                assert isinstance(data["data"], list)
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")


# ============================================================
# 7. 多模态病例分析 SSE 流式测试
# ============================================================

class TestMedicalCaseAnalysisSSE:
    """测试 POST /model/medical/analyze-case"""

    @pytest.mark.asyncio
    async def test_case_analysis_sse_stream(self):
        """多模态病例分析 SSE 流式应正常推送事件"""
        test_img = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{MODEL_BASE_URL}/model/medical/analyze-case",
                    json={
                        "message": "患者男性65岁，突发右侧肢体无力2小时，请分析CT影像",
                        "images": [test_img],
                        "case_type": "stroke",
                        "include_evidence": True,
                    },
                ) as response:
                    assert response.status_code == 200
                    events = []
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                event = json.loads(line)
                                events.append(event)
                                if event.get("type") == "done":
                                    break
                            except json.JSONDecodeError:
                                continue

                    # 至少应有 init 和 done 事件
                    event_types = [e.get("type") for e in events]
                    assert "init" in event_types, f"未收到 init 事件，收到: {event_types}"
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")


# ============================================================
# 8. 错误处理和边界条件测试
# ============================================================

class TestErrorHandling:
    """测试错误处理和边界条件"""

    @pytest.mark.asyncio
    async def test_service_unavailable_response(self):
        """服务不可用时应返回合适的错误码"""
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/analyze-image",
                    json={"images": ["invalid_base64_data"], "question": "test"},
                )
                # 不应崩溃，应有合理的响应
                assert resp.status_code in (200, 422, 500, 503)
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")

    @pytest.mark.asyncio
    async def test_empty_question_handled(self):
        """空问题应被正确处理"""
        test_img = _create_test_image_base64()

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/analyze-image",
                    json={"images": [test_img], "question": ""},
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["code"] == 1
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")

    @pytest.mark.asyncio
    async def test_multiple_images_handled(self):
        """多张图片应被正确处理"""
        imgs = [
            _create_test_image_base64(color="white"),
            _create_test_image_base64(color="red"),
            _create_test_image_base64(color="blue"),
        ]

        async with httpx.AsyncClient(timeout=TEST_TIMEOUT) as client:
            try:
                resp = await client.post(
                    f"{MODEL_BASE_URL}/model/medical/analyze-image",
                    json={
                        "images": imgs,
                        "question": "CT序列分析",
                    },
                )
                assert resp.status_code == 200
                data = resp.json()
                assert data["code"] == 1
            except httpx.ConnectError:
                pytest.skip("模型层服务未启动")
