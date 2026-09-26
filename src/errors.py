"""src/errors.py — Custom domain exception types for the Flight Booking MCP Server."""

from __future__ import annotations


class FlightBookingError(Exception):
    """Base exception for all Flight Booking domain errors."""


class BookingConflictError(FlightBookingError):
    """Raised when a seat or booking reference collision is detected."""


class BookingNotFoundError(FlightBookingError):
    """Raised when a booking reference does not exist in the database."""


class FlightNotFoundError(FlightBookingError):
    """Raised when a flight ID or flight number is not found."""


class SeatUnavailableError(FlightBookingError):
    """Raised when a seat is already occupied or held."""


class IdempotencyConflictError(FlightBookingError):
    """Raised when a duplicate request with the same idempotency key is detected."""


class PaymentDeclinedError(FlightBookingError):
    """Raised when a payment transaction is declined by the payment gateway."""
