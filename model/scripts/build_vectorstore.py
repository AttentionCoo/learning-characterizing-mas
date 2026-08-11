#!/usr/bin/env python
"""Build / rebuild the Multi-Collection ChromaDB vector store from local PDF documents.

构建 5 个主题隔离 collection（anatomy/guideline/etiology/treatment/prevention）：
1. 加载 PDF → 混合分块
2. 每个 chunk 打结构化标签（subtopic/collection/intervention/decision_node/year/authority）
3. 按 collection 物理分库写入
"""
import sys
import os
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.rag.retrievers import MultiCollectionSearchEngine, CONFIG as RETRIEVER_CONFIG


def main():
    persist_dir = RETRIEVER_CONFIG['multi_persist_dir']
    docs_dir = os.getenv('MEDICAL_DOCS_DIR') or RETRIEVER_CONFIG.get('docs_dir', './data/documents')

    print(f'persist_dir: {persist_dir}')
    print(f'docs_dir:    {docs_dir}')

    # 1. Delete old multi-collection vector store
    if os.path.exists(persist_dir):
        print(f'Deleting old vector store: {persist_dir}')
        shutil.rmtree(persist_dir)
        print('Deleted.')

    # 2. Rebuild（多库）
    print('Building multi-collection vector store from scratch...')
    engine = MultiCollectionSearchEngine(
        persist_dir=persist_dir,
        top_k=RETRIEVER_CONFIG.get('top_k_final', 3),
        docs_dir=docs_dir,
    )
    print(f'Done. chunks={len(engine.chunks)}')
    for collection, count in engine.get_collection_stats().items():
        print(f'  - collection[{collection}]: {count} chunks')


if __name__ == '__main__':
    main()
