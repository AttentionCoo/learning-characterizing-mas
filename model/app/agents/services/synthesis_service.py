from langchain_core.messages import HumanMessage, SystemMessage


class EvidenceSynthesisService:

    FALLBACK_PROMPT = """你是循证教育专家。

学习问题：{question}

教育参考资料：
{evidence}

请进行循证教育总结。"""

    def __init__(
        self,
        llm,
        prompt_manager=None
    ):
        self.llm = llm
        self.prompts = prompt_manager

    def synthesize(
        self,
        question: str,
        evidence: str
    ) -> str:

        prompt = None

        if self.prompts:
            prompt = self.prompts.get(
                "evidence_synthesis",
                question=question,
                evidence=evidence
            )

        if not prompt:
            prompt = self.FALLBACK_PROMPT.format(
                question=question,
                evidence=evidence
            )

        response = self.llm.invoke([
            SystemMessage(content="你是循证教育专家"),
            HumanMessage(content=prompt)
        ])

        return response.content