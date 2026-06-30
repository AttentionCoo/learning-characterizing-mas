"""Test shared memory system components"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.core.shared_memory import MetaMemoryFilter, ConsensusEngine, AgentReputationStore


def test_meta_memory_filter():
    mf = MetaMemoryFilter()
    text_high_value = "脑卒中急性期溶栓治疗需要严格把握时间窗，发病4.5小时内可使用rtPA静脉溶栓，NIHSS评分是评估卒中严重程度的重要工具。"
    text_noise = "嗯嗯好的知道了谢谢老师"

    should1, score1, detail1 = mf.should_persist(text_high_value)
    should2, score2, detail2 = mf.should_persist(text_noise)

    print(f"High value: should={should1}, entropy={score1:.4f}, detail={detail1}")
    print(f"Noise: should={should2}, entropy={score2:.4f}, detail={detail2}")

    assert should1 is True, f"High value text should persist, entropy={score1}"
    assert should2 is False, f"Noise text should be discarded, entropy={score2}"
    print("PASS: MetaMemoryFilter")


def test_consensus_engine():
    ce = ConsensusEngine()
    advices = {
        "agent_a": "建议从脑血管解剖基础开始复习，重点关注Willis环和脑供血系统。",
        "agent_b": "建议从脑血管解剖基础开始复习，重点关注Willis环和脑供血系统。",
        "agent_c": "建议直接学习溶栓治疗指南，跳过基础解剖知识。",
    }
    result = ce.resolve_conflict(advices)
    reached = result["consensus_reached"]
    winner = result["winning_agents"]
    print(f"Consensus: reached={reached}, winner={winner}")
    assert len(winner) > 0, "Should have a winning agent"
    print("PASS: ConsensusEngine")


def test_reputation_store():
    import tempfile
    test_file = os.path.join(tempfile.gettempdir(), "_test_reputation.json")
    ars = AgentReputationStore(config={"reputation_file": test_file})
    ars.update("agent_a", was_correct=True)
    ars.update("agent_a", was_correct=True)
    ars.update("agent_a", was_correct=False)
    score = ars.get_score("agent_a")
    print(f"Reputation score: {score:.3f}")
    assert abs(score - 2/3) < 0.01, f"Score should be 0.667, got {score}"
    try:
        if os.path.exists(test_file):
            os.remove(test_file)
    except Exception:
        pass
    print("PASS: AgentReputationStore")


def test_batch_filter():
    mf = MetaMemoryFilter()
    text_high = "脑卒中急性期溶栓治疗需要严格把握时间窗，发病4.5小时内可使用rtPA静脉溶栓。"
    text_noise = "嗯嗯好的"
    items = [
        {"content": text_high, "id": 1},
        {"content": text_noise, "id": 2},
    ]
    filtered = mf.filter_batch(items)
    print(f"Batch filter: input={len(items)}, output={len(filtered)}")
    assert len(filtered) == 1, f"Should keep 1 item, got {len(filtered)}"
    print("PASS: BatchFilter")


def test_full_integration():
    from app.agents.core.schema import LearningState
    from app.agents.core.shared_memory import SharedMemorySystem

    state = LearningState(
        case_text="", all_info="", report_mode="", intent_type="",
        context={}, learning_questions=[], key_risks=[], complexity="",
        difficulty_score=0.0, evidence="", proposal="", critique="",
        user_questions=[], report="", expert_advices={},
        validation_passed=True, validation_feedback="",
        reflection_count=0, agent_weights={}, rejection_categories=[],
        debate_history=[], active_experts=[], motivational_feedback="",
        profile_summary="", shared_memory_hits=[], memory_entropy_scores={},
        consensus_result={},
    )
    new_keys = list(state.keys())[-3:]
    print(f"LearningState new fields: {new_keys}")
    assert "shared_memory_hits" in new_keys, "Missing shared_memory_hits"
    assert "memory_entropy_scores" in new_keys, "Missing memory_entropy_scores"
    assert "consensus_result" in new_keys, "Missing consensus_result"

    sms = SharedMemorySystem()
    stats = sms.store.get_stats()
    print(f"SharedMemorySystem: store={stats}, filter={sms.filter.entropy_threshold}, consensus={sms.consensus.conflict_threshold}")

    mem_id = sms.store.store("Test: rtPA溶栓时间窗为4.5小时", "test_agent", force=True)
    print(f"Stored memory: {mem_id}")
    assert mem_id is not None, "Should store high-value memory"

    mem_id2 = sms.store.store("嗯嗯好的", "test_agent", force=False)
    print(f"Noise store result: {mem_id2} (should be None)")
    assert mem_id2 is None, "Should reject noise memory"

    hits = sms.store.retrieve("溶栓时间窗", top_k=3)
    print(f"Retrieved: {len(hits)} hits")
    assert len(hits) >= 1, "Should find at least 1 hit"

    advices = {
        "agent_a": "建议从脑血管解剖基础开始复习，重点关注Willis环。",
        "agent_b": "建议从脑血管解剖基础开始复习，重点关注Willis环。",
        "agent_c": "建议直接学习溶栓治疗指南。",
    }
    result = sms.resolve_conflict(advices)
    print(f"Consensus: reached={result['consensus_reached']}, winner={result['winning_agents']}")
    assert len(result["winning_agents"]) > 0, "Should have a winning agent"

    sms.update_reputation(["agent_a", "agent_b", "agent_c"], True, {})
    scores = sms.consensus.reputation_store.get_all_scores()
    print(f"Reputation after pass: {scores}")

    sms.update_reputation(["agent_a", "agent_b", "agent_c"], False, {"agent_a": 0.5, "agent_b": 1.0, "agent_c": 1.0})
    scores = sms.consensus.reputation_store.get_all_scores()
    print(f"Reputation after fail: {scores}")

    print("PASS: FullIntegration")


if __name__ == "__main__":
    test_meta_memory_filter()
    test_consensus_engine()
    test_reputation_store()
    test_batch_filter()
    test_full_integration()
    print("\n=== ALL TESTS PASSED ===")