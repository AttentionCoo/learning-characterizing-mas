#!/usr/bin/env python
"""Build / rebuild the ChromaDB vector store from local PDF documents."""
import sys
import os
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.rag.retrievers import UnifiedSearchEngine, CONFIG as RETRIEVER_CONFIG


def main():
    persist_dir = RETRIEVER_CONFIG['persist_dir']
    docs_dir = os.getenv('MEDICAL_DOCS_DIR') or RETRIEVER_CONFIG.get('docs_dir', './data/documents')

    print(f'persist_dir: {persist_dir}')
    print(f'docs_dir:    {docs_dir}')

    # 1. Delete old vector store
    if os.path.exists(persist_dir):
        print(f'Deleting old vector store: {persist_dir}')
        shutil.rmtree(persist_dir)
        print('Deleted.')

    # 2. Rebuild
    print('Building vector store from scratch...')
    engine = UnifiedSearchEngine(
        persist_dir=persist_dir,
        top_k=RETRIEVER_CONFIG.get('top_k_final', 3),
        docs_dir=docs_dir,
    )
    print(f'Done. chunks={len(engine.chunks)}, vectorstore={persist_dir}')


if __name__ == '__main__':
    main()
