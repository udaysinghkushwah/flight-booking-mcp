"""OpenAI and OpenAI-compatible (Ollama/vLLM) LLM Provider."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import urllib.error
import urllib.request
import uuid
from typing import List, Optional

from agent.models import AgentStep, Message, ToolCall, ToolDefinition
from agent.providers.base import LLMProvider

try:
    import truststore
    truststore.inject_into_ssl()
    SSL_CONTEXT = ssl.create_default_context()
except Exception:
    SSL_CONTEXT = ssl._create_unverified_context()

logger = logging.getLogger("agent.provider.openai")


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI and any OpenAI-compatible API endpoint."""

    def __init__(
        self,
        model_name: str = "gpt-4o",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        super().__init__(model_name=model_name)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.timeout = timeout or int(os.getenv("LLM_TIMEOUT", "120"))

    def generate_step(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
    ) -> AgentStep:
        openai_tools = [t.to_openai_format() for t in tools] if tools else None

        # Build payload messages
        formatted_messages = []
        for m in messages:
            msg_dict = {"role": m.role}
            if m.content is not None:
                if isinstance(m.content, (dict, list)):
                    msg_dict["content"] = json.dumps(m.content)
                else:
                    msg_dict["content"] = str(m.content)
            if m.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in m.tool_calls
                ]
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            formatted_messages.append(msg_dict)

        payload = {
            "model": self.model_name,
            "messages": formatted_messages,
            "temperature": 0.1,
        }
        if openai_tools:
            payload["tools"] = openai_tools
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=SSL_CONTEXT) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                choice = body["choices"][0]["message"]

                tool_calls: List[ToolCall] = []
                for raw_tc in choice.get("tool_calls", []):
                    func = raw_tc["function"]
                    args = json.loads(func.get("arguments", "{}"))
                    tool_calls.append(ToolCall(
                        id=raw_tc["id"],
                        name=func["name"],
                        arguments=args,
                    ))

                content = choice.get("content")
                if not tool_calls and content:
                    match = re.search(r"\{\s*\"name\"\s*:\s*\"([a-zA-Z0-9_-]+)\"\s*,\s*\"(?:parameters|arguments)\"\s*:\s*(\{.*?\})\s*\}", content, re.DOTALL)
                    if match:
                        tool_name = match.group(1)
                        try:
                            raw_args = json.loads(match.group(2))
                            tool_calls.append(ToolCall(
                                id=f"call_{uuid.uuid4().hex[:8]}",
                                name=tool_name,
                                arguments=raw_args,
                            ))
                        except Exception:
                            pass

                is_done = len(tool_calls) == 0 and bool(content)
                return AgentStep(
                    thought=None,
                    tool_calls=tool_calls,
                    final_response=content if is_done else None,
                    is_complete=is_done,
                )
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8")
            logger.error(f"OpenAI API Error {err.code}: {err_body}")
            raise RuntimeError(f"OpenAI API Error {err.code}: {err_body}")
