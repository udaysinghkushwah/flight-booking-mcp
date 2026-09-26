"""Production AI Agent orchestrating LLM reasoning with MCP tool execution."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from agent.client import MCPClient
from agent.models import Message, ToolCall, ToolDefinition
from agent.providers import create_provider
from agent.providers.base import LLMProvider
from agent.safety import HumanInTheLoopGate

logger = logging.getLogger("agent.orchestrator")


class ProductionFlightAgent:
    """Production AI Agent orchestrating LLM reasoning with live MCP tool execution."""

    def __init__(
        self,
        mcp_client: MCPClient,
        backend: str = "auto",
        model: Optional[str] = None,
        auto_approve: bool = False,
        provider: Optional[LLMProvider] = None,
        safety_gate: Optional[HumanInTheLoopGate] = None,
    ):
        self.mcp = mcp_client
        self.provider = provider or create_provider(backend=backend, model=model)
        self.safety_gate = safety_gate or HumanInTheLoopGate(auto_approve=auto_approve)
        self.auto_approve = auto_approve
        self.tools: List[ToolDefinition] = []

    def bootstrap(self) -> None:
        """Connect to MCP server, verify handshake, and sync available tools and prompt templates."""
        print(f"🔄 Initializing MCP connection to {self.mcp.base_url}...")
        init_res = self.mcp.initialize()
        server_info = init_res.get("serverInfo", {})
        print(f"   Connected to server: {server_info.get('name', 'mcp-server')} v{server_info.get('version', '1.0')}")

        print("🔍 Syncing available tools from MCP server...")
        raw_tools = self.mcp.list_tools()
        self.tools = []
        for t in raw_tools:
            if isinstance(t, ToolDefinition):
                self.tools.append(t)
            elif isinstance(t, dict):
                self.tools.append(ToolDefinition(
                    name=t.get("name", ""),
                    description=t.get("description", ""),
                    input_schema=t.get("inputSchema") or t.get("input_schema") or {},
                ))

        print(f"   Discovered {len(self.tools)} MCP tools:")
        for t in self.tools:
            desc = t.description[:65] + "..." if len(t.description) > 65 else t.description
            print(f"     • {t.name}: {desc}")

        prompts = self.mcp.list_prompts()
        print(f"📋 Discovered {len(prompts)} MCP Prompt Templates on server:")
        for p in prompts:
            print(f"     • {p['name']}")

    def convert_mcp_to_openai_tools(self) -> List[Dict[str, Any]]:
        """Translate MCP tools to OpenAI format (for backwards compatibility & inspection)."""
        return [t.to_openai_format() for t in self.tools]

    def check_human_in_the_loop_gate(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Delegate approval verification to the Safety Gate."""
        return self.safety_gate.authorize(tool_name, arguments)

    def execute_tool_with_guardrails(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool on the live MCP server with safety gates and telemetry."""
        # 1. Human-In-The-Loop Safety Gate
        if not self.check_human_in_the_loop_gate(tool_name, arguments):
            return {
                "status": "REJECTED_BY_OPERATOR",
                "message": f"Action {tool_name} was aborted by human supervisor.",
                "isError": True,
            }

        # 2. Idempotency Key Injection for mutating actions
        if tool_name == "create_booking_tool" and "idempotency_key" not in arguments:
            arguments["idempotency_key"] = f"agent-uuid-{uuid.uuid4().hex[:12]}"

        print(f"\n⚡ [MCP DISPATCH] Calling tool '{tool_name}' on AWS ECS...")
        t0 = time.perf_counter()
        result = self.mcp.call_tool(tool_name, arguments)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        res_keys = list(result.keys()) if isinstance(result, dict) else "list"
        print(f"   [MCP RETURN] Latency: {latency_ms:.1f}ms | Response keys: {res_keys}")
        return result

    def run(self, user_intent: str, max_turns: int = 6) -> str:
        """Run the end-to-end agentic reasoning and MCP tool execution loop."""
        print("\n" + "=" * 70)
        print("🤖  STARTING PRODUCTION FLIGHT AGENTIC LOOP")
        print(f"Provider: {self.provider.__class__.__name__} (Model: {self.provider.model_name})")
        print(f"User Request:\n    \"{user_intent}\"")
        print("=" * 70)

        # Hydrate system prompt template from MCP server
        system_prompt = self.mcp.get_prompt("flight_itinerary_assistant", {
            "origin": "JFK",
            "destination": "LHR",
            "departure_date": "2026-09-28",
        })
        if not system_prompt:
            system_prompt = "You are an autonomous Flight Booking Agent interacting via Model Context Protocol."

        conversation: List[Message] = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_intent),
        ]

        for turn in range(1, max_turns + 1):
            print(f"\n🧠 [Turn {turn}] Agent Reasoning...")

            step = self.provider.generate_step(conversation, self.tools)

            # Check if LLM completed reasoning
            if step.is_complete and step.final_response:
                print("\n✅ Final Response from Agent:")
                print("-" * 50)
                print(step.final_response)
                print("-" * 50)
                return step.final_response

            if not step.tool_calls:
                if step.final_response:
                    return step.final_response
                return "Agent terminated without action."

            # Execute tool calls
            for tc in step.tool_calls:
                args_summary = ", ".join(f"{k}={v}" for k, v in tc.arguments.items())
                print(f"   👉 LLM requested tool: {tc.name}({args_summary})")

                exec_result = self.execute_tool_with_guardrails(tc.name, tc.arguments)

                # Record assistant tool call and tool result in conversation history
                conversation.append(Message(
                    role="assistant",
                    tool_calls=[tc],
                ))
                conversation.append(Message(
                    role="tool",
                    tool_call_id=tc.id,
                    content=exec_result,
                ))

        return "Agent execution reached max turns limit."
