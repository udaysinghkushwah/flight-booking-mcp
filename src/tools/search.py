"""src/tools/search.py — Flight search and lookup tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.db.session import (
    check_seat_availability_db,
    get_flight_details_db,
    search_flights_db,
)
from src.middleware.rbac import CapabilityScope, guarded_tool


@guarded_tool(required_scope=CapabilityScope.FLIGHT_READ, sla_threshold_ms=250.0)
def search_flights(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure_date: Optional[str] = None,
    cabin_class: str = "ECONOMY",
    max_price: Optional[float] = None,
    direct_only: bool = True,
    limit: int = 10,
) -> Dict[str, Any]:
    """Search available flights with filtering on route, date, cabin class, and price.

    Args:
        origin: 3-letter IATA origin airport code (e.g. 'JFK', 'LHR', 'SFO').
        destination: 3-letter IATA destination airport code (e.g. 'DXB', 'HND').
        departure_date: Date formatted as YYYY-MM-DD (e.g. '2026-09-28').
        cabin_class: Cabin tier ('ECONOMY', 'BUSINESS', or 'FIRST'). Defaults to 'ECONOMY'.
        max_price: Optional maximum price threshold for the selected cabin class.
        direct_only: Whether to restrict to direct non-stop flights. Defaults to True.
        limit: Maximum number of flights to return (max 25).
    """
    if origin and len(origin.strip()) != 3:
        raise ValueError(f"Origin code '{origin}' must be a 3-letter IATA airport code.")
    if destination and len(destination.strip()) != 3:
        raise ValueError(f"Destination code '{destination}' must be a 3-letter IATA airport code.")

    clamped_limit = max(1, min(limit, 25))
    flights = search_flights_db(
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        cabin_class=cabin_class,
        max_price=max_price,
        direct_only=direct_only,
        limit=clamped_limit,
    )
    return {
        "count": len(flights),
        "search_filters": {
            "origin": origin,
            "destination": destination,
            "departure_date": departure_date,
            "cabin_class": cabin_class.upper(),
            "max_price": max_price,
        },
        "flights": flights,
    }


@guarded_tool(required_scope=CapabilityScope.FLIGHT_READ, sla_threshold_ms=150.0)
def get_flight_details(flight_number_or_id: str) -> Dict[str, Any]:
    """Get full flight details, schedule, aircraft model, and airport weather.

    Args:
        flight_number_or_id: Flight number (e.g. 'BA-178') or internal flight ID (e.g. 'FL-101').
    """
    if not flight_number_or_id:
        raise ValueError("Flight number or ID is required.")
    details = get_flight_details_db(flight_number_or_id.strip())
    if not details:
        return {"error": f"Flight '{flight_number_or_id}' not found."}
    return details


@guarded_tool(required_scope=CapabilityScope.FLIGHT_READ, sla_threshold_ms=200.0)
def check_seat_availability(flight_id: str, cabin_class: Optional[str] = None) -> Dict[str, Any]:
    """Check remaining seats and available seat numbers for a flight.

    Args:
        flight_id: Internal flight ID (e.g. 'FL-101', 'FL-201').
        cabin_class: Optional filter for cabin class ('ECONOMY', 'BUSINESS', 'FIRST').
    """
    if not flight_id:
        raise ValueError("flight_id is required.")
    return check_seat_availability_db(flight_id.strip().upper(), cabin_class)
