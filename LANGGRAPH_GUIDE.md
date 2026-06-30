# LangGraph 完整学习指南

> 如果你会 LangChain，那么可以这样理解：
> - **LangChain** = 单链路调用
> - **LangGraph** = 多节点状态机（State Machine）+ Agent 工作流编排
>
> LangGraph 特别适合：多Agent系统、RAG系统、知识图谱问答系统

---

# 第一章：核心概念

LangGraph 的核心只有四个东西：

```
State（状态）
  ↓
Node（节点）
  ↓
Edge（边）
  ↓
Graph（图）
```

整体结构类似：

```
开始
  ↓
LLM分析问题
  ↓
判断是否需要检索
  ↓
  ┌───────┐
  ↓       ↓
RAG      直接回答
  ↓       ↓
生成答案
  ↓
结束
```

---

# 第二章：State（状态）— 最重要

## 2.1 什么是 State？

State 是整个图的**数据共享区**。所有节点都从 State 中读取数据，也把处理结果写回 State。

## 2.2 定义 State

使用 `TypedDict` 定义：

```python
from typing import TypedDict

class State(TypedDict):
    question: str
    answer: str
    docs: list
```

## 2.3 运行时的 State

运行过程中，State 会像这样不断被更新：

```python
# 初始状态
{
    "question": "什么是黑洞",
    "docs": [],
    "answer": ""
}

# 经过检索节点后
{
    "question": "什么是黑洞",
    "docs": [Document(...), Document(...)],
    "answer": ""
}

# 经过生成节点后
{
    "question": "什么是黑洞",
    "docs": [Document(...), Document(...)],
    "answer": "黑洞是时空中的一个区域..."
}
```

## 2.4 关键机制：累积合并

LangGraph 的状态更新是**合并**而非替换。每个节点只需要返回它想修改的字段，其他字段自动保留。

```python
# 检索节点只返回 docs，question 和 answer 自动保留
def retrieve(state):
    docs = vectorstore.similarity_search(state["question"])
    return {"docs": docs}  # 只返回要更新的字段
```

---

# 第三章：Node（节点）

## 3.1 节点本质

```
State -> State

即：
输入状态
  ↓
处理
  ↓
返回更新状态
```

## 3.2 检索节点示例

```python
def retrieve(state):
    question = state["question"]
    docs = vectorstore.similarity_search(question)
    return {"docs": docs}
```

## 3.3 生成节点示例

```python
def generate(state):
    question = state["question"]
    docs = state["docs"]
    answer = llm.invoke(f"问题:{question}\n参考:{docs}")
    return {"answer": answer}
```

## 3.4 节点设计原则

- 每个节点只关心自己需要读的字段
- 只返回自己负责写的字段
- 互不干扰，LangGraph 负责合并

---

# 第四章：构建图

## 4.1 创建图

```python
from langgraph.graph import StateGraph

graph = StateGraph(State)
```

## 4.2 添加节点

```python
graph.add_node("retrieve", retrieve)
graph.add_node("generate", generate)
```

效果：

```
retrieve
generate
```

## 4.3 添加边

```python
graph.add_edge("retrieve", "generate")
```

效果：

```
retrieve
    ↓
generate
```

## 4.4 开始和结束

LangGraph 提供 `START` 和 `END` 标记：

```python
from langgraph.graph import START, END

graph.add_edge(START, "retrieve")
graph.add_edge("generate", END)
```

完整的图：

```
START
  ↓
retrieve
  ↓
generate
  ↓
END
```

## 4.5 编译

图定义完后**必须编译**才能运行：

```python
app = graph.compile()
```

## 4.6 执行

```python
result = app.invoke({"question": "什么是黑洞"})
```

返回：

```python
{
    "question": "什么是黑洞",
    "docs": [...],
    "answer": "..."
}
```

---

# 第五章：条件路由（重点）

## 5.1 为什么需要条件路由？

Agent 最常用的模式——根据当前状态决定下一步走哪条路。

```
用户问题
  ↓
判断
  ↓
需要RAG?
  ↓
  ┌───────┐
  ↓       ↓
retrieve  generate
```

## 5.2 定义路由函数

```python
def route(state):
    question = state["question"]
    if "数据库" in question:
        return "retrieve"
    return "generate"
```

## 5.3 添加条件边

```python
graph.add_conditional_edges("router", route)
```

图：

```
router
  ↓
  ┌───────┐
  ↓       ↓
retrieve generate
```

## 5.4 带映射表的条件边

```python
graph.add_conditional_edges(
    "intent",
    route_intent,
    {
        "rag": "retrieve",
        "direct": "generate",
        "reject": "reject_node",
    }
)
```

路由函数返回的字符串会查映射表，决定去哪个节点。

---

# 第六章：Command（新写法）

LangGraph 推荐的新写法：节点直接决定去哪，不用写额外路由函数。

```python
from langgraph.types import Command

def router(state):
    if need_rag:
        return Command(goto="retrieve")
    return Command(goto="generate")
```

**对比旧写法**：

| 旧写法 | 新写法（Command） |
|--------|------------------|
| 路由函数 + 条件边分开写 | 节点内部直接决定 |
| 逻辑分散在两处 | 逻辑集中在一处 |
| 需要维护映射表 | 不需要映射表 |

---

# 第七章：MessagesState

## 7.1 Agent 最常用的 State

LangGraph 内置了 `MessagesState`：

```python
from langgraph.graph import MessagesState

class State(MessagesState):
    pass
```

本质就是：

```python
{
    "messages": [
        HumanMessage(...),
        AIMessage(...)
    ]
}
```

## 7.2 LLM 节点典型写法

```python
def chatbot(state):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}
```

---

# 第八章：Tool 节点

## 8.1 使用预构建的 ToolNode

LangGraph 官方推荐：

```python
from langgraph.prebuilt import ToolNode

tools = [search_tool, calculator_tool]
tool_node = ToolNode(tools)
```

加入图：

```python
graph.add_node("tools", tool_node)
```

---

# 第九章：ReAct Agent

## 9.1 最经典的 Agent 结构

```
用户
  ↓
LLM
  ↓
需要工具?
  ↓
  ┌───────┐
  ↓       ↓
Tool     END
  ↓
LLM
  ↓
END
```

## 9.2 一行代码创建

```python
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model=llm,
    tools=tools
)
```

直接就是完整的 Agent，不需要手动构建图。

---

# 第十章：Memory（记忆）

## 10.1 为什么需要 Memory？

默认情况下，每次调用图都是独立的，不会记住之前的对话。Memory 让图可以保存历史状态。

## 10.2 使用 MemorySaver

```python
from langgraph.checkpoint.memory import MemorySaver

memory = MemorySaver()
```

编译时传入：

```python
app = graph.compile(checkpointer=memory)
```

## 10.3 执行时指定线程 ID

```python
config = {
    "configurable": {
        "thread_id": "1"
    }
}

app.invoke({"messages": [...]}, config=config)
```

同一个 `thread_id` 的多轮对话会自动保存和恢复。

---

# 第十一章：Streaming（流式输出）

## 11.1 基本用法

```python
for chunk in app.stream({"question": "什么是黑洞"}):
    print(chunk)
```

输出（每个节点执行完输出一次）：

```python
{"retrieve": {"docs": [...]}}
{"generate": {"answer": "..."}}
```

可以实时看到每个节点的执行过程。

## 11.2 流式事件

```python
async for event in app.astream_events(initial_state, version="v2"):
    # 可以捕获更细粒度的事件
    if event["event"] == "on_chat_model_stream":
        # LLM 逐 token 输出
        print(event["data"]["chunk"].content, end="")
```

---

# 第十二章：Human-in-the-loop（人工介入）

## 12.1 LangGraph 的王牌功能

运行到某个节点时暂停，等待人工确认后继续。

## 12.2 使用 interrupt()

```python
from langgraph.types import interrupt

def approve(state):
    result = interrupt("是否执行删除数据库?")
    return {"approved": result}
```

## 12.3 用户确认后继续

```python
app.invoke(Command(resume=True))
```

## 12.4 典型场景

- 危险操作前需要人工确认（如删除数据）
- 需要人工审核 AI 的输出
- 需要人工补充信息

---

# 第十三章：多 Agent 架构

## 13.1 Supervisor Agent 模式

最经典的多 Agent 架构：

```
用户
  ↓
Supervisor（调度者）
  ↓
  ┌─────────────┐
  ↓             ↓
Agent A       Agent B
  ↓             ↓
  └──────┬──────┘
         ↓
     汇总输出
         ↓
        END
```

Supervisor 负责决定把任务分给哪个 Agent，以及如何汇总结果。

## 13.2 典型结构：知识图谱 + RAG 多 Agent

```
用户
  ↓
Supervisor
  ↓
  ┌─────────────┐
  ↓             ↓
KG Agent     RAG Agent
  ↓             ↓
  └──────┬──────┘
         ↓
     Answer Agent
         ↓
        END
```

- **KG Agent**：查询 Neo4j 知识图谱
- **RAG Agent**：检索向量数据库
- **Answer Agent**：综合两个 Agent 的结果生成最终答案

## 13.3 项目中的实际应用

本项目的 `LearningAgent` 就是多 Agent 架构：

```
用户请求
  ↓
IntentNode（Supervisor 角色：判断意图，分配路由）
  ↓
  ┌───────────────────────┐
  ↓           ↓           ↓
reject    knowledge    analysis
                          ↓
                    AnalysisNode（拆解需求）
                          ↓
                    RetrieveNode（RAG 检索）
                          ↓
                    ReasonNode（多专家 Agent 并行推理）
                          ↓
                    ValidateNode（质检，不通过则退回）
                          ↓
                    ReportNode（生成报告）
```

---

# 第十四章：学习路线

## 第一阶段：必须掌握

| 概念 | 说明 |
|------|------|
| `StateGraph` | 创建图的入口 |
| `State` | 定义共享数据结构 |
| `Node` | 定义处理逻辑 |
| `Edge` | 定义执行顺序 |
| `START` / `END` | 图的入口和出口 |
| `compile()` | 编译图为可执行对象 |
| `invoke()` | 执行图 |

## 第二阶段：必须掌握

| 概念 | 说明 |
|------|------|
| `Conditional Edge` | 条件路由，根据状态决定走哪条路 |
| `Command` | 新写法，节点内部直接决定去哪 |
| `MessagesState` | Agent 对话专用的 State |
| `MemorySaver` | 保存对话历史 |
| `stream()` | 流式输出 |

## 第三阶段：多 Agent 进阶

| 概念 | 说明 |
|------|------|
| `Supervisor Agent` | 调度者模式，分配任务给子 Agent |
| `ToolNode` | 预构建的工具调用节点 |
| `Human-in-the-loop` | 人工介入，运行中暂停等待确认 |
| `create_react_agent` | 一行代码创建 ReAct Agent |

## 学习建议

1. 先用最简单的 `StateGraph + Node + Edge` 跑通一个两节点流程
2. 加上 `Conditional Edge`，实现条件路由
3. 加上 `MemorySaver`，实现多轮对话
4. 用 `create_react_agent` 快速创建一个带工具的 Agent
5. 手动构建 Supervisor 多 Agent 架构
6. 再看 LangGraph 官方的 Supervisor、多 Agent、Memory 和 Deep Agent 示例

---

# 附录：本项目中的 LangGraph 映射

| LangGraph 概念 | 本项目实现 | 文件位置 |
|----------------|-----------|---------|
| `State` | `LearningState` | `app/agents/core/schema.py` |
| `Node` | `IntentNode`, `AnalysisNode`, `RetrieveNode`, `ReasonNode`, `ValidateNode`, `ReportNode` | `app/agents/orchestrators/nodes/` |
| `Edge` | `graph.add_edge()` 固定边 | `app/agents/orchestrators/clinical_graph.py` |
| `Conditional Edge` | `_route_intent()`, `_route_validation()` | `app/agents/orchestrators/clinical_graph.py` |
| `MemorySaver` | `self.checkpointer = MemorySaver()` | `app/agents/orchestrators/clinical_graph.py` |
| `compile()` | `graph.compile(checkpointer=...)` | `app/agents/orchestrators/clinical_graph.py` |
| `astream_events()` | `self.graph.astream_events(initial_state, ...)` | `app/agents/orchestrators/qwen_agent.py` |
| 反思循环 | `validate → reason → validate` 环路 | `app/agents/orchestrators/clinical_graph.py` |
| 共享记忆 | `SharedMemorySystem`（物理层+逻辑层+元记忆过滤） | `app/agents/core/shared_memory.py` |
| 共享记忆配置 | `SharedMemoryConfigManager` | `app/config/shared_memory_config.yaml` |