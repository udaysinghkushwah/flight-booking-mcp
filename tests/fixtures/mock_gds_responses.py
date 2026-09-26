"""tests/fixtures/mock_gds_responses.py — Shared mock data fixtures for test suites."""

from __future__ import annotations

from typing import Any, Dict, List

MOCK_FLIGHT_SEARCH_RESPONSE: Dict[str, Any] = {
    "count": 2,
    "search_filters": {
        "origin": "JFK",
        "destination": "LHR",
        "departure_date": "2026-09-28",
        "cabin_class": "ECONOMY",
        "max_price": None,
    },
    "flights": [
        {
            "flight_id": "FL-101",
            "flight_number": "BA-178",
            "airline_code": "BA",
            "airline_name": "British Airways",
            "origin": "JFK",
            "destination": "LHR",
            "departure_time": "2026-09-28T08:00:00Z",
            "arrival_time": "2026-09-28T20:00:00Z",
            "aircraft_model": "Boeing 787-9",
            "status": "SCHEDULED",
            "price": 650.0,
            "available_seats": 120,
        },
    ],
}

MOCK_SEAT_AVAILABILITY_RESPONSE: Dict[str, Any] = {
    "flight_id": "FL-101",
    "flight_number": "BA-178",
    "aircraft_model": "Boeing 787-9",
    "total_queried": 156,
    "available_count": 154,
    "available_seats": ["15A", "15B", "15C", "16A", "16B"],
}

MOCK_BOOKING_CONFIRMATION_RESPONSE: Dict[str, Any] = {
    "status": "CONFIRMED",
    "booking_reference": "BK-TEST99",
    "flight_id": "FL-101",
    "flight_number": "BA-178",
    "passenger_name": "Dr. Robert McCall",
    "passenger_email": "robert.mccall@equalizer.org",
    "seat_number": "15B",
    "cabin_class": "ECONOMY",
    "total_price": 650.0,
    "origin": "JFK",
    "destination": "LHR",
    "created_at": "2026-09-27T20:00:00Z",
}

MOCK_GDS_API_ERROR: Dict[str, Any] = {
    "error": "GDS_TIMEOUT",
    "message": "Upstream GDS availability service timed out after 5000ms.",
    "retry_after_seconds": 10,
}
