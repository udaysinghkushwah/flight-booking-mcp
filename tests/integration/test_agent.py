"""Unit tests for Production MCP Agent."""

import json
import unittest
from unittest.mock import MagicMock, patch

from agent import MCPClient, ProductionFlightAgent


class TestProductionAgent(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=MCPClient)
        self.mock_client.base_url = "https://mock-mcp.internal"
        self.mock_client.initialize.return_value = {
            "serverInfo": {"name": "flight-booking-mcp-server", "version": "1.0.0"}
        }
        self.mock_client.list_tools.return_value = [
            {
                "name": "search_flights_tool",
                "description": "Search available flights",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "origin": {"type": "string"},
                        "destination": {"type": "string"},
                    },
                    "required": ["origin", "destination"],
                },
            },
            {
                "name": "create_booking_tool",
                "description": "Atomically book a flight",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "flight_id": {"type": "string"},
                        "seat_number": {"type": "string"},
                    },
                    "required": ["flight_id", "seat_number"],
                },
            },
        ]
        self.mock_client.list_prompts.return_value = [
            {"name": "flight_itinerary_assistant"}
        ]
        self.mock_client.get_prompt.return_value = "You are a flight travel agent."

    def test_bootstrap_and_schema_conversion(self):
        agent = ProductionFlightAgent(self.mock_client, backend="cognitive_builtin", auto_approve=True)
        agent.bootstrap()

        self.assertEqual(len(agent.tools), 2)
        openai_tools = agent.convert_mcp_to_openai_tools()
        self.assertEqual(len(openai_tools), 2)
        self.assertEqual(openai_tools[0]["type"], "function")
        self.assertEqual(openai_tools[0]["function"]["name"], "search_flights_tool")
        self.assertIn("origin", openai_tools[0]["function"]["parameters"]["properties"])

    def test_hitl_safety_gate_auto_approve(self):
        agent = ProductionFlightAgent(self.mock_client, auto_approve=True)
        # Mutating tool with auto-approve should pass
        allowed = agent.check_human_in_the_loop_gate(
            "create_booking_tool",
            {"flight_id": "FL-101", "seat_number": "15B"},
        )
        self.assertTrue(allowed)

        # Read tool should always pass without prompt
        read_allowed = agent.check_human_in_the_loop_gate(
            "search_flights_tool",
            {"origin": "JFK", "destination": "LHR"},
        )
        self.assertTrue(read_allowed)

    def test_hitl_safety_gate_manual_rejection(self):
        agent = ProductionFlightAgent(self.mock_client, auto_approve=False)
        with patch("builtins.input", return_value="n"):
            allowed = agent.check_human_in_the_loop_gate(
                "create_booking_tool",
                {"flight_id": "FL-101", "seat_number": "15B"},
            )
            self.assertFalse(allowed)

    def test_run_agentic_loop_with_cognitive_engine(self):
        agent = ProductionFlightAgent(self.mock_client, backend="cognitive_builtin", auto_approve=True)
        agent.bootstrap()

        # Mock tool responses for the 3 steps
        self.mock_client.call_tool.side_effect = [
            # Turn 1 response: search results
            {
                "count": 1,
                "flights": [
                    {
                        "flight_id": "FL-101",
                        "flight_number": "BA-178",
                        "price": 540.0,
                    }
                ],
            },
            # Turn 2 response: seat availability
            {
                "flight_id": "FL-101",
                "available_seats": ["15B", "16A"],
            },
            # Turn 3 response: booking result
            {
                "booking_reference": "BK-TEST99",
                "flight_number": "BA-178",
                "origin": "JFK",
                "destination": "LHR",
                "seat_number": "15B",
                "total_price": 540.0,
                "passenger_name": "Dr. Robert McCall",
                "status": "CONFIRMED",
            },
        ]

        result = agent.run("Find an economy flight from JFK to LHR on 2026-09-28 and book for Dr. Robert McCall")
        self.assertIn("Flight Booking Confirmed", result)
        self.assertIn("BK-TEST99", result)
        self.assertIn("BA-178", result)
        self.assertEqual(self.mock_client.call_tool.call_count, 3)


if __name__ == "__main__":
    unittest.main()
