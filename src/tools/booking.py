"""src/tools/booking.py — Reservation create, retrieve, cancel, and seat-modify tools."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.db.session import (
    cancel_booking_atomic,
    create_booking_atomic,
    get_booking_db,
    modify_booking_seat_atomic,
)
from src.middleware.rbac import CapabilityScope, guarded_tool


@guarded_tool(required_scope=CapabilityScope.FLIGHT_BOOK, sla_threshold_ms=300.0)
def create_booking(
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    passport_num: str,
    seat_number: str,
    cabin_class: str = "ECONOMY",
    idempotency_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Atomically create a flight reservation and reserve a specific seat.

    Args:
        flight_id: Internal flight ID to book (e.g. 'FL-101').
        passenger_name: Full legal passenger name as on government ID.
        passenger_email: Contact email for confirmation ticket.
        passport_num: Passenger passport number.
        seat_number: Specific seat number to assign (e.g. '15A', '5B', '1A').
        cabin_class: Cabin class tier ('ECONOMY', 'BUSINESS', 'FIRST').
        idempotency_key: Unique client request identifier to guarantee safe retries.
    """
    if not flight_id:
        raise ValueError("flight_id is required.")
    if not passenger_name or len(passenger_name.strip()) < 2:
        raise ValueError("Valid passenger_name is required.")
    if not passenger_email or "@" not in passenger_email:
        raise ValueError("Valid passenger_email is required.")
    if not passport_num or len(passport_num.strip()) < 5:
        raise ValueError("Valid passport_num is required.")
    if not seat_number:
        raise ValueError("seat_number is required.")

    return create_booking_atomic(
        flight_id=flight_id.strip().upper(),
        passenger_name=passenger_name.strip(),
        passenger_email=passenger_email.strip().lower(),
        passport_num=passport_num.strip(),
        seat_number=seat_number.strip().upper(),
        cabin_class=cabin_class.strip().upper(),
        idempotency_key=idempotency_key.strip() if idempotency_key else None,
    )


@guarded_tool(required_scope=CapabilityScope.FLIGHT_READ, sla_threshold_ms=150.0)
def get_booking(booking_reference: str) -> Dict[str, Any]:
    """Retrieve booking details, passenger ticket, seat assignment, and flight status.

    Args:
        booking_reference: Unique 6-character booking code (e.g. 'BK-7F9A1').
    """
    if not booking_reference:
        raise ValueError("booking_reference is required.")
    booking = get_booking_db(booking_reference.strip().upper())
    if not booking:
        return {"error": f"Booking '{booking_reference}' not found."}
    return booking


@guarded_tool(required_scope=CapabilityScope.FLIGHT_BOOK, sla_threshold_ms=300.0)
def cancel_booking(
    booking_reference: str,
    reason: str = "Passenger voluntary cancellation",
) -> Dict[str, Any]:
    """Cancel a booking, release seat back to inventory, and calculate refund.

    Args:
        booking_reference: Unique booking code to cancel (e.g. 'BK-7F9A1').
        reason: Justification for ticket cancellation.
    """
    if not booking_reference:
        raise ValueError("booking_reference is required.")
    return cancel_booking_atomic(booking_reference.strip().upper(), reason=reason)


@guarded_tool(required_scope=CapabilityScope.FLIGHT_BOOK, sla_threshold_ms=250.0)
def modify_booking_seat(booking_reference: str, new_seat_number: str) -> Dict[str, Any]:
    """Change the seat allocation for an active confirmed flight booking.

    Args:
        booking_reference: Booking code to update (e.g. 'BK-7F9A1').
        new_seat_number: Target seat number to switch to (e.g. '16B').
    """
    if not booking_reference:
        raise ValueError("booking_reference is required.")
    if not new_seat_number:
        raise ValueError("new_seat_number is required.")
    return modify_booking_seat_atomic(
        booking_reference.strip().upper(),
        new_seat_number.strip().upper(),
    )
