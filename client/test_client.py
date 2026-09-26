"""client/test_client.py — Reference MCP client for testing and development."""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request

try:
    import truststore
    truststore.inject_into_ssl()
    SSL_CONTEXT = ssl.create_default_context()
except Exception:
    SSL_CONTEXT = ssl._create_unverified_context()

BASE_URL = os.getenv("MCP_URL", "https://my-62557ba230744e00bfa6dee1bce8609e.ecs.us-east-1.on.aws")
API_KEY = os.getenv("MCP_API_KEY", "flight-agent-key-secret")


def post_mcp(payload: dict, session_id: str | None = None) -> tuple[dict, str | None]:
    url = f"{BASE_URL}/mcp"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", f"Bearer {API_KEY}")
    if session_id:
        req.add_header("mcp-session-id", session_id)

    try:
        with urllib.request.urlopen(req, timeout=15, context=SSL_CONTEXT) as resp:
            new_session_id = resp.headers.get("mcp-session-id") or session_id
            body = resp.read().decode("utf-8")
            return json.loads(body), new_session_id
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        print(f"\n[HTTP ERROR {err.code}] {body}")
        raise


def main():
    print(f"Connecting to: {BASE_URL}/mcp")

    # tools/list
    res, _ = post_mcp({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    tools = res["result"]["tools"]
    print(f"\nAvailable tools ({len(tools)}):")
    for t in tools:
        print(f"  • {t['name']}: {t.get('description', '')[:60]}...")

    # search_flights_tool
    res, _ = post_mcp({
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {
            "name": "search_flights_tool",
            "arguments": {"origin": "JFK", "destination": "LHR", "departure_date": "2026-09-28"},
        },
    })
    print("\nFlight search result keys:", list(res.get("result", {}).get("structuredContent", {}).get("result", {}).keys()))
    print("\nClient test complete ✓")


if __name__ == "__main__":
    main()
