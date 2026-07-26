import logging
import requests
from typing import List
from app.agents.schemas.retrieval import RerankResult
from app.agents.core.decorators import retry
from app.agents.infra.base_reranker import BaseReranker
from app.config.qwen import get_qwen_api_key, get_qwen_rerank_model

logger = logging.getLogger(__name__)


class DashScopeReranker(BaseReranker):
    BASE_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"

    def __init__(self):
        self.api_key = get_qwen_api_key(required=False)
        if not self.api_key:
            raise ValueError("未找到 QWEN_API_KEY 或 DASHSCOPE_API_KEY 环境变量")
        self.model = get_qwen_rerank_model()
        logger.info(f"✅ Qwen Reranker 初始化完成: {self.model}")

    @retry(max_retries=3, delay=1)
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5
    ) -> List[RerankResult]:

        if not documents:
            return []

        payload = {
            "model": self.model,
            "input": {
                "query": query,
                "documents": documents
            },
            "parameters": {
                "top_n": min(top_k, len(documents)),
                "return_documents": True
            }
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            self.BASE_URL,
            headers=headers,
            json=payload,
            timeout=15
        )

        response.raise_for_status()

        result = response.json()

        if result.get("code") not in (None, "200"):
            raise RuntimeError(result.get("message", "rerank失败"))

        output = result["output"]["results"]

        return [
            RerankResult(
                index=item["index"],
                content=item["document"]["text"],
                score=item["relevance_score"]
            )
            for item in output
        ]
