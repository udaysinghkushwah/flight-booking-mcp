"""Domain models and typed dataclasses for the MCP AI Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class RiskLevel(str, Enum):
    """Operation risk level for tool execution."""

    READ_ONLY = "READ_ONLY"
    MUTATION_MEDIUM = "MUTATION_MEDIUM"
    MUTATION_CRITICAL = "MUTATION_CRITICAL"


@dataclass
class ToolDefinition:
    """Standardized MCP tool definition."""

    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)

    def to_openai_format(self) -> Dict[str, Any]:
        """Convert MCP tool schema to OpenAI / OpenAI-compatible tool spec."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema if self.input_schema else {"type": "object", "properties": {}},
            },
        }

    def to_anthropic_format(self) -> Dict[str, Any]:
        """Convert MCP tool schema to Anthropic tool spec."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema if self.input_schema else {"type": "object", "properties": {}},
        }


@dataclass
class ToolCall:
    """Structured tool call requested by an LLM."""

    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResult:
    """Structured execution output from an MCP tool."""

    call_id: str
    tool_name: str
    data: Any
    is_error: bool = False
    latency_ms: float = 0.0


@dataclass
class Message:
    """Normalized multi-turn chat message."""

    role: str  # 'system', 'user', 'assistant', 'tool'
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"role": self.role}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass
class AgentStep:
    """Single step in an agent's reasoning-action cycle."""

    thought: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    final_response: Optional[str] = None
    is_complete: bool = False
