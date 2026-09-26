"""MCP Resources for Flight Booking Server."""

from __future__ import annotations

import json
from typing import Any, Dict

from src.db.session import get_connection


def get_airport_resource(airport_code: str) -> str:
    """Returns airport conditions, active runways, and scheduled flight counts."""
    code = airport_code.strip().upper()
    conn = get_connection()
    try:
        airport = conn.execute("SELECT * FROM airports WHERE code = ?", (code,)).fetchone()
        if not airport:
            return json.dumps({"error": f"Airport code '{code}' not found."})

        flights_out = conn.execute("SELECT COUNT(*) FROM flights WHERE origin = ?", (code,)).fetchone()[0]
        flights_in = conn.execute("SELECT COUNT(*) FROM flights WHERE destination = ?", (code,)).fetchone()[0]

        data = dict(airport)
        data["departures_count"] = flights_out
        data["arrivals_count"] = flights_in
        return json.dumps(data, indent=2)
    finally:
        conn.close()


def get_cancellation_policies_resource() -> str:
    """Returns official cancellation and baggage allowance policies."""
    policies = {
        "cancellation_policy": {
            "risk_free_cancellation_hours": 24,
            "refund_rules": [
                {
                    "cabin": "FIRST",
                    "cancellation_fee_percent": 0.0,
                    "notice_hours_before_departure": 2,
                    "refund_type": "FULL_ORIGINAL_PAYMENT",
                },
                {
                    "cabin": "BUSINESS",
                    "cancellation_fee_percent": 5.0,
                    "notice_hours_before_departure": 6,
                    "refund_type": "ORIGINAL_PAYMENT_MINUS_FEE",
                },
                {
                    "cabin": "ECONOMY",
                    "cancellation_fee_percent": 15.0,
                    "notice_hours_before_departure": 24,
                    "refund_type": "ORIGINAL_PAYMENT_MINUS_FEE",
                },
            ],
            "weather_or_airline_cancellation": "100% full cash refund or complimentary alternative rebooking within 48 hours."
        },
        "baggage_allowance": {
            "FIRST": {"carry_on": "2 x 10kg", "checked": "3 x 32kg bags included"},
            "BUSINESS": {"carry_on": "2 x 10kg", "checked": "2 x 32kg bags included"},
            "ECONOMY": {"carry_on": "1 x 8kg", "checked": "1 x 23kg bag included"},
        },
        "check_in_window": {
            "online_opens_hours_before": 24,
            "counter_closes_minutes_before_intl": 60,
            "boarding_gate_closes_minutes_before": 20,
        },
    }
    return json.dumps(policies, indent=2)


def get_analytics_summary_resource() -> str:
    """Returns booking analytics, revenue totals, and seat occupancy."""
    conn = get_connection()
    try:
        total_bookings = conn.execute("SELECT COUNT(*) FROM bookings").fetchone()[0]
        confirmed_bookings = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'CONFIRMED'").fetchone()[0]
        total_revenue = conn.execute("SELECT COALESCE(SUM(total_price), 0.0) FROM bookings WHERE status = 'CONFIRMED'").fetchone()[0]
        
        # Flight occupancy rates
        flights = conn.execute(
            """
            SELECT flight_number, origin, destination,
                   (total_economy_seats + total_business_seats + total_first_seats) AS total_capacity,
                   ((total_economy_seats - available_economy) + (total_business_seats - available_business) + (total_first_seats - available_first)) AS booked_seats
            FROM flights
            ORDER BY booked_seats DESC
            """
        ).fetchall()

        summary = {
            "total_bookings_lifetime": total_bookings,
            "active_confirmed_bookings": confirmed_bookings,
            "gross_booking_revenue_usd": round(total_revenue, 2),
            "flights_occupancy": [
                {
                    "flight_number": f["flight_number"],
                    "route": f"{f['origin']} -> {f['destination']}",
                    "capacity": f["total_capacity"],
                    "booked": f["booked_seats"],
                    "load_factor_percent": round((f["booked_seats"] / f["total_capacity"]) * 100, 1) if f["total_capacity"] > 0 else 0.0,
                }
                for f in flights[:10]
            ],
        }
        return json.dumps(summary, indent=2)
    finally:
        conn.close()
