"""共享记忆系统 — 物理层 + 逻辑层 + 元记忆过滤

架构分层:
  物理层 (SharedMemoryStore): 基于 ChromaDB 的持久化共享记忆存储
  逻辑层 (ConsensusEngine):  信任加权投票共识，解决 Agent 间记忆冲突
  元记忆过滤 (MetaMemoryFilter): 基于信息熵的高价值信息筛选
"""
import json
import math
import os
import time
import logging
import threading
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 元记忆过滤 — 基于信息熵的高价值信息筛选
# ============================================================

class MetaMemoryFilter:
    """元记忆过滤器：计算信息熵值，低熵（高价值、强关联）信息持久化，高熵噪音丢弃"""

    DOMAIN_KEYWORDS = [
        "脑卒中", "中风", "卒中", "脑梗", "脑梗死", "脑出血",
        "缺血性", "出血性", "溶栓", "取栓", "抗血小板", "抗凝",
        "NIHSS", "mRS", "ASPECTS", "rtPA", "阿替普酶",
        "康复", "二级预防", "颈动脉", "支架", "脑水肿",
        "学习", "复习", "知识点", "掌握", "薄弱", "评估",
        "画像", "认知风格", "学习目标", "易错点", "资源偏好",
        "个性化", "难度", "练习", "辅导", "路径",
    ]

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.entropy_threshold = cfg.get("entropy_threshold", 0.85)
        self.keyword_weight = cfg.get("keyword_weight", 0.3)
        self.density_weight = cfg.get("density_weight", 0.3)
        self.shannon_weight = cfg.get("shannon_weight", 0.2)
        self.length_weight = cfg.get("length_weight", 0.2)
        self.min_length = cfg.get("min_length", 20)
        logger.info(
            f"[meta_filter] 初始化 | 熵阈值={self.entropy_threshold} "
            f"关键词权重={self.keyword_weight} 密度权重={self.density_weight} "
            f"香农权重={self.shannon_weight} 长度权重={self.length_weight}"
        )

    def compute_shannon_entropy(self, text: str) -> float:
        """计算字符级香农熵，熵越高表示字符分布越均匀（信息越分散）"""
        if not text:
            return 0.0
        freq = Counter(text)
        total = len(text)
        entropy = 0.0
        for count in freq.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        max_entropy = math.log2(len(freq)) if len(freq) > 1 else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def compute_keyword_density(self, text: str) -> float:
        """计算领域关键词密度，密度越高表示信息越聚焦"""
        if not text:
            return 0.0
        text_lower = text.lower()
        hit_count = sum(1 for kw in self.DOMAIN_KEYWORDS if kw.lower() in text_lower)
        max_possible = min(len(self.DOMAIN_KEYWORDS), len(text) // 2)
        if max_possible == 0:
            return 0.0
        return min(hit_count / max_possible, 1.0)

    def compute_token_density(self, text: str) -> float:
        """计算 token 信息密度（唯一 token 占比），越高表示信息越浓缩

        对极短文本施加惩罚：token 数越少，密度上限越低
        """
        if not text:
            return 0.0
        tokens = text.split()
        if not tokens:
            return 0.0
        unique_ratio = len(set(tokens)) / len(tokens)
        token_count = len(tokens)
        if token_count < 5:
            short_penalty = token_count / 5.0
            unique_ratio *= short_penalty
        return unique_ratio

    def compute_length_score(self, text: str) -> float:
        """计算长度得分，过短的信息价值低，适中长度得分高"""
        if not text:
            return 0.0
        length = len(text)
        if length < self.min_length:
            return length / self.min_length * 0.3
        if length < 200:
            return 0.7 + 0.3 * (length - self.min_length) / (200 - self.min_length)
        if length < 2000:
            return 1.0
        return max(0.5, 1.0 - (length - 2000) / 10000)

    def compute_entropy_score(self, text: str) -> Tuple[float, Dict[str, float]]:
        """综合计算信息熵评分

        返回:
            (综合熵分, 各维度明细)
            熵分越低 → 信息越有价值 → 越应该持久化
            熵分越高 → 噪音越大 → 应该丢弃
        """
        if not text or not text.strip():
            return 1.0, {"shannon": 1.0, "keyword": 0.0, "density": 0.0, "length": 0.0}

        shannon = self.compute_shannon_entropy(text)
        keyword_density = self.compute_keyword_density(text)
        token_density = self.compute_token_density(text)
        length_score = self.compute_length_score(text)

        keyword_signal = 1.0 - keyword_density
        density_signal = 1.0 - token_density
        length_signal = 1.0 - length_score

        entropy_score = (
            self.shannon_weight * shannon
            + self.keyword_weight * keyword_signal
            + self.density_weight * density_signal
            + self.length_weight * length_signal
        )

        details = {
            "shannon": round(shannon, 4),
            "keyword": round(keyword_density, 4),
            "density": round(token_density, 4),
            "length": round(length_score, 4),
        }

        return round(entropy_score, 4), details

    def should_persist(self, text: str) -> Tuple[bool, float, Dict[str, float]]:
        """判断信息是否应该持久化

        返回:
            (是否持久化, 熵分, 明细)
        """
        entropy_score, details = self.compute_entropy_score(text)
        should = entropy_score < self.entropy_threshold
        if should:
            logger.info(f"[meta_filter] ✅ 持久化 | 熵分={entropy_score:.4f} < 阈值={self.entropy_threshold}")
        else:
            logger.debug(f"[meta_filter] ❌ 丢弃 | 熵分={entropy_score:.4f} >= 阈值={self.entropy_threshold}")
        return should, entropy_score, details

    def filter_batch(self, items: List[Dict], text_key: str = "content") -> List[Dict]:
        """批量过滤，只保留低熵（高价值）条目"""
        results = []
        for item in items:
            text = item.get(text_key, "")
            should, score, details = self.should_persist(text)
            if should:
                item_copy = dict(item)
                item_copy["entropy_score"] = score
                item_copy["entropy_details"] = details
                results.append(item_copy)
        logger.info(f"[meta_filter] 批量过滤 | 输入={len(items)} 输出={len(results)}")
        return results


# ============================================================
# 物理层 — 共享记忆存储
# ============================================================

class SharedMemoryStore:
    """基于 ChromaDB 的共享记忆存储，负责持久化高价值学习洞察"""

    COLLECTION_NAME = "shared_learning_memory"

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.persist_dir = cfg.get(
            "persist_dir",
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "chroma_db_shared_memory")
        )
        self.meta_filter = MetaMemoryFilter(cfg.get("meta_filter", {}))
        self._collection = None
        self._embeddings = None
        self._initialized = False
        logger.info(f"[shared_memory] 初始化 | 持久化目录={self.persist_dir}")

    def _ensure_initialized(self):
        if self._initialized:
            return
        try:
            from app.rag.retrievers import DashScopeEmbeddings
            import chromadb

            self._embeddings = DashScopeEmbeddings(model="text-embedding-v2")

            client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"}
            )
            self._initialized = True
            count = self._collection.count()
            logger.info(f"[shared_memory] ✅ 初始化完成 | 已有 {count} 条共享记忆")
        except Exception as e:
            logger.error(f"[shared_memory] ❌ 初始化失败: {e}")
            self._initialized = False

    def store(
        self,
        content: str,
        source_agent: str,
        metadata: Optional[Dict] = None,
        force: bool = False,
    ) -> Optional[str]:
        """存储一条高价值共享记忆

        Args:
            content: 记忆内容
            source_agent: 来源智能体
            metadata: 附加元数据
            force: 是否跳过熵值过滤（强制存储）

        Returns:
            记忆ID（如果存储成功），否则 None
        """
        self._ensure_initialized()
        if not self._initialized:
            logger.warning("[shared_memory] 未初始化，跳过存储")
            return None

        if not content or not content.strip():
            return None

        if not force:
            should, entropy_score, details = self.meta_filter.should_persist(content)
            if not should:
                logger.info(f"[shared_memory] 熵值过滤拦截 | source={source_agent} score={entropy_score}")
                return None
        else:
            entropy_score, details = self.meta_filter.compute_entropy_score(content)

        mem_id = f"mem_{source_agent}_{int(time.time() * 1000)}"

        meta = {
            "source_agent": source_agent,
            "timestamp": time.time(),
            "entropy_score": entropy_score,
            "knowledge_points": json.dumps(metadata.get("knowledge_points", []), ensure_ascii=False) if metadata else "[]",
            "confidence": metadata.get("confidence", 0.8) if metadata else 0.8,
            "intent_type": metadata.get("intent_type", "") if metadata else "",
            "session_id": metadata.get("session_id", "") if metadata else "",
        }
        if metadata:
            for k, v in metadata.items():
                if k not in meta and isinstance(v, (str, int, float, bool)):
                    meta[k] = v

        try:
            embedding = self._embeddings.embed_query(content)
            self._collection.add(
                ids=[mem_id],
                documents=[content],
                embeddings=[embedding],
                metadatas=[meta],
            )
            logger.info(f"[shared_memory] ✅ 存储 | id={mem_id} source={source_agent} entropy={entropy_score}")
            return mem_id
        except Exception as e:
            logger.warning(f"[shared_memory] ⚠️ 向量存储失败，降级为纯文档存储: {e}")
            try:
                self._collection.add(
                    ids=[mem_id],
                    documents=[content],
                    metadatas=[meta],
                )
                logger.info(f"[shared_memory] ✅ 降级存储成功 | id={mem_id}")
                return mem_id
            except Exception as e2:
                logger.error(f"[shared_memory] ❌ 存储完全失败: {e2}")
                return None

    def retrieve(self, query: str, top_k: int = 5, intent_type: str = "") -> List[Dict]:
        """检索与查询相关的共享记忆"""
        self._ensure_initialized()
        if not self._initialized:
            return []

        where_filter = None
        if intent_type:
            where_filter = {"intent_type": intent_type}

        try:
            query_embedding = self._embeddings.embed_query(query)

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )

            memories = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    distance = results["distances"][0][i] if results["distances"] else 0.0
                    memories.append({
                        "id": results["ids"][0][i] if results.get("ids") else f"mem_{i}",
                        "content": doc,
                        "metadata": meta,
                        "relevance": round(1.0 - distance, 4),
                        "source_agent": meta.get("source_agent", "unknown"),
                        "confidence": meta.get("confidence", 0.8),
                        "entropy_score": meta.get("entropy_score", 0.0),
                    })

            logger.info(f"[shared_memory] 检索 | query={query[:50]}... 命中={len(memories)}")
            return memories
        except Exception as e:
            logger.warning(f"[shared_memory] ⚠️ 向量检索失败，降级为关键词检索: {e}")
            try:
                results = self._collection.query(
                    query_texts=[query],
                    n_results=top_k,
                    where=where_filter,
                    include=["documents", "metadatas"],
                )
                memories = []
                if results and results.get("documents"):
                    for i, doc in enumerate(results["documents"][0]):
                        meta = results["metadatas"][0][i] if results["metadatas"] else {}
                        memories.append({
                            "id": results["ids"][0][i] if results.get("ids") else f"mem_{i}",
                            "content": doc,
                            "metadata": meta,
                            "relevance": 0.5,
                            "source_agent": meta.get("source_agent", "unknown"),
                            "confidence": meta.get("confidence", 0.8),
                            "entropy_score": meta.get("entropy_score", 0.0),
                        })
                logger.info(f"[shared_memory] 降级检索 | 命中={len(memories)}")
                return memories
            except Exception as e2:
                logger.error(f"[shared_memory] ❌ 检索完全失败: {e2}")
                return []

    def store_agent_insight(
        self,
        agent_role: str,
        advice: str,
        state: Dict,
        confidence: float = 0.8,
    ) -> Optional[str]:
        """存储智能体推理洞察（便捷方法）"""
        metadata = {
            "intent_type": state.get("intent_type", ""),
            "confidence": confidence,
            "knowledge_points": state.get("learning_questions", []),
            "difficulty_score": state.get("difficulty_score", 0.5),
        }
        return self.store(
            content=advice,
            source_agent=agent_role,
            metadata=metadata,
        )

    def get_stats(self) -> Dict:
        """获取共享记忆统计信息"""
        self._ensure_initialized()
        if not self._initialized:
            return {"total": 0, "initialized": False}
        try:
            count = self._collection.count()
            return {"total": count, "initialized": True}
        except Exception:
            return {"total": 0, "initialized": False}


# ============================================================
# 逻辑层 — 信任加权投票共识
# ============================================================

class AgentReputationStore:
    """跨会话的智能体信誉积分持久化存储"""

    DEFAULT_REPUTATION_FILE = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "data", "agent_reputation.json"
    )

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.file_path = cfg.get("reputation_file", self.DEFAULT_REPUTATION_FILE)
        self._lock = threading.Lock()
        self._reputation: Dict[str, Dict] = {}
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.file_path):
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self._reputation = json.load(f)
                logger.info(f"[reputation] ✅ 加载信誉数据 | {len(self._reputation)} 个智能体")
            else:
                self._reputation = {}
                logger.info("[reputation] 信誉文件不存在，使用空数据")
        except Exception as e:
            logger.error(f"[reputation] ❌ 加载失败: {e}")
            self._reputation = {}

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self._reputation, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[reputation] ❌ 保存失败: {e}")

    def _ensure_agent(self, role: str):
        if role not in self._reputation:
            self._reputation[role] = {
                "correct": 0,
                "total": 0,
                "score": 1.0,
                "last_updated": time.time(),
            }

    def update(self, agent_role: str, was_correct: bool, weight: float = 1.0):
        """更新智能体信誉

        Args:
            agent_role: 智能体角色名
            was_correct: 本次决策是否正确
            weight: 本次决策的权重（高难度问题权重更高）
        """
        with self._lock:
            self._ensure_agent(agent_role)
            rec = self._reputation[agent_role]
            rec["total"] += 1
            if was_correct:
                rec["correct"] += 1
            rec["score"] = rec["correct"] / rec["total"] if rec["total"] > 0 else 0.5
            rec["last_updated"] = time.time()
            self._save()

        status = "✅ 正确" if was_correct else "❌ 错误"
        logger.info(
            f"[reputation] {status} | agent={agent_role} "
            f"score={rec['score']:.3f} ({rec['correct']}/{rec['total']})"
        )

    def get_score(self, agent_role: str) -> float:
        """获取智能体信誉分数 (0.0 ~ 1.0)"""
        with self._lock:
            self._ensure_agent(agent_role)
            return self._reputation[agent_role]["score"]

    def get_all_scores(self) -> Dict[str, float]:
        """获取所有智能体的信誉分数"""
        with self._lock:
            result = {}
            for role in self._reputation:
                result[role] = self._reputation[role]["score"]
            return result

    def get_reputation_weights(self, agent_roles: List[str]) -> Dict[str, float]:
        """获取指定智能体的信誉权重矩阵"""
        weights = {}
        for role in agent_roles:
            weights[role] = self.get_score(role)
        return weights

    def batch_update(self, results: List[Tuple[str, bool]]):
        """批量更新信誉"""
        for role, was_correct in results:
            self.update(role, was_correct)


class ConsensusEngine:
    """信任加权投票共识引擎：解决 Agent 间记忆/意见冲突"""

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.reputation_store = AgentReputationStore(cfg)
        self.conflict_threshold = cfg.get("conflict_threshold", 0.4)
        self.min_agreement_ratio = cfg.get("min_agreement_ratio", 0.6)
        logger.info(
            f"[consensus] 初始化 | 冲突阈值={self.conflict_threshold} "
            f"最低一致比={self.min_agreement_ratio}"
        )

    def detect_conflict(self, agent_advices: Dict[str, str]) -> bool:
        """检测智能体意见是否存在冲突

        通过简单的关键词重叠度判断：如果意见间重叠度低于阈值，则认为存在冲突
        """
        if len(agent_advices) < 2:
            return False

        advices = list(agent_advices.values())
        roles = list(agent_advices.keys())

        overlap_scores = []
        for i in range(len(advices)):
            for j in range(i + 1, len(advices)):
                tokens_i = set(advices[i].split())
                tokens_j = set(advices[j].split())
                if not tokens_i or not tokens_j:
                    continue
                intersection = tokens_i & tokens_j
                union = tokens_i | tokens_j
                jaccard = len(intersection) / len(union) if union else 0
                overlap_scores.append(jaccard)

        if not overlap_scores:
            return False

        avg_overlap = sum(overlap_scores) / len(overlap_scores)
        has_conflict = avg_overlap < self.conflict_threshold

        if has_conflict:
            logger.info(f"[consensus] ⚠️ 检测到意见冲突 | 平均重叠度={avg_overlap:.4f}")
        else:
            logger.debug(f"[consensus] 意见一致 | 平均重叠度={avg_overlap:.4f}")

        return has_conflict

    def resolve_conflict(
        self,
        agent_advices: Dict[str, str],
        session_weights: Optional[Dict[str, float]] = None,
    ) -> Dict:
        """通过信任加权投票解决冲突

        Args:
            agent_advices: {agent_role: advice_text}
            session_weights: 当前会话内的权重（来自退火机制）

        Returns:
            {
                "consensus_reached": bool,
                "winning_agents": List[str],
                "winning_advice": str,
                "vote_details": Dict,
                "combined_weights": Dict[str, float],
            }
        """
        if not agent_advices:
            return {
                "consensus_reached": False,
                "winning_agents": [],
                "winning_advice": "",
                "vote_details": {},
                "combined_weights": {},
            }

        roles = list(agent_advices.keys())
        reputation_weights = self.reputation_store.get_reputation_weights(roles)

        combined_weights = {}
        for role in roles:
            rep_w = reputation_weights.get(role, 0.5)
            sess_w = session_weights.get(role, 1.0) if session_weights else 1.0
            combined_weights[role] = round(rep_w * sess_w, 4)

        total_weight = sum(combined_weights.values())
        if total_weight == 0:
            combined_weights = {r: 1.0 for r in roles}
            total_weight = len(roles)

        normalized = {r: w / total_weight for r, w in combined_weights.items()}

        sorted_agents = sorted(normalized.items(), key=lambda x: x[1], reverse=True)
        top_agent = sorted_agents[0][0]
        top_weight = sorted_agents[0][1]

        consensus_reached = top_weight >= self.min_agreement_ratio

        vote_details = {}
        for role, weight in sorted_agents:
            vote_details[role] = {
                "reputation_weight": reputation_weights.get(role, 0.5),
                "session_weight": session_weights.get(role, 1.0) if session_weights else 1.0,
                "combined_weight": combined_weights[role],
                "normalized_weight": round(weight, 4),
            }

        result = {
            "consensus_reached": consensus_reached,
            "winning_agents": [top_agent],
            "winning_advice": agent_advices[top_agent],
            "vote_details": vote_details,
            "combined_weights": combined_weights,
        }

        logger.info(
            f"[consensus] {'✅ 共识达成' if consensus_reached else '⚠️ 共识未达成'} | "
            f"胜出={top_agent} 权重={top_weight:.4f}"
        )

        return result

    def update_reputation_from_validation(
        self,
        active_experts: List[str],
        validation_passed: bool,
        agent_weights: Dict[str, float],
    ):
        """根据校验结果更新智能体信誉

        校验通过 → 所有参与专家 +1 correct
        校验失败 → 权重最低的专家 -1 correct，权重最高的专家不受影响
        """
        if not active_experts:
            return

        if validation_passed:
            for role in active_experts:
                self.reputation_store.update(role, was_correct=True)
        else:
            sorted_by_weight = sorted(
                active_experts,
                key=lambda r: agent_weights.get(r, 1.0),
            )
            low_count = max(1, len(sorted_by_weight) // 3)
            for role in sorted_by_weight[:low_count]:
                self.reputation_store.update(role, was_correct=False)
            for role in sorted_by_weight[low_count:]:
                self.reputation_store.update(role, was_correct=True)

    def get_consensus_enhanced_weights(
        self,
        agent_roles: List[str],
        session_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """获取融合信誉的增强权重矩阵"""
        reputation_weights = self.reputation_store.get_reputation_weights(agent_roles)

        enhanced = {}
        for role in agent_roles:
            rep_w = reputation_weights.get(role, 0.5)
            sess_w = session_weights.get(role, 1.0) if session_weights else 1.0
            enhanced[role] = round(rep_w * sess_w, 4)

        return enhanced


# ============================================================
# 便捷入口 — 统一管理三个机制
# ============================================================

class SharedMemorySystem:
    """共享记忆系统统一入口：物理层 + 逻辑层 + 元记忆过滤"""

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        self.store = SharedMemoryStore(cfg.get("store", {}))
        self.consensus = ConsensusEngine(cfg.get("consensus", {}))
        self.filter = self.store.meta_filter
        logger.info("[shared_memory_system] ✅ 共享记忆系统初始化完成")

    def store_insight(
        self,
        agent_role: str,
        content: str,
        state: Dict,
        confidence: float = 0.8,
        force: bool = False,
    ) -> Optional[str]:
        """存储智能体洞察（自动过滤 + 存储）"""
        return self.store.store_agent_insight(agent_role, content, state, confidence)

    def retrieve_relevant(
        self,
        query: str,
        top_k: int = 5,
        intent_type: str = "",
    ) -> List[Dict]:
        """检索相关共享记忆"""
        return self.store.retrieve(query, top_k, intent_type)

    def resolve_conflict(
        self,
        agent_advices: Dict[str, str],
        session_weights: Optional[Dict[str, float]] = None,
    ) -> Dict:
        """解决智能体间意见冲突"""
        return self.consensus.resolve_conflict(agent_advices, session_weights)

    def update_reputation(
        self,
        active_experts: List[str],
        validation_passed: bool,
        agent_weights: Dict[str, float],
    ):
        """根据校验结果更新信誉"""
        self.consensus.update_reputation_from_validation(
            active_experts, validation_passed, agent_weights
        )

    def get_enhanced_weights(
        self,
        agent_roles: List[str],
        session_weights: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """获取融合信誉的增强权重"""
        return self.consensus.get_consensus_enhanced_weights(agent_roles, session_weights)