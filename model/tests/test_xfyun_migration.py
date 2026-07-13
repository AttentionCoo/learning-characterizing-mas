"""讯飞迁移测试：鉴权签名、Embedding 协议、图片理解请求结构、无 DashScope 残留。"""
import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from app.utils.xfyun_auth import assemble_auth_url


class TestAuthUrl:
    URL = "wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image"

    def test_url_contains_required_params(self):
        signed = assemble_auth_url(self.URL, "test-key", "test-secret")
        qs = parse_qs(urlparse(signed).query)
        assert set(qs) == {"authorization", "date", "host"}
        assert qs["host"][0] == "spark-api.cn-huabei-1.xf-yun.com"
        assert signed.startswith(self.URL + "?")

    def test_signature_verifiable(self):
        """authorization 解码后可用同样的 secret 复算签名。"""
        signed = assemble_auth_url(self.URL, "my-key", "my-secret", method="GET")
        qs = parse_qs(urlparse(signed).query)
        auth = base64.b64decode(qs["authorization"][0]).decode()

        assert 'api_key="my-key"' in auth
        assert 'algorithm="hmac-sha256"' in auth
        assert 'headers="host date request-line"' in auth

        sig = auth.split('signature="')[1].rstrip('"')
        origin = (f"host: spark-api.cn-huabei-1.xf-yun.com\n"
                  f"date: {qs['date'][0]}\n"
                  f"GET /v2.1/image HTTP/1.1")
        expected = base64.b64encode(
            hmac.new(b"my-secret", origin.encode(), hashlib.sha256).digest()
        ).decode()
        assert sig == expected

    def test_post_method_in_request_line(self):
        signed = assemble_auth_url("https://emb-cn-huabei-1.xf-yun.com/",
                                   "k", "s", method="POST")
        auth = base64.b64decode(parse_qs(urlparse(signed).query)["authorization"][0]).decode()
        # 签名对象含 POST request-line：换 secret 复算 GET 版本应不相等
        sig = auth.split('signature="')[1].rstrip('"')
        date = parse_qs(urlparse(signed).query)["date"][0]
        get_origin = f"host: emb-cn-huabei-1.xf-yun.com\ndate: {date}\nGET / HTTP/1.1"
        get_sig = base64.b64encode(hmac.new(b"s", get_origin.encode(), hashlib.sha256).digest()).decode()
        assert sig != get_sig


class TestXfyunEmbeddings:
    def _make(self, monkeypatch):
        monkeypatch.setenv("XFYUN_APP_ID", "app1")
        monkeypatch.setenv("XFYUN_API_KEY", "key1")
        monkeypatch.setenv("XFYUN_API_SECRET", "sec1")
        monkeypatch.setenv("XFYUN_EMBEDDING_URL", "https://emb-cn-huabei-1.xf-yun.com/")
        from app.rag.retrievers import XfyunEmbeddings
        return XfyunEmbeddings()

    def _mock_response(self, vector):
        import struct
        resp = MagicMock()
        vec_bytes = struct.pack(f"{len(vector)}f", *vector)
        resp.json.return_value = {
            "header": {"code": 0, "message": "success"},
            "payload": {"feature": {"text": base64.b64encode(vec_bytes).decode()}},
        }
        return resp

    def test_embed_query_parses_vector(self, monkeypatch):
        emb = self._make(monkeypatch)
        with patch("requests.post", return_value=self._mock_response([0.1, 0.2, 0.3])) as mock_post:
            vec = emb.embed_query("脑卒中")
        assert len(vec) == 3
        assert abs(vec[1] - 0.2) < 1e-6
        # 官方 HTTP 接口使用单一地址，通过 domain 参数区分 query/para
        assert "emb-cn-huabei-1.xf-yun.com" in mock_post.call_args[0][0]
        body = mock_post.call_args[1]["json"]
        assert body["parameter"]["emb"]["domain"] == "query"
        inner = json.loads(base64.b64decode(body["payload"]["messages"]["text"]))
        assert inner[0]["content"] == "脑卒中"

    def test_embed_documents_uses_para_domain(self, monkeypatch):
        emb = self._make(monkeypatch)
        with patch("requests.post", return_value=self._mock_response([1.0] * 4)) as mock_post:
            vecs = emb.embed_documents(["文档一", "文档二"])
        assert len(vecs) == 2
        assert mock_post.call_count == 2
        assert "emb-cn-huabei-1.xf-yun.com" in mock_post.call_args[0][0]
        body = mock_post.call_args[1]["json"]
        assert body["parameter"]["emb"]["domain"] == "para"

    def test_error_code_raises_after_retries(self, monkeypatch):
        emb = self._make(monkeypatch)
        bad = MagicMock()
        bad.json.return_value = {"header": {"code": 11202, "message": "licc failed"}}
        with patch("requests.post", return_value=bad), patch("time.sleep"):
            with pytest.raises(ValueError, match="11202"):
                emb.embed_query("x")

    def test_error_code_raises_after_retries(self, monkeypatch):
        emb = self._make(monkeypatch)
        bad = MagicMock()
        bad.json.return_value = {"header": {"code": 11202, "message": "rate limit"}}
        with patch("requests.post", return_value=bad), patch("time.sleep"):
            with pytest.raises(ValueError, match="11202"):
                emb.embed_query("x")


class TestVisionService:
    def _make(self, monkeypatch):
        monkeypatch.setenv("XFYUN_APP_ID", "app1")
        monkeypatch.setenv("XFYUN_API_KEY", "key1")
        monkeypatch.setenv("XFYUN_API_SECRET", "sec1")
        from app.services.vision_service import VisionAnalysisService
        return VisionAnalysisService(prompt_manager=MagicMock(get=lambda *_: None))

    def test_request_image_must_be_first(self, monkeypatch):
        svc = self._make(monkeypatch)
        req = svc._build_request("aW1n", "这是什么？")
        text = req["payload"]["message"]["text"]
        assert text[0]["content_type"] == "image"
        assert text[1]["content_type"] == "text"
        assert req["header"]["app_id"] == "app1"
        assert req["parameter"]["chat"]["domain"] in ("general", "imagev3")

    def test_normalize_strips_data_url_prefix(self, monkeypatch):
        svc = self._make(monkeypatch)
        assert svc._normalize_image("data:image/png;base64,QUJD") == "QUJD"
        assert svc._normalize_image("QUJD") == "QUJD"

    def test_missing_credentials_degrades(self, monkeypatch):
        import asyncio

        for var in ("XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET"):
            monkeypatch.delenv(var, raising=False)
        from app.services.vision_service import VisionAnalysisService
        svc = VisionAnalysisService(prompt_manager=MagicMock(get=lambda *_: None))

        async def collect():
            return [e async for e in svc.analyze_stream(["QUJD"], "看图", "")]

        events = asyncio.run(collect())
        assert any("未配置" in e.get("content", "") for e in events)


def test_no_dashscope_left_in_core_paths():
    """对话/视觉/向量主链路不应再引用 DashScope（rerank 可选保留除外）。"""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app"
    for rel in ("main.py", "services/vision_service.py", "utils/naming_model.py", "rag/qa_generator.py"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "dashscope" not in text.lower(), f"{rel} 仍引用 DashScope"
