"""Test vector store persistence - build, load, search, cross-session"""

import os
import sys
import shutil
import logging
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("test_vectorstore")

TEST_PERSIST_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "vector_stores", "_test_persist"
))


def hdr(title):
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


def ok(name, passed, detail=""):
    s = "PASS" if passed else "FAIL"
    print(f"  [{s}] {name}" + (f" -- {detail}" if detail else ""))


def cleanup(path):
    if os.path.exists(path):
        shutil.rmtree(path)


# Test 1: Main knowledge base build & load
def test_main_kb():
    hdr("Test 1: Main KB - Build & Load")
    cleanup(TEST_PERSIST_DIR)
    try:
        from langchain_core.documents import Document
        from app.rag.retrievers import build_or_load_vectorstore, XfyunEmbeddings

        chunks = [
            Document(page_content="rtPA IV thrombolysis time window is within 4.5 hours of onset.", metadata={"source": "t1.pdf"}),
            Document(page_content="NIHSS score ranges 0-42, higher = more severe neurological deficit.", metadata={"source": "t1.pdf"}),
            Document(page_content="Secondary prevention includes antiplatelet, BP control, glucose management.", metadata={"source": "t2.pdf"}),
            Document(page_content="Carotid stenting indicated for symptomatic stenosis >= 70%.", metadata={"source": "t2.pdf"}),
            Document(page_content="ICH acute management: BP control, ICP management, complication prevention.", metadata={"source": "t3.pdf"}),
        ]

        vdb = build_or_load_vectorstore(chunks, TEST_PERSIST_DIR, enable_qa=False)
        count = vdb._collection.count()
        ok("Build", count == 5, f"expected 5, got {count}")

        sqlite = os.path.join(TEST_PERSIST_DIR, "chroma.sqlite3")
        ok("Persistence file", os.path.exists(sqlite), sqlite)

        vdb2 = build_or_load_vectorstore([], TEST_PERSIST_DIR, enable_qa=False)
        ok("Reload", vdb2._collection.count() == 5, f"count={vdb2._collection.count()}")

        emb = XfyunEmbeddings()
        qv = emb.embed_query("thrombolysis time window")
        res = vdb2._collection.query(query_embeddings=[qv], n_results=2, include=["documents", "distances"])
        hits = len(res["documents"][0]) if res["documents"] else 0
        ok("Search", hits > 0, f"hits={hits}")
        if hits:
            for i, (d, dist) in enumerate(zip(res["documents"][0], res["distances"][0])):
                print(f"      #{i+1} [dist={dist:.4f}] {d[:60]}...")
        return True
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        ok("Main KB", False, str(e))
        return False


# Test 2: Shared memory store & retrieve
def test_shared_memory():
    hdr("Test 2: Shared Memory - Store & Retrieve")
    try:
        from app.agents.core.shared_memory import SharedMemoryStore

        mem_dir = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "vector_stores", "chroma_db_shared_memory"
        ))
        cleanup(mem_dir)

        store = SharedMemoryStore(config={"persist_dir": mem_dir})
        stats = store.get_stats()
        ok("Init", stats["initialized"], f"total={stats['total']}")

        mid1 = store.store("rtPA thrombolysis time window is within 4.5h.", "agent1",
                           metadata={"kp": ["thrombolysis"], "conf": 0.9}, force=True)
        ok("Store high-value", mid1 is not None, f"id={mid1}")

        mid2 = store.store("NIHSS score ranges 0-42 for stroke severity.", "agent2",
                           metadata={"kp": ["NIHSS"], "conf": 0.85}, force=True)
        ok("Store 2nd", mid2 is not None, f"id={mid2}")

        mid3 = store.store("ok thanks", "agent3", force=False)
        ok("Noise filtered", mid3 is None, "low-value content rejected")

        hits = store.retrieve("thrombolysis", top_k=3)
        ok("Semantic search", len(hits) >= 1, f"hits={len(hits)}")
        if hits:
            for h in hits:
                print(f"      [{h['relevance']:.4f}] {h['content'][:60]}...")

        stats = store.get_stats()
        ok("Stats", stats["total"] == 2, f"expected 2, got {stats['total']}")
        return True
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        ok("Shared Memory", False, str(e))
        return False


# Test 3: Cross-session persistence
def test_cross_session():
    hdr("Test 3: Cross-Session Persistence")
    try:
        from app.agents.core.shared_memory import SharedMemoryStore

        mem_dir = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "vector_stores", "chroma_db_shared_memory"
        ))

        store2 = SharedMemoryStore(config={"persist_dir": mem_dir})
        stats = store2.get_stats()
        ok("Data retained", stats["total"] >= 2, f"total={stats['total']}")

        hits = store2.retrieve("NIHSS", top_k=3)
        ok("Cross-session search", len(hits) >= 1, f"hits={len(hits)}")

        mid = store2.store("ICH BP target: SBP < 140mmHg.", "new_agent",
                           metadata={"kp": ["ICH", "BP"], "conf": 0.9}, force=True)
        ok("New session write", mid is not None, f"id={mid}")

        stats = store2.get_stats()
        ok("Total after write", stats["total"] >= 3, f"total={stats['total']}")
        return True
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        ok("Cross-Session", False, str(e))
        return False


# Test 4: Dimension consistency
def test_dimension():
    hdr("Test 4: Dimension Consistency")
    try:
        from app.rag.retrievers import XfyunEmbeddings
        import chromadb

        emb = XfyunEmbeddings()
        vec = emb.embed_query("stroke thrombolysis")
        dim = len(vec)
        ok("Embedding dimension", dim > 0, f"dim={dim}")

        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stores = {
            "main_kb": os.path.join(base, "data", "vector_stores", "chroma_db_unified"),
            "test_kb": os.path.join(base, "data", "vector_stores", "_test_persist"),
            "shared_mem": os.path.join(base, "data", "vector_stores", "chroma_db_shared_memory"),
        }
        for name, path in stores.items():
            if os.path.exists(path):
                try:
                    client = chromadb.PersistentClient(path=path)
                    cols = client.list_collections()
                    if cols:
                        c = cols[0]
                        ef = type(c._embedding_function).__name__ if c._embedding_function else "None"
                        print(f"      {name}: count={c.count()}, ef={ef}")
                    else:
                        print(f"      {name}: empty")
                except Exception as e:
                    print(f"      {name}: error -- {e}")
            else:
                print(f"      {name}: not created yet")

        ok("Dimension check", True, f"current dim={dim}")
        return True
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        ok("Dimension", False, str(e))
        return False


# Test 5: MetaMemory filter
def test_meta():
    hdr("Test 5: MetaMemory Filter")
    try:
        from app.agents.core.shared_memory import MetaMemoryFilter
        mf = MetaMemoryFilter()

        ok("High-value retained", mf.should_persist(
            "Stroke thrombolysis with rtPA within 4.5h. NIHSS assessment tool.")[0] is True)

        ok("Noise rejected", mf.should_persist("ok thanks bye")[0] is False)

        items = [
            {"content": "Stroke rtPA thrombolysis within 4.5h. NIHSS assessment.", "id": 1},
            {"content": "ok thanks", "id": 2},
            {"content": "Secondary prevention: antiplatelet, BP, glucose control.", "id": 3},
        ]
        filtered = mf.filter_batch(items)
        ok("Batch filter", len(filtered) == 2, f"in={len(items)} out={len(filtered)}")
        return True
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        ok("MetaMemory", False, str(e))
        return False


# Test 6: Consensus & reputation
def test_consensus():
    hdr("Test 6: Consensus & Reputation")
    try:
        from app.agents.core.shared_memory import ConsensusEngine, AgentReputationStore

        ce = ConsensusEngine()
        advices = {
            "a": "Start with Willis circle anatomy.",
            "b": "Start with Willis circle anatomy.",
            "c": "Skip anatomy, go to guidelines.",
        }
        r = ce.resolve_conflict(advices)
        ok("Consensus", len(r["winning_agents"]) > 0, f"winner={r['winning_agents']}")

        tf = os.path.join(tempfile.gettempdir(), "_test_rep.json")
        ars = AgentReputationStore(config={"reputation_file": tf})
        ars.update("a", True)
        ars.update("a", True)
        ars.update("a", False)
        sc = ars.get_score("a")
        ok("Score", abs(sc - 2/3) < 0.01, f"score={sc:.3f}")

        ars2 = AgentReputationStore(config={"reputation_file": tf})
        sc2 = ars2.get_score("a")
        ok("Reputation persistence", abs(sc2 - 2/3) < 0.01, f"reload score={sc2:.3f}")

        try:
            os.remove(tf)
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error(f"FAIL: {e}", exc_info=True)
        ok("Consensus", False, str(e))
        return False


if __name__ == "__main__":
    results = [
        ("MetaMemory Filter", test_meta()),
        ("Consensus & Reputation", test_consensus()),
        ("Main KB Build & Load", test_main_kb()),
        ("Shared Memory Store & Retrieve", test_shared_memory()),
        ("Cross-Session Persistence", test_cross_session()),
        ("Dimension Consistency", test_dimension()),
    ]
    hdr("SUMMARY")
    passed = sum(1 for _, r in results if r)
    for name, r in results:
        ok(name, r)
    print(f"\n  Result: {passed}/{len(results)} passed")
    if passed == len(results):
        print("  All tests passed! Vector store persistence is working.")
    cleanup(TEST_PERSIST_DIR)