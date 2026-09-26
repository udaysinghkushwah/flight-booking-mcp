"""Integration tests for Server HTTP endpoints."""

import unittest
from starlette.testclient import TestClient

from src.server import app


class TestServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._client_cm = TestClient(app)
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls._client_cm.__exit__(None, None, None)

    def test_index_endpoint(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["service"], "flight-booking-mcp-server")
        self.assertIn("search_flights_tool", data["tools_available"])

    def test_health_endpoint(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["status"], ("HEALTHY", "DEGRADED"))
        self.assertTrue(data["database"]["database_connected"])

    def test_metrics_endpoint(self):
        res = self.client.get("/metrics")
        self.assertEqual(res.status_code, 200)
        self.assertIn("flight_mcp_uptime_seconds", res.text)
        self.assertIn("flight_mcp_database_connected", res.text)

    def test_mcp_auth_rejection_without_key(self):
        # When auth is enabled, missing API key returns 401
        res = self.client.post("/mcp", json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}
        })
        self.assertEqual(res.status_code, 401)

    def test_mcp_auth_with_valid_key(self):
        # Using configured test API key
        headers = {
            "Authorization": "Bearer flight-agent-key-secret",
            "Content-Type": "application/json",
        }
        res = self.client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "test", "version": "1.0"}}
            }
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["result"]["serverInfo"]["name"], "flight-booking-mcp-server")


if __name__ == "__main__":
    unittest.main()
