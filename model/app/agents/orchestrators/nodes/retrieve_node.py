import logging
import asyncio
from typing import Dict
from app.agents.core.schema import LearningState
from app.agents.orchestrators.nodes.base import BaseNode
from app.agents.constants import MAX_EVIDENCE_CHARS
from app.agents.utils.text_utils import truncate_text

logger = logging.getLogger(__name__)


class RetrieveNode(BaseNode):

    def __init__(self, learning_assistant):
        self.learning_assistant = learning_assistant

    async def run(self, state: LearningState) -> Dict:
        evidence = await self.learning_assistant.afast_parallel_retrieve(
            state["learning_questions"]
        )
        return {"evidence": truncate_text(evidence, MAX_EVIDENCE_CHARS)}