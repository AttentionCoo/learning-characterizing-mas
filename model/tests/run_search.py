from app.rag.data_loader import load_pdfs_from_dir, split_documents
from app.rag.retrievers import build_or_load_vectorstore, HybridRetriever


def main():
    docs_dir = r"/data\documents"

    docs = load_pdfs_from_dir(docs_dir)

    chunks = split_documents(docs)
    print(f"✂️ 切分得到 {len(chunks)} 个 chunk")

    vectordb = build_or_load_vectorstore(chunks)

    retriever = HybridRetriever(vectordb, chunks, recall_k=5, rrf_top_k=5)

    query = "脑梗死出血转化的处理原则是什么？"
    results = retriever.search(query, top_k_final=3)

    for i, doc in enumerate(results, 1):
        print(f"\n[{i}] ({doc.metadata['source']} - p{doc.metadata['page']})")
        print(doc.page_content[:300])


if __name__ == "__main__":
    main()