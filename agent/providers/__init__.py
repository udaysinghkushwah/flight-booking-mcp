"""LLM Provider factory for the Flight AI Agent."""

from __future__ import annotations

import os
from typing import Optional

from agent.providers.anthropic_provider import AnthropicProvider
from agent.providers.base import LLMProvider
from agent.providers.cognitive_engine import CognitiveEngineProvider
from agent.providers.openai_provider import OpenAIProvider


def create_provider(backend: str = "auto", model: Optional[str] = None) -> LLMProvider:
    """Instantiate the appropriate LLM provider strategy based on config and env."""
    resolved_backend = backend.lower()
    if resolved_backend == "auto":
        if os.getenv("OPENAI_API_KEY"):
            resolved_backend = "openai"
        elif os.getenv("ANTHROPIC_API_KEY"):
            resolved_backend = "anthropic"
        elif os.getenv("OPENAI_BASE_URL"):
            resolved_backend = "openai_compatible"
        else:
            resolved_backend = "cognitive_builtin"

    if resolved_backend == "openai":
        return OpenAIProvider(model_name=model or "gpt-4o")
    elif resolved_backend == "openai_compatible":
        return OpenAIProvider(model_name=model or "llama3")
    elif resolved_backend == "anthropic":
        return AnthropicProvider(model_name=model or "claude-3-5-sonnet-20241022")
    elif resolved_backend == "cognitive_builtin":
        return CognitiveEngineProvider(model_name=model or "flight-cognitive-v1")
    else:
        raise ValueError(f"Unknown LLM backend: '{backend}'. Supported: auto, openai, anthropic, cognitive_builtin")


__all__ = ["LLMProvider", "OpenAIProvider", "AnthropicProvider", "CognitiveEngineProvider", "create_provider"]
