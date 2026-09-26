"""Anthropic Claude LLM Provider."""

from __future__ import annotations

import json
import logging
import os
import ssl
import urllib.error
import urllib.request
from typing import List, Optional

from agent.models import AgentStep, Message, ToolCall, ToolDefinition
from agent.providers.base import LLMProvider

try:
    import truststore
    truststore.inject_into_ssl()
    SSL_CONTEXT = ssl.create_default_context()
except Exception:
    SSL_CONTEXT = ssl._create_unverified_context()

logger = logging.getLogger("agent.provider.anthropic")


class AnthropicProvider(LLMProvider):
    """Native Anthropic Messages API Provider."""

    def __init__(
        self,
        model_name: str = "claude-3-5-sonnet-20241022",
        api_key: Optional[str] = None,
    ):
        super().__init__(model_name=model_name)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")

    def generate_step(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
    ) -> AgentStep:
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required for AnthropicProvider.")

        anthropic_tools = [t.to_anthropic_format() for t in tools] if tools else []

        system_prompt = ""
        user_or_asst_messages = []
        for m in messages:
            if m.role == "system":
                system_prompt = m.content or ""
            elif m.role == "tool":
                user_or_asst_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id,
                        "content": json.dumps(m.content) if isinstance(m.content, (dict, list)) else str(m.content),
                    }],
                })
            elif m.role == "assistant":
                content_blocks = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                if m.tool_calls:
                    for tc in m.tool_calls:
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                user_or_asst_messages.append({"role": "assistant", "content": content_blocks})
            else:
                user_or_asst_messages.append({
                    "role": "user",
                    "content": m.content or "",
                })

        payload = {
            "model": self.model_name,
            "max_tokens": 1024,
            "messages": user_or_asst_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if anthropic_tools:
            payload["tools"] = anthropic_tools

        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode("utf-8"), method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("x-api-key", self.api_key)
        req.add_header("anthropic-version", "2023-06-01")

        try:
            with urllib.request.urlopen(req, timeout=30, context=SSL_CONTEXT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                stop_reason = body.get("stop_reason")
                content_blocks = body.get("content", [])

                tool_calls: List[ToolCall] = []
                text_response: List[str] = []

                for block in content_blocks:
                    if block.get("type") == "tool_use":
                        tool_calls.append(ToolCall(
                            id=block["id"],
                            name=block["name"],
                            arguments=block.get("input", {}),
                        ))
                    elif block.get("type") == "text":
                        text_response.append(block.get("text", ""))

                combined_text = "\n".join(text_response).strip()
                is_done = stop_reason == "end_turn" and len(tool_calls) == 0

                return AgentStep(
                    thought=None,
                    tool_calls=tool_calls,
                    final_response=combined_text if is_done else None,
                    is_complete=is_done,
                )
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8")
            logger.error(f"Anthropic API Error {err.code}: {err_body}")
            raise RuntimeError(f"Anthropic API Error {err.code}: {err_body}")
