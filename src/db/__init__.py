"""src/db package — database engine, session management, and ORM-style helpers."""

from src.db.session import (
    get_connection,
    init_db,
    search_flights_db,
    get_flight_details_db,
    check_seat_availability_db,
    create_booking_atomic,
    get_booking_db,
    cancel_booking_atomic,
    modify_booking_seat_atomic,
    execute_readonly_query,
    record_audit,
    fetch_audit_logs,
    get_db_stats,
)

__all__ = [
    "get_connection",
    "init_db",
    "search_flights_db",
    "get_flight_details_db",
    "check_seat_availability_db",
    "create_booking_atomic",
    "get_booking_db",
    "cancel_booking_atomic",
    "modify_booking_seat_atomic",
    "execute_readonly_query",
    "record_audit",
    "fetch_audit_logs",
    "get_db_stats",
]
