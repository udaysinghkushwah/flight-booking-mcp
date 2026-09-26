"""src/server.py — Entry point: creates the MCPServer instance, registers all tools, resources, and prompts.

Production Flight Booking MCP Server running on AWS ECS Fargate.

Features:
- Full Model Context Protocol (Tools, Resources, Prompts)
- Streamable HTTP & SSE Transport (/mcp)
- Transport Security with DNS Rebinding Protection & Host Allowlists
- API Key & Bearer Token Authentication Middleware
- Fine-grained RBAC Capability Scopes (flight:read, flight:book, flight:admin, sql:readonly)
- Token-bucket Rate Limiting per Actor
- Safe Read-Only SQL Query Tool with AST Validation
- Real-time SLA Tracking & Audit Logging
- Observability: Liveness/Readiness (/health) & Prometheus Metrics (/metrics)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse

from src.config import settings
from src.db import init_db
from src.middleware.auth import AuthenticationMiddleware
from src.prompts.itinerary_prompts import (
    get_disruption_advisor_prompt,
    get_itinerary_assistant_prompt,
)
from src.resources import (
    get_airport_resource,
    get_analytics_summary_resource,
    get_cancellation_policies_resource,
)
from src.telemetry import get_platform_health_report, get_prometheus_metrics
from src.tools.admin import get_audit_trail, query_flight_database
from src.tools.booking import (
    cancel_booking,
    create_booking,
    get_booking,
    modify_booking_seat,
)
from src.tools.search import check_seat_availability, get_flight_details, search_flights

# ─────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("flight-booking-mcp")

# ─────────────────────────────────────────────────────────────
# Bootstrap database
# ─────────────────────────────────────────────────────────────
init_db()

# ─────────────────────────────────────────────────────────────
# Create MCP Server instance
# ─────────────────────────────────────────────────────────────
mcp = MCPServer("flight-booking-mcp-server")


# ─────────────────────────────────────────────────────────────
# 1. TOOLS
# ─────────────────────────────────────────────────────────────

@mcp.tool()
def search_flights_tool(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure_date: Optional[str] = None,
    cabin_class: str = "ECONOMY",
    max_price: Optional[float] = None,
    direct_only: bool = True,
    limit: int = 10,
) -> Dict[str, Any]:
    """Search available flights with filtering on route, date, cabin class, and price."""
    return search_flights(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        cabin_class=cabin_class,
        max_price=max_price,
        direct_only=direct_only,
        limit=limit,
    )


@mcp.tool()
def get_flight_details_tool(flight_number_or_id: str) -> Dict[str, Any]:
    """Get full flight details, schedule, aircraft model, and airport weather."""
    return get_flight_details(flight_number_or_id=flight_number_or_id)


@mcp.tool()
def check_seat_availability_tool(flight_id: str, cabin_class: Optional[str] = None) -> Dict[str, Any]:
    """Check remaining seats and available seat numbers for a flight."""
    return check_seat_availability(flight_id=flight_id, cabin_class=cabin_class)


@mcp.tool()
def create_booking_tool(
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    passport_num: str,
    seat_number: str,
    cabin_class: str = "ECONOMY",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Atomically create a flight reservation and reserve a specific seat."""
    return create_booking(
        flight_id=flight_id,
        passenger_name=passenger_name,
        passenger_email=passenger_email,
        passport_num=passport_num,
        seat_number=seat_number,
        cabin_class=cabin_class,
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def get_booking_tool(booking_reference: str) -> Dict[str, Any]:
    """Retrieve booking details, passenger ticket, seat assignment, and flight status."""
    return get_booking(booking_reference=booking_reference)


@mcp.tool()
def cancel_booking_tool(
    booking_reference: str,
    reason: str = "Passenger voluntary cancellation",
) -> Dict[str, Any]:
    """Cancel a booking, release seat back to inventory, and calculate refund."""
    return cancel_booking(booking_reference=booking_reference, reason=reason)


@mcp.tool()
def modify_booking_seat_tool(booking_reference: str, new_seat_number: str) -> Dict[str, Any]:
    """Change the seat allocation for an active confirmed flight booking."""
    return modify_booking_seat(booking_reference=booking_reference, new_seat_number=new_seat_number)


@mcp.tool()
def get_audit_trail_tool(limit: int = 50, tool_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve compliance audit records, execution latencies, and SLA breach logs (Privileged)."""
    return get_audit_trail(limit=limit, tool_filter=tool_filter)


@mcp.tool()
def query_flight_database_tool(sql_query: str) -> Dict[str, Any]:
    """Execute a read-only SELECT SQL query against the flight database with AST safety verification."""
    return query_flight_database(sql_query=sql_query)


# ─────────────────────────────────────────────────────────────
# 2. RESOURCES
# ─────────────────────────────────────────────────────────────

@mcp.resource("flight://airports/{code}")
def airport_resource(code: str) -> str:
    """Real-time airport conditions, active runways, and scheduled flight counts."""
    return get_airport_resource(code)


@mcp.resource("flight://policies/cancellation")
def cancellation_policy_resource() -> str:
    """Official cancellation, refund rules, and baggage allowance policies."""
    return get_cancellation_policies_resource()


@mcp.resource("flight://analytics/daily-summary")
def analytics_summary_resource() -> str:
    """Daily booking analytics, total gross revenue, and flight seat occupancy rates."""
    return get_analytics_summary_resource()


# ─────────────────────────────────────────────────────────────
# 3. PROMPTS
# ─────────────────────────────────────────────────────────────

@mcp.prompt("flight_itinerary_assistant")
def itinerary_assistant_prompt(
    origin: str,
    destination: str,
    departure_date: str,
    max_budget: str = "any",
) -> str:
    """Assists passengers in searching flights, comparing cabin classes, and confirming bookings."""
    return get_itinerary_assistant_prompt(origin, destination, departure_date, max_budget)


@mcp.prompt("disruption_rebooking_advisor")
def disruption_advisor_prompt(
    flight_number: str,
    booking_reference: str,
    disruption_type: str = "DELAYED",
) -> str:
    """Handles flight disruptions, passenger compensation rights, and automated rebooking."""
    return get_disruption_advisor_prompt(flight_number, booking_reference, disruption_type)


# ─────────────────────────────────────────────────────────────
# 4. CUSTOM HTTP ROUTES (Health, Metrics, Index)
# ─────────────────────────────────────────────────────────────

@mcp.custom_route("/", methods=["GET"])
async def index_route(_: Request) -> JSONResponse:
    """Landing index documentation for the MCP server."""
    return JSONResponse({
        "service": "flight-booking-mcp-server",
        "version": "1.0.0",
        "description": "Production Model Context Protocol (MCP) Flight Booking Fleet on AWS ECS",
        "mcp_endpoint": "/mcp",
        "health_endpoint": "/health",
        "metrics_endpoint": "/metrics",
        "tools_available": [
            "search_flights_tool", "get_flight_details_tool", "check_seat_availability_tool",
            "create_booking_tool", "get_booking_tool", "cancel_booking_tool",
            "modify_booking_seat_tool", "get_audit_trail_tool", "query_flight_database_tool",
        ],
        "resources_available": [
            "flight://airports/{code}",
            "flight://policies/cancellation",
            "flight://analytics/daily-summary",
        ],
        "prompts_available": [
            "flight_itinerary_assistant",
            "disruption_rebooking_advisor",
        ],
        "authentication": "Bearer token or X-API-Key header required for /mcp requests.",
    })


@mcp.custom_route("/health", methods=["GET"])
async def health_route(_: Request) -> JSONResponse:
    """Detailed health check for load balancer and cluster monitors."""
    report = get_platform_health_report()
    status_code = 200 if report["status"] in ("HEALTHY", "DEGRADED") else 503
    return JSONResponse(report, status_code=status_code)


@mcp.custom_route("/metrics", methods=["GET"])
async def metrics_route(_: Request) -> PlainTextResponse:
    """Prometheus exposition metrics endpoint."""
    return PlainTextResponse(
        get_prometheus_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# ─────────────────────────────────────────────────────────────
# 5. CONFIGURE TRANSPORT SECURITY & BUILD APP
# ─────────────────────────────────────────────────────────────

security = TransportSecuritySettings(
    enable_dns_rebinding_protection=not settings.disable_dns_rebinding,
    allowed_hosts=settings.allowed_hosts,
    allowed_origins=settings.allowed_origins,
)

stateless_http = os.getenv("MCP_STATELESS_HTTP", "true").lower() in ("true", "1", "yes")

app = mcp.streamable_http_app(
    streamable_http_path="/mcp",
    json_response=True,
    stateless_http=stateless_http,
    transport_security=security,
    host=settings.host,
)

app.add_middleware(AuthenticationMiddleware)

logger.info(
    f"Flight Booking MCP Server initialized (DNS rebinding check: {not settings.disable_dns_rebinding}, "
    f"Allowed hosts: {settings.allowed_hosts})"
)
