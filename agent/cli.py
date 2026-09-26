"""Command Line Interface for the Production MCP AI Agent."""

from __future__ import annotations

import argparse
import os

from agent.client import MCPClient
from agent.orchestrator import ProductionFlightAgent

DEFAULT_MCP_URL = os.getenv("MCP_URL", "https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws")
DEFAULT_API_KEY = os.getenv("MCP_API_KEY", "flight-agent-key-secret")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent",
        description="Production Autonomous AI Flight Booking Agent for MCP",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_MCP_URL,
        help="MCP Server Base URL (default: AWS ECS live endpoint)",
    )
    parser.add_argument(
        "--api-key",
        default=DEFAULT_API_KEY,
        help="MCP Bearer token / API Key (default: flight-agent-key-secret)",
    )
    parser.add_argument(
        "--backend",
        default="auto",
        choices=["auto", "openai", "anthropic", "openai_compatible", "cognitive_builtin"],
        help="LLM provider backend (default: auto-detect from environment)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Specific model name (e.g. gpt-4o, claude-3-5-sonnet-20241022)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve mutating operations without interactive HITL prompt",
    )
    parser.add_argument(
        "--prompt",
        default="Find me an economy flight from JFK to LHR on 2026-09-28 and book a seat for Dr. Robert McCall (passport: P88776655, email: robert.mccall@equalizer.org).",
        help="Passenger natural language booking request",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    client = MCPClient(base_url=args.url, api_key=args.api_key)
    agent = ProductionFlightAgent(
        mcp_client=client,
        backend=args.backend,
        model=args.model,
        auto_approve=args.auto_approve,
    )

    agent.bootstrap()
    agent.run(args.prompt)


if __name__ == "__main__":
    main()
