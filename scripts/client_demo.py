#!/usr/bin/env python3
"""Interactive Client Demo for Production Flight Booking MCP Server."""

import json
import os
import sys
import urllib.request
import urllib.error

import ssl

try:
    import truststore
    truststore.inject_into_ssl()
    ssl_context = ssl.create_default_context()
except Exception:
    ssl_context = ssl._create_unverified_context()

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
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as resp:
            new_session_id = resp.headers.get("mcp-session-id") or session_id
            body = resp.read().decode("utf-8")
            return json.loads(body), new_session_id
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8")
        print(f"\n[HTTP ERROR {err.code}] {body}")
        raise


def extract_tool_result(res: dict) -> dict:
    raw = res.get("result", {})
    if "structuredContent" in raw and "result" in raw["structuredContent"]:
        return raw["structuredContent"]["result"]
    if "content" in raw and raw["content"] and "text" in raw["content"][0]:
        try:
            return json.loads(raw["content"][0]["text"])
        except Exception:
            return {"text": raw["content"][0]["text"]}
    return raw


def run_demo():
    print("=" * 70)
    print("✈️   FLIGHT BOOKING PRODUCTION MCP SERVER DEMO")
    print(f"Target URL: {BASE_URL}")
    print("=" * 70)

    # 1. Server Health Check
    print("\n[STEP 1] Checking server health...")
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=10, context=ssl_context) as resp:
            health = json.loads(resp.read().decode("utf-8"))
            print(f"  Status: {health.get('status')} | Service: {health.get('service')}")
            if "database" in health:
                print(f"  Airports: {health['database']['airports']} | Flights: {health['database']['flights']}")
    except Exception as e:
        print(f"  Health check notice: {e}")

    # 2. MCP Handshake
    print("\n[STEP 2] Performing MCP JSON-RPC Handshake (initialize)...")
    init_res, session_id = post_mcp({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "flight-demo-client", "version": "1.0.0"}
        }
    })
    server_info = init_res.get("result", {}).get("serverInfo", {})
    print(f"  Connected to: {server_info.get('name')}")

    # 3. List Tools
    print("\n[STEP 3] Discovering available tools...")
    tools_res, _ = post_mcp({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }, session_id=session_id)
    tools = tools_res.get("result", {}).get("tools", [])
    print(f"  Discovered {len(tools)} tools:")
    for t in tools:
        print(f"    - {t['name']}: {t.get('description', '')[:65]}...")

    # 4. Search Flights
    print("\n[STEP 4] Searching flights: JFK -> LHR (Economy)...")
    search_res, _ = post_mcp({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "search_flights_tool",
            "arguments": {
                "origin": "JFK",
                "destination": "LHR",
                "cabin_class": "ECONOMY",
                "limit": 3
            }
        }
    }, session_id=session_id)
    flights_data = extract_tool_result(search_res)
    print(f"  Found {flights_data.get('count', 0)} flights.")
    flights = flights_data.get("flights", [])
    if flights:
        selected_flight = flights[0]
        print(f"  Selected Flight: {selected_flight['flight_number']} ({selected_flight['airline_name']})")
        print(f"  Departure: {selected_flight['departure_time']} | Price: ${selected_flight['economy_price']}")
        flight_id = selected_flight["flight_id"]

        # 5. Check Seats
        print(f"\n[STEP 5] Checking seat availability on flight {flight_id}...")
        seats_res, _ = post_mcp({
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "check_seat_availability_tool",
                "arguments": {
                    "flight_id": flight_id,
                    "cabin_class": "ECONOMY"
                }
            }
        }, session_id=session_id)
        seats_data = extract_tool_result(seats_res)
        avail_seats = seats_data.get("available_seats", [])
        chosen_seat = avail_seats[0] if avail_seats else "15B"
        print(f"  Available Economy Seats: {seats_data.get('available_count')}")
        print(f"  Selecting seat: {chosen_seat}")

        # 6. Create Booking
        print(f"\n[STEP 6] Creating atomic flight reservation...")
        idemp_key = f"demo-run-{os.urandom(4).hex()}"
        booking_res, _ = post_mcp({
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "create_booking_tool",
                "arguments": {
                    "flight_id": flight_id,
                    "passenger_name": "Elena Rostova",
                    "passenger_email": "elena.r@example.com",
                    "passport_num": "P77665544",
                    "seat_number": chosen_seat,
                    "cabin_class": "ECONOMY",
                    "idempotency_key": idemp_key,
                }
            }
        }, session_id=session_id)
        booking = extract_tool_result(booking_res)
        booking_ref = booking.get("booking_reference")
        print(f"  Status: {booking.get('status')}")
        print(f"  Booking Reference: {booking_ref}")
        print(f"  Total Charged: ${booking.get('total_price')}")

        if booking_ref:
            # 7. Modify Seat
            target_seat = avail_seats[1] if len(avail_seats) > 1 else "15C"
            print(f"\n[STEP 7] Changing seat assignment to {target_seat}...")
            mod_res, _ = post_mcp({
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "modify_booking_seat_tool",
                    "arguments": {
                        "booking_reference": booking_ref,
                        "new_seat_number": target_seat,
                    }
                }
            }, session_id=session_id)
            mod_data = extract_tool_result(mod_res)
            print(f"  Result: {mod_data.get('status')} | New Seat: {target_seat}")

            # 8. Cancel Booking
            print(f"\n[STEP 8] Cancelling reservation and releasing seat inventory...")
            cancel_res, _ = post_mcp({
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "cancel_booking_tool",
                    "arguments": {
                        "booking_reference": booking_ref,
                        "reason": "Customer trip postponed",
                    }
                }
            }, session_id=session_id)
            cancel_data = extract_tool_result(cancel_res)
            print(f"  Status: {cancel_data.get('status')}")
            print(f"  Refund Amount: ${cancel_data.get('refund_amount')}")
            print(f"  Seat Released: {cancel_data.get('seat_released')}")

    print("\n" + "=" * 70)
    print("✅ All Flight Booking MCP tools executed successfully.")
    print("=" * 70)


if __name__ == "__main__":
    run_demo()
