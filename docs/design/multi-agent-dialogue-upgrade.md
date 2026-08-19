# 多智能体升级方案：Agent 间对话信息交流（M2+M3 已实施）

> 状态：已实施（M2 结构化消息 + M3 黑板共享工作区），GitHub 调研报告已合并。
> 目标：把"专家并行独立推理 → 一次性合并"升级为"专家间真实对话协作"。

## 一、现状诊断（已核实代码）

当前系统已是多智能体架构，但 **agent 间通信非常浅**：

| 环节 | 现状 | 问题 |
|:---|:---|:---|
| 专家首次推理 | 并行独立（`reason_node.py` `_ask_expert`） | 每位专家只见 case_info + evidence，**看不到其他专家观点** |
| 辩论 | `DebateOrchestrator`，**max_rounds=1** | 只有 1 轮"广播式回应"，非结构化对话；上下文截断 500 字/条 |
| 综合 | 教学总监一次 LLM 调用合并 | 无中间交互，直接出 Proposal/Critique |
| 共识 | Jaccard 重叠 + 信誉加权投票 | 是仲裁不是对话 |
| 状态通道 | `debate_history` 平铺记录 | 无结构化消息（from/to/type/round） |
| 流式 | `debate` 事件推全文 | 无"谁→谁说了什么"的对话级流式 |

## 二、GitHub 灵感（调研报告已合并，源码级核实）

### 1. 黑板模式（Blackboard）
- [whiteducksoftware/flock](https://github.com/whiteducksoftware/flock)：类型化/版本化 artifact 存储 + 订阅调度（`consumes(Type)/publishes(Type)`）+ dedup/断路器；无 merge（靠避免冲突）
- [claudioed/agent-blackboard](https://github.com/claudioed/agent-blackboard)：9 专家共享黑板，`dict[domain][key]→KnowledgeEntry` 版本化条目 + ontology + 每 agent 读写 ACL（结构最接近本项目 8-9 专家场景）
- [ryanstwrt/multi_agent_blackboard_system](https://github.com/ryanstwrt/multi_agent_blackboard_system)（MABS）：KAAR 触发记录 + controller 选最高触发值胜者（教科书式控制组件）
- [hemantsingh443/blackboard-core](https://github.com/hemantsingh443/blackboard-core)：唯一有真 merge 策略（`MergeStrategy` THEIRS/OURS/FAIL/NEWEST）
- [p3nchan/multi-agent-patterns Blackboard Convergence](https://github.com/p3nchan/multi-agent-patterns/blob/main/patterns/blackboard-convergence.md)：**关键负面案例**——共享散文黑板会编辑战/无收敛/上下文膨胀；修复=结构化 artifact + 状态字段 + 硬轮数上限

### 2. LangGraph 官方多智能体模式
- [extrawest/multi_agent_workflow_demo_in_langgraph](https://github.com/extrawest/multi_agent_workflow_demo_in_langgraph)：3 个 demo（supervisor 中介路由 `next` 字段 / hierarchical 子图拼接 / 对等网络 `sender` 字段）；无 swarm/blackboard demo（0.2 时代 API）
- [langchain-ai/langgraph concepts multi_agent](https://github.com/langchain-ai/langgraph/blob/8c4904bee93cc4124f11132c7c3f4e747dbce3c0/docs/docs/concepts/multi_agent.md)：5 种官方架构共享 `MessagesState + Command` 原语；supervisor 用 `Send()` 做 map-reduce 并行扇出
- [langgraph-supervisor](https://github.com/langchain-ai/langgraph-supervisor-py) 官方包：`create_supervisor` 的 `parallel_tool_calls=True` 一轮扇出多位专家、`add_handoff_messages=True` 交接轨迹、`output_mode="last_message"` 上下文控制
- [langgraph-swarm](https://github.com/langchain-ai/langgraph-swarm-py)：去中心化 handoff（`transfer_to_<agent>` 工具 + `Command(goto, PARENT)`）——**教育场景低适配**
- [LangGraph 101 DeepWiki](https://deepwiki.com/langchain-ai/langgraph-101/6-utilities)：supervisor vs swarm 对比；`RemainingSteps` 内建步数上限
- 关键结论：自定义事件（`get_stream_writer` + `stream_mode="custom"`）**与模式无关**，重构不破坏 Vue SSE 契约

### 3. 共享内存/消息总线
- [Citadel-Cloud-Management/langchain-multi-agent-framework](https://github.com/Citadel-Cloud-Management/langchain-multi-agent-framework)：独立 `SharedMemory`（线程安全、每 agent `MemoryEntry{agent_name, content, entry_type}` 账本）+ `results: dict[str,str]` 面板 + "Context from other agents:" prompt 注入——本项目已有更难的部分（ChromaDB + 熵过滤 + 信任加权共识）
- [hermes-agentmesh](https://github.com/seleman66eeddwegger3-art/hermes-agentmesh)：Redis 异步消息总线（本项目单进程内用 state 通道即可，无需引入）
- [ForceInjection/AI-fundamentals multi_agent_system](https://github.com/ForceInjection/AI-fundamentals)：生产就绪企业级多智能体参考

### 4. 框架级消息传递（AutoGen GroupChat / MetaGPT）
- [AutoGen v0.2 GroupChat](https://github.com/microsoft/autogen/blob/v0.2.36/autogen/agentchat/groupchat.py)：广播进所有 mailbox + 管理器**每轮只选 1 个说话者**（嵌套双 agent 选择器）→ 串行 O(专家数×轮数)；**抄广播+仲裁语义，别抄串行循环**
- [AutoGen v0.4](https://github.com/microsoft/autogen/blob/main/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_base_group_chat.py)：真 pub-sub topic 总线，仍一次一说话者
- [MetaGPT](https://github.com/geekan/MetaGPT)：`Message{cause_by, send_to, instruct_content}` 默认广播（`send_to=ALL`）+ 按 `cause_by`（内容类型）过滤 = pub-sub + 直接 mailbox 寻址；角色并发执行（`asyncio.gather`）；`cause_by`/`send_to` schema 直接映射本项目的 M2 `agent_msg` 事件

### 5. 跨模式对比结论（对本项目）
| 模式 | 适配 | 理由 |
|---|---|---|
| LangGraph Supervisor + `Send()` 扇出 | **高** | 确定性、可审计、可并行——本项目主干 |
| Supervisor tool-calling | **高** | 已实现（`TutorSupervisor`） |
| AutoGen GroupChat 语义 | **中** | 广播+仲裁做辩论轮；保留并行 |
| MetaGPT pub-sub/mailbox | **中-高** | `cause_by`/`send_to` 映射 M2 `agent_msg` |
| Blackboard 类型化分节 | **中-高** | 映射 M3 工作区；仲裁者独占 synthesis 节 |
| Swarm / Network / Hierarchical | **低** | 无界控制流/无覆盖保证，与医学红线冲突 |

## 三、升级方向（候选）

### M1 两阶段会诊（低成本，改 reason_node）
专家先独立出初稿 → 互见全部观点后修订终稿 → 教学总监综合。
- 改动：`_ask_expert` 增加第二阶段，喂入其他专家初稿摘要
- 流式：新增 `agent_msg` 事件（role=from, to=all, round=2, type=revise）

### M2 结构化消息通道（中成本，改 schema + debate）
state 新增 `agent_messages: List[Dict]`：
```python
{"from": "需求分析智能体", "to": "题目生成智能体", "round": 1,
 "type": "question|reply|revise|agree|object", "content": "..."}
```
- 定向提问：A 可以点名问 B（supervisor/教学总监编排"质询"）
- 多轮收敛：max_rounds 提到 2~3，异议驱动停止
- 流式：每条消息实时推 `agent_msg` 事件，前端展示"谁→谁：内容"

后端透传（`AIStreamingServiceImpl.java`）：在 `experts` 分支后加 `agent_msg` 白名单分支
```java
if ("agent_msg".equalsIgnoreCase(type)) {
    Map<String, Object> msgResp = baseResponse(talkId, generatedTitle[0], "agent_msg");
    msgResp.put("from", json.path("from").asText(""));
    msgResp.put("to", json.path("to").asText(""));
    msgResp.put("round", json.path("round").asInt(1));
    msgResp.put("kind", json.path("kind").asText(""));
    msgResp.put("content", json.path("content").asText(""));
    return Flux.just(objectMapper.writeValueAsString(msgResp));
}
```

### M3 黑板共享工作区（高成本，改 reason_node + schema + 前端）
state 新增 `blackboard: List[Dict]`，专家写发现/读发现/认领子问题：
```python
{"role": "...", "claim": "子问题3", "finding": "...", "revises": "特征抽取智能体"}
```
- 复用现有共享记忆的冲突检测 + 信誉加权
- 教学总监从黑板收敛

## 四、流式契约（新增事件）

```jsonc
// agent_msg 事件（对话级，区别于 debate 的轮次级）
{"type": "agent_msg", "talkId": "...",
 "from": "需求分析智能体", "to": "题目生成智能体",
 "round": 1, "kind": "question",
 "content": "题目难度与画像匹配度如何评估？"}
```

## 五、前端接入点（已核实）

新增 `agent_msg` 事件只需两处：

1. `frontend/src/utils/sseStream.js` — 在 `type === 'experts'` 分支后加 `agent_msg` 分支，把 `{from, to, round, kind, content}` 映射为 `onThinking({phase: 'agent_msg', ...})`
2. `frontend/src/components/ReasoningTrace.vue` — 新增 `agent-msg` 渲染块（参考现有 `.debate-item` 样式：`谁 → 谁：内容`），并在 `phaseLabel` 增加 `agent_msg: '对话'`

## 六、待办
- [x] M2+M3 组合已实施（用户选定）
- [ ] 合并子代理 GitHub 调研报告（extrawest / Citadel / langgraph-101 / AutoGen / MetaGPT）
- [ ] 重建镜像 + e2e 验证 + commit/push

## 七、实施记录（M2+M3 组合）

### 新增文件
- `model/app/agents/orchestrators/nodes/reason_dialogue.py` — `DialogueOrchestrator`：
  - M2：`_ask_dialogue` 让每位专家基于「黑板 + 消息历史 + 他人观点」输出 0~2 条结构化消息（JSON），`_parse_messages` 做白名单/结构校验（kind ∈ question/reply/revise/agree/object/finding）
  - M3：黑板初始化写入每位专家初稿，`_update_blackboard` 支持修订；`_run_convergence` 教学总监收敛；`_run_arbitration` 依据对话+黑板+证据裁决
  - 异议驱动停止：本轮无 object/question/revise 且 ≥2 轮 → 提前收敛；无消息 → 立即停止
- `model/tests/test_reason_dialogue.py` — 8 个单测（消息解析、黑板修订、异常兜底、收敛跳过）

### 修改文件
- `model/app/agents/core/schema.py` — LearningState 增加 `agent_messages: List[Dict]`、`blackboard: List[Dict]`
- `model/app/agents/orchestrators/learning_agent.py` — initial_state 初始化两通道；custom 分支透传 `agent_msg`/`blackboard` 事件
- `model/app/agents/orchestrators/nodes/reason_node.py` — 初稿后优先走 `DialogueOrchestrator`（dialogue_enabled），旧 DebateOrchestrator 保留为回退；收敛结论 + 对话摘要并入综合输入；返回携带两通道
- `model/app/config/config_loader.py` — 新增 `is_dialogue_enabled()`
- `model/app/config/expert_config.yaml` — debate 节新增 `dialogue_enabled: true`、`dialogue_max_rounds: 2`、`dialogue_prompt_template`
- `backend/server/.../AIStreamingServiceImpl.java` — 新增 `agent_msg`/`blackboard` 白名单透传
- `frontend/src/utils/sseStream.js` — 新增 agent_msg/blackboard 事件映射
- `frontend/src/components/ReasoningTrace.vue` — 新增「专家间对话」「会诊黑板」渲染块与样式
- `frontend/tests/sseStream.test.js` — 新增 agent_msg/blackboard 事件映射测试

### 流式契约
```jsonc
// agent_msg（对话级）
{"type":"agent_msg","node":"reason","from":"需求分析智能体","to":"题目生成智能体",
 "round":1,"kind":"question","content":"难度怎么定？"}
// blackboard（黑板快照 + 收敛 + 仲裁）
{"type":"blackboard","node":"reason","entries":[{"role":"...","round":1,"kind":"finding","content":"..."}],
 "convergence":"...","arbitration":"..."}
```

### 关键设计决策
- 对话模板用 `str.replace` 而非 `str.format`：模板内含 JSON 字面量 `{"kind":...}`，format 会误解析为占位符（实测 KeyError）
- 消息 kind 白名单含 `finding`（初版遗漏导致测试失败，已修）
- `dialogue_enabled` 独立于 `debate.enabled`，可在 YAML 一键回退旧广播辩论
- 收敛结论 + 对话摘要拼入 synthesis 输入，教学总监综合时可见专家间讨论过程
