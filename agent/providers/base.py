"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from agent.models import AgentStep, Message, ToolDefinition


class LLMProvider(ABC):
    """Abstract Strategy interface for Large Language Model backends."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    def generate_step(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
    ) -> AgentStep:
        """Process conversation history and available tools, returning the next agent step."""
        raise NotImplementedError
