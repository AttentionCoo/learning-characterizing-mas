"""专家注册表：把 YAML 配置的领域专家实例化为可寻址的 Specialist Agent。

每个 SpecialistAgent 是持久化的 react agent（system_prompt + 工具 + 会话 scratchpad），
监督者可通过 dispatch_agent(name, task) 精确点将单挑，而非一次性并行群发。

注：注册表按请求构建（工具闭包捕获当前 state），专家"会话记忆"为请求内 scratchpad，
跨请求的长期记忆由共享记忆系统承担。
"""
import logging
from typing import Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)


class SpecialistAgent:
    """单个领域专家：封装 react agent + 请求内会话记忆。"""

    def __init__(self, role: str, system_prompt: str, llm, tools: List, max_rounds: int = 8):
        self.role = role
        self.system_prompt = system_prompt
        self.llm = llm
        self.tools = tools
        self.max_rounds = max_rounds
        self._agent = None
        self.history: List = []

    def _ensure_agent(self):
        if self._agent is None:
            self._agent = create_react_agent(
                self.llm, tools=self.tools or [], prompt=self.system_prompt,
            )
        return self._agent

    async def run(self, task: str) -> str:
        """让该专家处理一个任务，返回最终发言（保留请求内会话记忆）。"""
        try:
            agent = self._ensure_agent()
            messages = list(self.history) + [HumanMessage(content=task)]
            result = await agent.ainvoke(
                {"messages": messages},
                config={"recursion_limit": self.max_rounds},
            )
            out = result.get("messages", []) or []
            answer = ""
            for m in reversed(out):
                c = getattr(m, "content", "")
                if isinstance(c, str) and c.strip():
                    answer = c.strip()
                    break
            self.history.append(HumanMessage(content=task))
            self.history = self.history[-8:]
            return answer or f"未能获取{self.role}建议。"
        except Exception as e:
            logger.error(f"[registry] {self.role} 执行失败: {e}")
            return f"未能获取{self.role}建议。"


class AgentRegistry:
    """按角色名维护并检索 Specialist Agent。"""

    def __init__(
        self,
        llm,
        expert_configs: List[Dict],
        tool_factory: Callable[[], Dict[str, object]],
        max_rounds: int = 8,
    ):
        self.agents: Dict[str, SpecialistAgent] = {}
        for cfg in expert_configs:
            role = cfg.get("role")
            if not role:
                continue
            all_tools = tool_factory()
            tools_declared = cfg.get("tools") or []
            tools = [all_tools[t] for t in tools_declared if t in all_tools]
            self.agents[role] = SpecialistAgent(
                role=role,
                system_prompt=cfg.get("system_prompt", f"你是专业的{role}"),
                llm=llm,
                tools=tools,
                max_rounds=max_rounds,
            )

    def get(self, role: str) -> Optional[SpecialistAgent]:
        return self.agents.get(role)

    def roles(self) -> List[str]:
        return list(self.agents.keys())
