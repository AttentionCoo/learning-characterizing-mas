import os
import re
import logging
import numpy as np
from pypdf import PdfReader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 文本清洗
# ═══════════════════════════════════════════════════════════════


def clean_text(text: str) -> str:
    """去除换行和多余空格，修复中文重复标点（递归切分用）"""
    text = text.replace("\n", "").replace(" ", "")
    text = text.replace("，，", "，").replace("。。", "。")
    return text.strip()


def clean_text_preserve_nl(text: str) -> str:
    """
    轻量清洗：保留换行（段落边界），仅去除空格和修复标点。
    语义分块专用——换行是重要的语义边界信号。
    """
    text = text.replace(" ", "")
    text = text.replace("，，", "，").replace("。。", "。")
    return text.strip()


# ═══════════════════════════════════════════════════════════════
# PDF 加载
# ═══════════════════════════════════════════════════════════════


def load_pdfs_from_dir(dir_path: str, clean_fn=clean_text):
    """从目录加载所有 PDF，逐页清洗后返回 Document 列表"""
    documents = []
    if not os.path.exists(dir_path):
        logger.warning(f"⚠️ 文档目录不存在: {dir_path}")
        return []
    for filename in os.listdir(dir_path):
        if not filename.lower().endswith(".pdf"):
            continue
        pdf_path = os.path.join(dir_path, filename)
        logger.info(f"📄 加载 PDF: {filename}")
        try:
            # 直接使用 pypdf 提取文本（替代已停止维护的 langchain-community PyPDFLoader）
            reader = PdfReader(pdf_path)
            for page_idx, page in enumerate(reader.pages):
                raw_text = page.extract_text() or ""
                cleaned = clean_fn(raw_text)
                if len(cleaned) < 50:
                    continue
                documents.append(Document(
                    page_content=cleaned,
                    metadata={
                        "source": filename,
                        "page": page_idx
                    }
                ))
        except Exception as e:
            logger.error(f"❌ 加载 {filename} 失败: {e}")
    logger.info(f"✅ 共加载 {len(documents)} 页医学文档")
    return documents


# ═══════════════════════════════════════════════════════════════
# 语义分块工具函数
# ═══════════════════════════════════════════════════════════════


def _cosine_similarity(a, b):
    """计算两个向量的余弦相似度"""
    a_arr = np.array(a)
    b_arr = np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)


def _split_sentences(text: str):
    """
    将文本拆分为句子列表，保留句末标点。
    分隔符包括中文标点（。！？；）、英文标点（!?）和换行（段落边界）。
    """
    sentences = []
    current = ""
    end_markers = {'。', '！', '？', '；', '!', '?', '\n'}

    for char in text:
        current += char
        if char in end_markers:
            stripped = current.strip()
            if stripped:
                sentences.append(stripped)
            current = ""

    if current.strip():
        sentences.append(current.strip())

    return sentences


def _add_sentence_overlap(chunks, sentences, breakpoints, overlap_ratio=0.25):
    """
    为语义块添加句子级重叠。

    每个块向前后各扩展 overlap_ratio 比例的句子，
    确保跨块边界的信息不会因切分而丢失。
    类似于递归切分的 chunk_overlap，但粒度是句子而非字符。
    """
    if len(chunks) <= 1 or overlap_ratio <= 0:
        return chunks

    result = []

    for i in range(len(chunks)):
        # 确定当前块在原始句子列表中的起止位置
        if i == 0:
            start_sent = 0
        else:
            start_sent = breakpoints[i - 1] + 1

        if i < len(breakpoints):
            end_sent = breakpoints[i] + 1
        else:
            end_sent = len(sentences)

        num_in_chunk = end_sent - start_sent
        overlap_count = max(1, int(num_in_chunk * overlap_ratio))

        # 向前后扩展
        extended_start = max(0, start_sent - overlap_count)
        extended_end = min(len(sentences), end_sent + overlap_count)

        extended_text = "".join(sentences[extended_start:extended_end])
        if extended_text.strip():
            result.append(extended_text.strip())

    return result


def _semantic_split(
    documents,
    embeddings_model,
    similarity_threshold=0.80,
    min_chunk_size=100,
    max_chunk_size=800,
    overlap_ratio=0.25,
):
    """
    语义分块核心算法

    流程:
        1. 将每篇文档拆分为句子列表（含换行作为段落边界）
        2. 批量计算每个句子的嵌入向量
        3. 计算相邻句子的余弦相似度，在"语义断崖"处切分
        4. 为每个语义块添加句子级重叠
        5. 后处理：合并过小块、拆分过大块

    参数:
        documents:              LangChain Document 列表
        embeddings_model:       嵌入模型实例（需实现 embed_documents 方法）
        similarity_threshold:   余弦相似度阈值，相邻句子相似度低于此值时切分
                               —— 医学文本术语密度高，建议 0.80~0.85
        min_chunk_size:         最小块大小（字符），更小的块会与相邻块合并
        max_chunk_size:         最大块大小（字符），更大的块用递归字符切分兜底
        overlap_ratio:          句子级重叠比例（默认 25%）
    """
    all_chunks = []

    for doc in documents:
        text = doc.page_content

        # 过短文本直接跳过
        if len(text) < min_chunk_size:
            continue

        # ── 第一步：拆分为句子（含 \n 段落边界）──
        sentences = _split_sentences(text)
        if len(sentences) <= 1:
            all_chunks.append(Document(
                page_content=text,
                metadata=doc.metadata.copy()
            ))
            continue

        # ── 第二步：批量计算句子嵌入向量 ──
        try:
            sentence_embeddings = embeddings_model.embed_documents(sentences)
        except Exception as e:
            logger.warning(f"⚠️ 句子嵌入计算失败 ({e})，回退到全页作为一个块")
            all_chunks.append(Document(
                page_content=text,
                metadata=doc.metadata.copy()
            ))
            continue

        # ── 第三步：计算相邻句子余弦相似度，定位"语义断崖" ──
        breakpoints = []       # 在 breakpoints[i] 和 breakpoints[i]+1 之间切分
        similarities = []      # 所有相邻相似度（用于日志）

        for i in range(len(sentences) - 1):
            sim = _cosine_similarity(
                sentence_embeddings[i],
                sentence_embeddings[i + 1]
            )
            similarities.append(sim)
            if sim < similarity_threshold:
                breakpoints.append(i)

        # 日志：相似度分布
        if similarities:
            avg_sim = sum(similarities) / len(similarities)
            min_sim = min(similarities)
            logger.debug(
                f"📊 [{doc.metadata.get('source', '?')} p.{doc.metadata.get('page', '?')}] "
                f"语义相似度: avg={avg_sim:.3f}, min={min_sim:.3f}, "
                f"断点={len(breakpoints)}/{len(similarities)}"
            )

        # ── 第四步：根据断点构建语义块（无重叠）──
        raw_chunks = []
        start = 0
        for bp in breakpoints:
            chunk_text = "".join(sentences[start:bp + 1])
            if chunk_text.strip():
                raw_chunks.append(chunk_text.strip())
            start = bp + 1

        # 最后一个块
        if start < len(sentences):
            chunk_text = "".join(sentences[start:])
            if chunk_text.strip():
                raw_chunks.append(chunk_text.strip())

        # ── 第五步：添加句子级重叠 ──
        overlapped_chunks = _add_sentence_overlap(
            raw_chunks, sentences, breakpoints, overlap_ratio
        )

        # ── 第六步：后处理（合并过小块 + 拆分过大块）──
        result_docs = _postprocess_chunks(
            overlapped_chunks, doc.metadata.copy(),
            min_chunk_size, max_chunk_size,
        )

        all_chunks.extend(result_docs)

    logger.info(
        f"✅ 语义分块完成：{len(documents)} 页 → {len(all_chunks)} 个语义块 "
        f"(阈值={similarity_threshold}, 重叠={overlap_ratio}, "
        f"块范围={min_chunk_size}~{max_chunk_size}字符)"
    )
    return all_chunks


def _postprocess_chunks(chunks, base_metadata, min_chunk_size, max_chunk_size):
    """
    块后处理：
    1. 将小于 min_chunk_size 的块合并到相邻块
    2. 将大于 max_chunk_size 的块用递归字符切分器二次拆分
    """
    if not chunks:
        return []

    # ── 第一遍：合并过小的块 ──
    merged = []
    for chunk_text in chunks:
        if len(chunk_text) < min_chunk_size and merged:
            # 合并到上一个块
            merged[-1] = merged[-1] + chunk_text
        else:
            merged.append(chunk_text)

    # ── 第二遍：拆分过大的块（递归字符切分兜底）──
    result = []
    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chunk_size,
        chunk_overlap=int(max_chunk_size * 0.25),
        separators=["\n", "。", "；", " ", ""]  # 保留换行作为首选分割符
    )

    for chunk_text in merged:
        if len(chunk_text) > max_chunk_size:
            sub_docs = fallback_splitter.split_documents([
                Document(page_content=chunk_text)
            ])
            for sd in sub_docs:
                sd.metadata.update(base_metadata)
                result.append(sd)
        else:
            result.append(Document(
                page_content=chunk_text,
                metadata=base_metadata
            ))

    return result


# ═══════════════════════════════════════════════════════════════
# 混合分块 (Hybrid Chunking) —— 默认策略
# ═══════════════════════════════════════════════════════════════
#
# 流程:
#   1. Rule-based boundary protection（规则边界保护）
#      → 在标题、列表、小节等结构边界处预切分，保证结构完整
#   2. RecursiveCharacterTextSplitter (512/128)
#      → 在每个受保护段内递归切分，控制块大小
#   3. Post-merge small chunks
#      → 合并 < min_chunk_size 的过小块到相邻块
#
# 设计原则:
#   - 递归切分是主策略（快速、可控、可复现）
#   - 规则边界保护是轻量增强（零 API 开销、确定性行为）
#   - 语义分块降级为可选 opt-in（成本高、仅首次构建有意义）

# ── 结构边界检测正则（中文医学文档常见模式）──
STRUCTURAL_BOUNDARY_PATTERNS = [
    # 章节标题
    r'^第[一二三四五六七八九十百千\d]+[章节]',
    # 中文序号标题: 一、二、三、
    r'^[一二三四五六七八九十]+[、，]',
    # 括号中文序号: （一）（二）
    r'^（[一二三四五六七八九十]+）',
    # 数字序号: 1.1 / 2.3.1
    r'^\d+\.\d+(?:\.\d+)?',
    # 纯数字序号: 1. 2、3)
    r'^\d+[\.\、\)]',
    # 方头括号标题: 【推荐意见】【证据级别】
    r'^【[^】]+】',
    # 方括号标题: [推荐意见]
    r'^\[[^\]]+\]',
    # 表/图引用: 表1 图2
    r'^[表图]\s*\d+',
    # 指南常用小节头
    r'^(推荐意见|证据级别|推荐等级|适应证|禁忌证|用法用量|不良反应|注意事项|药物相互作用|药理作用|临床研究)',
]


def _detect_boundary_positions(text: str) -> list:
    """
    扫描全文，返回所有结构边界的位置列表（字符索引）。

    对每条 STRUCTURAL_BOUNDARY_PATTERNS 进行全文扫描，
    记录匹配行的起始位置，去重排序后返回。

    参数:
        text: 待扫描的文本（需保留换行，用于行首匹配）

    返回:
        升序排列的边界位置列表（整数）
    """
    boundaries = set()
    for pattern in STRUCTURAL_BOUNDARY_PATTERNS:
        for match in re.finditer(pattern, text, re.MULTILINE):
            boundaries.add(match.start())

    # 总是在文本开头和结尾添加边界标记
    boundaries.add(0)
    boundaries.add(len(text))

    return sorted(boundaries)


def _split_at_boundaries(text: str) -> list:
    """
    在检测到的结构边界处将文本预切分为"受保护段"。

    每个受保护段以结构边界开头（标题/序号/小节头），
    保证后续递归切分不会跨越结构边界。

    参数:
        text: 待切分的文本

    返回:
        受保护段列表（字符串列表）
    """
    positions = _detect_boundary_positions(text)

    segments = []
    for i in range(len(positions) - 1):
        start = positions[i]
        end = positions[i + 1]
        segment = text[start:end].strip()
        if segment:
            segments.append(segment)

    return segments


def _merge_small_chunks(chunks: list, min_chunk_size: int, max_chunk_size: int = 800) -> list:
    """
    后处理：将过小的块合并到相邻块。

    两遍扫描：
      1. 正向扫描：当前块 < min_chunk_size 时合并到前一个块
      2. 反向兜底：若结果首个块仍 < min_chunk_size，合并到第二个块

    参数:
        chunks:        待处理的块列表（字符串）
        min_chunk_size: 最小块大小（字符），低于此值的块将被合并
        max_chunk_size: 合并后的硬上限（字符），防止合并导致块过大

    返回:
        合并后的块列表
    """
    if not chunks:
        return []

    # ── 第一遍：正向扫描 ──
    merged = []
    for chunk_text in chunks:
        if len(chunk_text) < min_chunk_size and merged:
            # 与前一个块合并，但不超过硬上限
            if len(merged[-1]) + len(chunk_text) <= max_chunk_size:
                merged[-1] = merged[-1] + chunk_text
            else:
                merged.append(chunk_text)
        else:
            merged.append(chunk_text)

    # ── 第二遍：反向兜底 —— 首个块仍过小则向后合并 ──
    if len(merged) >= 2 and len(merged[0]) < min_chunk_size:
        if len(merged[0]) + len(merged[1]) <= max_chunk_size:
            merged[1] = merged[0] + merged[1]
            merged = merged[1:]

    return merged


def _hybrid_chunking(
    documents,
    chunk_size: int = 512,
    chunk_overlap: int = 128,
    min_chunk_size: int = 100,
    max_chunk_size: int = 800,
):
    """
    混合分块主流程 (Hybrid Chunking Pipeline)

    PDF 文档
      ↓
    结构边界检测 (regex rule-based)
      ↓
    预切分为受保护段
      ↓
    递归字符切分 (RecursiveCharacterTextSplitter, 512/128)
      ↓
    后处理合并过小块 (< min_chunk_size)

    参数:
        documents:      LangChain Document 列表
        chunk_size:     递归切分的块大小（默认 512）
        chunk_overlap:  递归切分的块重叠（默认 128）
        min_chunk_size: 最小块大小（字符），低于此值后处理合并
        max_chunk_size: 合并后的硬上限（字符）
    """
    if not documents:
        return []

    all_chunks = []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", "，", " ", ""]
    )

    for doc in documents:
        text = doc.page_content

        # 过短文本直接跳过
        if len(text) < min_chunk_size:
            continue

        # ── Step 1+2: 结构边界检测 + 预切分为受保护段 ──
        segments = _split_at_boundaries(text)
        logger.debug(
            f"📐 [{doc.metadata.get('source', '?')} p.{doc.metadata.get('page', '?')}] "
            f"结构边界预切分: {len(segments)} 个受保护段"
        )

        # ── Step 3: 在每个受保护段内递归切分 ──
        raw_chunks = []
        for seg in segments:
            if len(seg) > chunk_size:
                # 段内文本过长，递归切分
                sub_docs = splitter.split_documents([
                    Document(page_content=seg)
                ])
                for sd in sub_docs:
                    if sd.page_content.strip():
                        raw_chunks.append(sd.page_content.strip())
            else:
                # 段内文本较小，保持完整
                if seg.strip():
                    raw_chunks.append(seg.strip())

        # ── Step 4: 后处理合并过小块 ──
        merged = _merge_small_chunks(raw_chunks, min_chunk_size, max_chunk_size)

        for chunk_text in merged:
            all_chunks.append(Document(
                page_content=chunk_text,
                metadata=doc.metadata.copy()
            ))

    logger.info(
        f"✅ 混合分块完成: {len(documents)} 页 → {len(all_chunks)} 个块 "
        f"(chunk_size={chunk_size}/{chunk_overlap}, "
        f"后处理合并阈值={min_chunk_size}字符)"
    )
    return all_chunks


# ═══════════════════════════════════════════════════════════════
# 统一的文档切分入口
# ═══════════════════════════════════════════════════════════════


def split_documents(
    documents,
    embeddings=None,
    similarity_threshold=0.80,
    min_chunk_size=100,
    max_chunk_size=800,
    overlap_ratio=0.25,
    strategy="hybrid",
):
    """
    文档切分入口

    策略选择:
        - strategy="hybrid" (默认): 混合分块
            1. Rule-based 结构边界保护（标题/序号/小节头）
            2. RecursiveCharacterTextSplitter (512/128) 递归切分
            3. 后处理合并 < min_chunk_size 的过小块
            → 推荐！快速、确定性、零 API 开销

        - strategy="semantic": 语义分块（需提供 embeddings）
            1. 拆分为句子 + 批量计算嵌入向量
            2. 在余弦相似度"断崖"处切分
            3. 句子级重叠 + 后处理
            → 首次构建向量库时可选，成本高但块内语义一致

    参数:
        documents:            待切分的 Document 列表
        embeddings:           嵌入模型实例 — strategy="semantic" 时必须提供
        similarity_threshold: 语义切分的余弦相似度阈值（默认 0.80）
        min_chunk_size:       最小块大小（字符），两种策略均生效
        max_chunk_size:       最大块大小（字符）
        overlap_ratio:        语义切分的句子级重叠比例（默认 0.25）
        strategy:             切分策略: "hybrid" / "semantic"
    """
    if not documents:
        return []

    if strategy == "semantic":
        if embeddings is None:
            logger.warning(
                "⚠️ strategy='semantic' 但未提供 embeddings，"
                "回退到 hybrid 策略"
            )
            return _hybrid_chunking(
                documents,
                chunk_size=512,
                chunk_overlap=128,
                min_chunk_size=min_chunk_size,
                max_chunk_size=max_chunk_size,
            )

        logger.info(
            f"🧠 使用语义分块 "
            f"(阈值={similarity_threshold}, 重叠={overlap_ratio}, "
            f"{min_chunk_size}~{max_chunk_size}字符)"
        )
        return _semantic_split(
            documents, embeddings,
            similarity_threshold, min_chunk_size, max_chunk_size,
            overlap_ratio=overlap_ratio,
        )

    # 默认: 混合分块
    logger.info(
        f"🔀 使用混合分块 (Hybrid Chunking): "
        f"规则边界保护 → 递归切分(512/128) → 合并<{min_chunk_size}字符"
    )
    return _hybrid_chunking(
        documents,
        chunk_size=512,
        chunk_overlap=128,
        min_chunk_size=min_chunk_size,
        max_chunk_size=max_chunk_size,
    )
