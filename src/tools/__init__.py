"""src/tools/__init__.py — Registers all tools with the MCP server instance."""

from src.tools.admin import get_audit_trail, query_flight_database
from src.tools.booking import (
    cancel_booking,
    create_booking,
    get_booking,
    modify_booking_seat,
)
from src.tools.search import check_seat_availability, get_flight_details, search_flights

__all__ = [
    # Search & Lookup
    "search_flights",
    "get_flight_details",
    "check_seat_availability",
    # Reservation Management
    "create_booking",
    "get_booking",
    "cancel_booking",
    "modify_booking_seat",
    # Privileged Admin
    "get_audit_trail",
    "query_flight_database",
]
