"""Production HTTP client for Model Context Protocol (JSON-RPC 2.0)."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from agent.models import ToolDefinition

try:
    import truststore
    truststore.inject_into_ssl()
    SSL_CONTEXT = ssl.create_default_context()
except Exception:
    SSL_CONTEXT = ssl._create_unverified_context()

logger = logging.getLogger("agent.client")


class MCPClient:
    """Low-level JSON-RPC 2.0 client for interacting with an MCP server."""

    def __init__(self, base_url: str, api_key: str, timeout_sec: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.endpoint = f"{self.base_url}/mcp"
        self.api_key = api_key
        self.timeout_sec = timeout_sec
        self.session_id: Optional[str] = None
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def call_rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a JSON-RPC 2.0 request to the MCP server."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        if self.session_id:
            req.add_header("mcp-session-id", self.session_id)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec, context=SSL_CONTEXT) as resp:
                new_session = resp.headers.get("mcp-session-id")
                if new_session:
                    self.session_id = new_session
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8")
            logger.error(f"MCP RPC HTTP {err.code}: {err_body}")
            raise RuntimeError(f"MCP HTTP Error {err.code}: {err_body}")
        except Exception as e:
            logger.error(f"Network error contacting MCP endpoint {self.endpoint}: {e}")
            raise RuntimeError(f"MCP Network Connection Failed to {self.endpoint}: {e}")

    def initialize(self) -> Dict[str, Any]:
        """Handshake with MCP server and establish session capabilities."""
        res = self.call_rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"roots": {"listChanged": True}},
            "clientInfo": {"name": "production-flight-agent", "version": "1.0.0"},
        })
        return res.get("result", {})

    def list_tools(self) -> List[ToolDefinition]:
        """Query available tools and return typed ToolDefinition models."""
        res = self.call_rpc("tools/list", {})
        raw_tools = res.get("result", {}).get("tools", [])
        return [
            ToolDefinition(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {}),
            )
            for t in raw_tools
        ]

    def list_resources(self) -> List[Dict[str, Any]]:
        """Query available data resources."""
        res = self.call_rpc("resources/list", {})
        return res.get("result", {}).get("resources", [])

    def read_resource(self, uri: str) -> str:
        """Fetch content of an MCP resource by URI."""
        res = self.call_rpc("resources/read", {"uri": uri})
        contents = res.get("result", {}).get("contents", [])
        if contents and "text" in contents[0]:
            return contents[0]["text"]
        return ""

    def list_prompts(self) -> List[Dict[str, Any]]:
        """Query available prompt templates."""
        res = self.call_rpc("prompts/list", {})
        return res.get("result", {}).get("prompts", [])

    def get_prompt(self, name: str, arguments: Optional[Dict[str, str]] = None) -> str:
        """Retrieve rendered prompt template text."""
        res = self.call_rpc("prompts/get", {"name": name, "arguments": arguments or {}})
        messages = res.get("result", {}).get("messages", [])
        if messages and "content" in messages[0] and "text" in messages[0]["content"]:
            return messages[0]["content"]["text"]
        return ""

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool on the MCP server and parse the output."""
        res = self.call_rpc("tools/call", {"name": name, "arguments": arguments})
        if "error" in res:
            return {"error": res["error"], "isError": True}

        raw = res.get("result", {})
        if "structuredContent" in raw and "result" in raw["structuredContent"]:
            return raw["structuredContent"]["result"]

        if "content" in raw and raw["content"] and "text" in raw["content"][0]:
            try:
                return json.loads(raw["content"][0]["text"])
            except Exception:
                return {"text": raw["content"][0]["text"]}

        return raw
