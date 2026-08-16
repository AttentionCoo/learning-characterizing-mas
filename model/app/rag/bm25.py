"""轻量 BM25 检索器：替代 langchain-community 的 BM25Retriever（该库已宣布停止维护）。

对中文医学文本使用「拉丁词整词 + CJK 字符二元组」分词，无需额外分词依赖；
原 BM25Retriever 的默认分词按空白切分，对无空格的中文文本基本失效，本实现修复了该问题。

API 与原 BM25Retriever 保持兼容：from_documents(...) / .k / .invoke(query)。
与原来不同的是：查询与语料完全无词项重叠时返回空列表，而不是按插入顺序返回 k 篇，
避免把无关文档送进 RRF 融合。
"""
import logging
from typing import Callable, List, Optional

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

_CJK_RANGES = (
    (0x3400, 0x4DBF),   # CJK 扩展 A
    (0x4E00, 0x9FFF),   # CJK 统一表意
)


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def tokenize(text: str) -> List[str]:
    """中英混合分词。

    - ASCII 字母数字连续段 → 单个小写词（如 "tPA" → "tpa"）
    - 连续 CJK 字符段 → 重叠二元组（单个字符则保留单字），
      二元组能显著提升无分词器环境下的中文 BM25 召回
    - 标点/空白作为分段边界，不产生词项
    """
    tokens: List[str] = []
    ascii_buf: List[str] = []
    cjk_buf: List[str] = []

    def flush_ascii():
        if ascii_buf:
            tokens.append("".join(ascii_buf).lower())
            ascii_buf.clear()

    def flush_cjk():
        if cjk_buf:
            if len(cjk_buf) == 1:
                tokens.append(cjk_buf[0])
            else:
                for i in range(len(cjk_buf) - 1):
                    tokens.append(cjk_buf[i] + cjk_buf[i + 1])
            cjk_buf.clear()

    for ch in text:
        if ch.isascii() and ch.isalnum():
            flush_cjk()
            ascii_buf.append(ch)
        elif _is_cjk(ch):
            flush_ascii()
            cjk_buf.append(ch)
        else:
            flush_ascii()
            flush_cjk()

    flush_ascii()
    flush_cjk()
    return tokens


class BM25Retriever:
    """与 langchain_community.retrievers.BM25Retriever 兼容的轻量实现。"""

    def __init__(
        self,
        documents: List[Document],
        k: int = 4,
        tokenizer: Optional[Callable[[str], List[str]]] = None,
    ):
        self.k = k
        self.docs = list(documents)
        self.tokenizer = tokenizer or tokenize
        self._corpus_tokens = [self.tokenizer(doc.page_content) for doc in self.docs]
        if self.docs:
            self._bm25 = BM25Okapi(self._corpus_tokens)
        else:
            self._bm25 = None

    @classmethod
    def from_documents(cls, documents: List[Document], **kwargs) -> "BM25Retriever":
        return cls(documents, **kwargs)

    def invoke(self, query: str) -> List[Document]:
        if not self._bm25 or not self.docs:
            return []
        query_tokens = self.tokenizer(query)
        if not query_tokens:
            return []
        scores = self._bm25.get_scores(query_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        # 注意：rank_bm25 的 idf 在词项出现于大多数文档时为负，
        # 匹配文档的总分可能为负，不能用「分数 > 0」判断相关性；
        # 用词项重叠过滤零相关文档，用 BM25 分数排序。
        query_set = set(query_tokens)
        top = [
            i for i in ranked
            if query_set & set(self._corpus_tokens[i])
        ][: self.k]
        if not top:
            logger.info("🔍 [BM25] 查询与语料无词项重叠，返回空结果: %s", query[:60])
            return []
        return [self.docs[i] for i in top]
