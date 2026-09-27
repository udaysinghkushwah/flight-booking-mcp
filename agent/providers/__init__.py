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

    env_model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    target_model = model or env_model

    if resolved_backend == "openai":
        return OpenAIProvider(model_name=target_model or "gpt-4o")
    elif resolved_backend == "openai_compatible":
        return OpenAIProvider(model_name=target_model or "llama3:8b")
    elif resolved_backend == "anthropic":
        return AnthropicProvider(model_name=target_model or "claude-3-5-sonnet-20241022")
    elif resolved_backend == "cognitive_builtin":
        return CognitiveEngineProvider(model_name=target_model or "flight-cognitive-v1")
    else:
        raise ValueError(f"Unknown LLM backend: '{backend}'. Supported: auto, openai, anthropic, cognitive_builtin")


__all__ = ["LLMProvider", "OpenAIProvider", "AnthropicProvider", "CognitiveEngineProvider", "create_provider"]
