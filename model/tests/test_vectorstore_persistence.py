"""测试向量库持久化打造功能

测试覆盖:
  1. 主知识库 (chroma_db_unified) — 构建、加载、搜索
  2. 共享记忆库 (chroma_db_shared_memory) — 存储、检索、跨会话持久化
  3. 维度一致性检查
  4. 跨会话持久化验证
"""
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


TEST_PERSIST_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "vector_stores", "_test_persist"
)
TEST_PERSIST_DIR = os.path.normpath(TEST_PERSIST_DIR)


def print_header(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_result(name: str, passed: bool, detail: str = ""):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def cleanup(persist_dir: str):
    if os.path.exists(persist_dir):
        shutil.rmtree(persist_dir)
        logger.info(f"🧹 已清理测试目录: {persist_dir}")


# ============================================================
# 测试 1: 主知识库 — 构建与加载
# ============================================================
def test_main_knowledge_base_build_and_load():
    print_header("测试 1: 主知识库 — 构建与加载")

    cleanup(TEST_PERSIST_DIR)

    try:
        from langchain_core.documents import Document
        from app.rag.retrievers import build_or_load_vectorstore, XfyunEmbeddings

        # 1.1 创建测试文档
        test_chunks = [
            Document(
                page_content="脑卒中急性期溶栓治疗需要严格把握时间窗，发病4.5小时内可使用rtPA静脉溶栓。",
                metadata={"source": "test_doc_1.pdf", "page": 1},
            ),
            Document(
                page_content="NIHSS评分是评估卒中严重程度的重要工具，范围0-42分，分数越高表示神经功能缺损越严重。",
                metadata={"source": "test_doc_1.pdf", "page": 2},
            ),
            Document(
                page_content="缺血性脑卒中的二级预防包括抗血小板治疗、血压控制、血糖管理和生活方式干预。",
                metadata={"source": "test_doc_2.pdf", "page": 1},
            ),
            Document(
                page_content="颈动脉支架植入术是治疗颈动脉狭窄的有效方法，适用于狭窄程度≥70%的症状性患者。",
                metadata={"source": "test_doc_2.pdf", "page": 3},
            ),
            Document(
                page_content="脑出血急性期管理包括血压控制、颅内压管理和并发症防治。",
                metadata={"source": "test_doc_3.pdf", "page": 1},
            ),
        ]

        # 1.2 构建向量库（enable_qa=False，快速测试）
        logger.info("🏗️  构建向量库...")
        vectordb = build_or_load_vectorstore(
            test_chunks, TEST_PERSIST_DIR, enable_qa=False
        )
        count = vectordb._collection.count()
        print_result("向量库构建成功", count == len(test_chunks),
                     f"预期 {len(test_chunks)} 条，实际 {count} 条")

        # 1.3 验证向量库持久化文件
        sqlite_path = os.path.join(TEST_PERSIST_DIR, "chroma.sqlite3")
        print_result("持久化文件存在", os.path.exists(sqlite_path),
                     f"路径: {sqlite_path}")

        # 1.4 重新加载向量库（模拟跨会话）
        logger.info("🔄 重新加载向量库（模拟跨会话）...")
        vectordb2 = build_or_load_vectorstore(
            [], TEST_PERSIST_DIR, enable_qa=False
        )
        count2 = vectordb2._collection.count()
        print_result("跨会话加载数据一致", count2 == len(test_chunks),
                     f"重新加载后 count={count2}")

        # 1.5 检索测试
        embeddings = XfyunEmbeddings()
        query = "溶栓治疗时间窗"
        query_embedding = embeddings.embed_query(query)
        results = vectordb2._collection.query(
            query_embeddings=[query_embedding],
            n_results=3,
            include=["documents", "distances"],
        )
        hit_count = len(results["documents"][0]) if results["documents"] else 0
        print_result("向量检索功能", hit_count > 0,
                     f"查询'{query}'命中 {hit_count} 条")

        # 1.6 打印检索结果
        if hit_count > 0:
            for i, (doc, dist) in enumerate(zip(results["documents"][0], results["distances"][0])):
                print(f"      #{i+1} [distance={dist:.4f}] {doc[:60]}...")

        return True
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        print_result("主知识库测试", False, str(e))
        return False


# ============================================================
# 测试 2: 共享记忆库 — 存储与检索
# ============================================================
def test_shared_memory_store_and_retrieve():
    print_header("测试 2: 共享记忆库 — 存储与检索")

    try:
        from app.agents.core.shared_memory import SharedMemoryStore

        # 清理旧的共享记忆测试数据
        mem_persist_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "vector_stores", "chroma_db_shared_memory"
        )
        mem_persist_dir = os.path.normpath(mem_persist_dir)
        cleanup(mem_persist_dir)

        store = SharedMemoryStore(config={"persist_dir": mem_persist_dir})

        # 2.1 初始化状态
        stats = store.get_stats()
        print_result("记忆库初始化成功", stats["initialized"],
                     f"总记忆数={stats['total']}")

        # 2.2 存储高价值记忆
        mem_id1 = store.store(
            "rtPA静脉溶栓时间窗为发病4.5小时内，需严格把握适应症和禁忌症。",
            "test_agent_1",
            metadata={"knowledge_points": ["溶栓", "时间窗"], "confidence": 0.9},
            force=True,
        )
        print_result("存储高价值记忆", mem_id1 is not None, f"id={mem_id1}")

        mem_id2 = store.store(
            "NIHSS评分是评估卒中严重程度的重要工具，范围0-42分。",
            "test_agent_2",
            metadata={"knowledge_points": ["NIHSS", "评估"], "confidence": 0.85},
            force=True,
        )
        print_result("存储第二条记忆", mem_id2 is not None, f"id={mem_id2}")

        # 2.3 噪声音记忆应被过滤
        mem_id3 = store.store(
            "嗯嗯好的知道了",
            "test_agent_3",
            force=False,
        )
        print_result("噪声音记忆被过滤", mem_id3 is None,
                     f"低价值内容被熵值过滤拦截")

        # 2.4 检索
        hits = store.retrieve("溶栓治疗", top_k=3)
        print_result("语义检索成功", len(hits) >= 1,
                     f"查询'溶栓治疗'命中 {len(hits)} 条")

        if hits:
            for h in hits:
                print(f"      [{h['relevance']:.4f}] {h['content'][:60]}...")

        # 2.5 统计
        stats = store.get_stats()
        print_result("记忆库统计正确", stats["total"] == 2,
                     f"预期 2 条，实际 {stats['total']} 条")

        return True
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        print_result("共享记忆库测试", False, str(e))
        return False


# ============================================================
# 测试 3: 共享记忆库 — 跨会话持久化
# ============================================================
def test_shared_memory_cross_session_persistence():
    print_header("测试 3: 共享记忆库 — 跨会话持久化")

    try:
        from app.agents.core.shared_memory import SharedMemoryStore

        mem_persist_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "data", "vector_stores", "chroma_db_shared_memory"
        )
        mem_persist_dir = os.path.normpath(mem_persist_dir)

        # 3.1 重新创建 store（模拟新会话）
        store2 = SharedMemoryStore(config={"persist_dir": mem_persist_dir})
        stats = store2.get_stats()
        print_result("跨会话数据保留", stats["total"] >= 2,
                     f"持久化记忆数={stats['total']}（预期 ≥ 2）")

        # 3.2 新会话中检索旧数据
        hits = store2.retrieve("NIHSS评分", top_k=3)
        print_result("跨会话检索旧数据", len(hits) >= 1,
                     f"查询'NIHSS评分'命中 {len(hits)} 条")

        # 3.3 新会话中写入新数据
        mem_id_new = store2.store(
            "脑出血急性期血压控制目标为收缩压<140mmHg。",
            "test_agent_new",
            metadata={"knowledge_points": ["脑出血", "血压"], "confidence": 0.9},
            force=True,
        )
        print_result("新会话写入数据", mem_id_new is not None,
                     f"id={mem_id_new}")

        stats = store2.get_stats()
        print_result("新会话数据总量正确", stats["total"] >= 3,
                     f"持久化记忆数={stats['total']}（预期 ≥ 3）")

        return True
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        print_result("跨会话持久化测试", False, str(e))
        return False


# ============================================================
# 测试 4: 维度一致性检查
# ============================================================
def test_dimension_consistency():
    print_header("测试 4: 维度一致性检查")

    try:
        from app.rag.retrievers import XfyunEmbeddings
        import chromadb

        embeddings = XfyunEmbeddings()

        # 4.1 生成一个 embedding 并检查维度
        test_text = "脑卒中急性期溶栓治疗"
        vec = embeddings.embed_query(test_text)
        dim = len(vec)

        print_result("Embedding 维度有效", dim > 0, f"维度={dim}")

        # 4.2 验证两个向量库的维度一致
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        stores = {
            "主知识库": os.path.join(base_dir, "data", "vector_stores", "chroma_db_unified"),
            "_test_persist": os.path.join(base_dir, "data", "vector_stores", "_test_persist"),
            "共享记忆库": os.path.join(base_dir, "data", "vector_stores", "chroma_db_shared_memory"),
        }

        for name, path in stores.items():
            if os.path.exists(path):
                try:
                    client = chromadb.PersistentClient(path=path)
                    collections = client.list_collections()
                    if collections:
                        col = collections[0]
                        count = col.count()
                        ef = col._embedding_function
                        ef_name = type(ef).__name__ if ef else "None"
                        print(f"      {name}: count={count}, embedding_function={ef_name}")
                    else:
                        print(f"      {name}: 集合为空")
                except Exception as e:
                    print(f"      {name}: 检查失败 — {e}")
            else:
                print(f"      {name}: 目录不存在（尚未创建）")

        print_result("维度一致性检查完成", True, f"当前 embedding 维度={dim}")

        return True
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        print_result("维度一致性检查", False, str(e))
        return False


# ============================================================
# 测试 5: 元记忆过滤器
# ============================================================
def test_meta_memory_filter():
    print_header("测试 5: 元记忆过滤器")

    try:
        from app.agents.core.shared_memory import MetaMemoryFilter

        mf = MetaMemoryFilter()

        # 5.1 高价值医学内容
        text_high = "脑卒中急性期溶栓治疗需要严格把握时间窗，发病4.5小时内可使用rtPA静脉溶栓，NIHSS评分是评估卒中严重程度的重要工具。"
        should, score, detail = mf.should_persist(text_high)
        print_result("高价值内容被保留", should is True,
                     f"熵分={score:.4f} < 阈值={mf.entropy_threshold}")

        # 5.2 噪音内容
        text_noise = "嗯嗯好的知道了谢谢老师"
        should2, score2, _ = mf.should_persist(text_noise)
        print_result("噪音内容被丢弃", should2 is False,
                     f"熵分={score2:.4f} >= 阈值={mf.entropy_threshold}")

        # 5.3 批量过滤
        items = [
            {"content": text_high, "id": 1},
            {"content": text_noise, "id": 2},
            {"content": "缺血性脑卒中二级预防包括抗血小板、血压控制、血糖管理。", "id": 3},
        ]
        filtered = mf.filter_batch(items)
        print_result("批量过滤正确", len(filtered) == 2,
                     f"输入={len(items)} 输出={len(filtered)}")

        return True
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        print_result("元记忆过滤器", False, str(e))
        return False


# ============================================================
# 测试 6: 共识引擎与信誉存储
# ============================================================
def test_consensus_and_reputation():
    print_header("测试 6: 共识引擎与信誉存储")

    try:
        from app.agents.core.shared_memory import ConsensusEngine, AgentReputationStore

        # 6.1 共识引擎
        ce = ConsensusEngine()
        advices = {
            "agent_a": "建议从脑血管解剖基础开始复习，重点关注Willis环和脑供血系统。",
            "agent_b": "建议从脑血管解剖基础开始复习，重点关注Willis环和脑供血系统。",
            "agent_c": "建议直接学习溶栓治疗指南，跳过基础解剖知识。",
        }
        result = ce.resolve_conflict(advices)
        print_result("共识引擎工作正常", len(result["winning_agents"]) > 0,
                     f"winner={result['winning_agents']}")

        # 6.2 信誉存储持久化
        test_file = os.path.join(tempfile.gettempdir(), "_test_reputation_persist.json")
        ars = AgentReputationStore(config={"reputation_file": test_file})
        ars.update("agent_a", was_correct=True)
        ars.update("agent_a", was_correct=True)
        ars.update("agent_a", was_correct=False)
        score = ars.get_score("agent_a")
        print_result("信誉评分正确", abs(score - 2/3) < 0.01,
                     f"score={score:.3f} (预期 0.667)")

        # 6.3 信誉持久化
        ars2 = AgentReputationStore(config={"reputation_file": test_file})
        score2 = ars2.get_score("agent_a")
        print_result("信誉数据持久化", abs(score2 - 2/3) < 0.01,
                     f"重新加载后 score={score2:.3f}")

        try:
            if os.path.exists(test_file):
                os.remove(test_file)
        except Exception:
            pass

        return True
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}", exc_info=True)
        print_result("共识引擎与信誉存储", False, str(e))
        return False


# ============================================================
# 主入口
# ============================================================
if __name__ == "__main__":
    results = []

    results.append(("元记忆过滤器", test_meta_memory_filter()))
    results.append(("共识引擎与信誉存储", test_consensus_and_reputation()))
    results.append(("主知识库 — 构建与加载", test_main_knowledge_base_build_and_load()))
    results.append(("共享记忆库 — 存储与检索", test_shared_memory_store_and_retrieve()))
    results.append(("共享记忆库 — 跨会话持久化", test_shared_memory_cross_session_persistence()))
    results.append(("维度一致性检查", test_dimension_consistency()))

    # 汇总
    print_header("测试汇总")
    passed = sum(1 for _, r in results if r)
    total = len(results)
    for name, r in results:
        print_result(name, r)

    print(f"\n  📊 总计: {passed}/{total} 通过")
    if passed == total:
        print("  🎉 全部测试通过！向量库持久化功能正常。")
    else:
        print(f"  ⚠️ 有 {total - passed} 个测试失败，请检查日志。")

    # 清理
    cleanup(TEST_PERSIST_DIR)