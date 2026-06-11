from abc import ABC, abstractmethod
from typing import Dict, Any
from app.agents.core.schema import LearningState


class BaseNode(ABC):

    @abstractmethod
    async def run(self, state: LearningState) -> Dict[str, Any]:
        pass