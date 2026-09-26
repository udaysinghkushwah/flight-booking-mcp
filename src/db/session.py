"""Persistent SQLite Database Layer for Flight Booking MCP Server."""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from src.config import settings


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or settings.db_path
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initializes tables and seeds initial flight data if empty."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS airports (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT NOT NULL,
                country TEXT NOT NULL,
                timezone TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                weather_condition TEXT NOT NULL DEFAULT 'CLEAR',
                active_runways INTEGER NOT NULL DEFAULT 2
            );

            CREATE TABLE IF NOT EXISTS airlines (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                country TEXT NOT NULL,
                rating REAL NOT NULL DEFAULT 4.5,
                fleet_size INTEGER NOT NULL DEFAULT 100
            );

            CREATE TABLE IF NOT EXISTS flights (
                flight_id TEXT PRIMARY KEY,
                flight_number TEXT NOT NULL,
                airline_code TEXT NOT NULL REFERENCES airlines(code),
                origin TEXT NOT NULL REFERENCES airports(code),
                destination TEXT NOT NULL REFERENCES airports(code),
                departure_time TEXT NOT NULL,
                arrival_time TEXT NOT NULL,
                aircraft_model TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'SCHEDULED',
                economy_price REAL NOT NULL,
                business_price REAL NOT NULL,
                first_price REAL NOT NULL,
                total_economy_seats INTEGER NOT NULL,
                total_business_seats INTEGER NOT NULL,
                total_first_seats INTEGER NOT NULL,
                available_economy INTEGER NOT NULL,
                available_business INTEGER NOT NULL,
                available_first INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seats (
                flight_id TEXT NOT NULL REFERENCES flights(flight_id) ON DELETE CASCADE,
                seat_number TEXT NOT NULL,
                cabin_class TEXT NOT NULL,
                is_available INTEGER NOT NULL DEFAULT 1,
                passenger_name TEXT,
                PRIMARY KEY (flight_id, seat_number)
            );

            CREATE TABLE IF NOT EXISTS bookings (
                booking_reference TEXT PRIMARY KEY,
                flight_id TEXT NOT NULL REFERENCES flights(flight_id),
                passenger_name TEXT NOT NULL,
                passenger_email TEXT NOT NULL,
                passport_num TEXT NOT NULL,
                cabin_class TEXT NOT NULL,
                seat_number TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'CONFIRMED',
                idempotency_key TEXT UNIQUE,
                total_price REAL NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                capability_scope TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                parameters TEXT NOT NULL,
                execution_ms REAL NOT NULL,
                status TEXT NOT NULL,
                sla_breached INTEGER NOT NULL,
                details TEXT
            );

            CREATE TABLE IF NOT EXISTS api_keys (
                api_key TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                scopes TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                rate_limit_rpm INTEGER NOT NULL DEFAULT 120,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            """)

            # Seed if airports is empty
            count = conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
            if count == 0:
                _seed_initial_data(conn)
    finally:
        conn.close()


def _seed_initial_data(conn: sqlite3.Connection) -> None:
    # 1. Airports
    airports_data = [
        ("JFK", "John F. Kennedy International Airport", "New York", "USA", "America/New_York", "ACTIVE", "CLEAR, 21C", 4),
        ("LHR", "London Heathrow Airport", "London", "UK", "Europe/London", "ACTIVE", "PARTLY CLOUDY, 16C", 2),
        ("SFO", "San Francisco International Airport", "San Francisco", "USA", "America/Los_Angeles", "ACTIVE", "FOGGY, 15C", 4),
        ("DXB", "Dubai International Airport", "Dubai", "UAE", "Asia/Dubai", "ACTIVE", "SUNNY, 35C", 2),
        ("HND", "Tokyo Haneda Airport", "Tokyo", "Japan", "Asia/Tokyo", "ACTIVE", "CLEAR, 19C", 4),
        ("ORD", "O'Hare International Airport", "Chicago", "USA", "America/Chicago", "ACTIVE", "CLEAR, 18C", 8),
        ("CDG", "Charles de Gaulle Airport", "Paris", "France", "Europe/Paris", "ACTIVE", "LIGHT RAIN, 14C", 4),
        ("SIN", "Singapore Changi Airport", "Singapore", "Singapore", "Asia/Singapore", "ACTIVE", "HUMID, 30C", 3),
        ("FRA", "Frankfurt Airport", "Frankfurt", "Germany", "Europe/Berlin", "ACTIVE", "CLOUDY, 17C", 4),
        ("LAX", "Los Angeles International Airport", "Los Angeles", "USA", "America/Los_Angeles", "ACTIVE", "SUNNY, 24C", 4),
    ]
    conn.executemany(
        "INSERT INTO airports VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        airports_data
    )

    # 2. Airlines
    airlines_data = [
        ("BA", "British Airways", "UK", 4.6, 257),
        ("AA", "American Airlines", "USA", 4.3, 960),
        ("DL", "Delta Air Lines", "USA", 4.7, 980),
        ("EK", "Emirates", "UAE", 4.9, 260),
        ("NH", "All Nippon Airways", "Japan", 4.8, 215),
        ("LH", "Lufthansa", "Germany", 4.5, 280),
    ]
    conn.executemany(
        "INSERT INTO airlines VALUES (?, ?, ?, ?, ?)",
        airlines_data
    )

    # 3. Flights
    flights_data = [
        ("FL-101", "BA-178", "BA", "JFK", "LHR", "2026-09-28T08:00:00Z", "2026-09-28T20:00:00Z", "Boeing 787-9", "SCHEDULED", 650.0, 2400.0, 5200.0, 180, 36, 8, 178, 35, 8),
        ("FL-102", "AA-100", "AA", "JFK", "LHR", "2026-09-28T18:30:00Z", "2026-09-29T06:30:00Z", "Boeing 777-300ER", "SCHEDULED", 620.0, 2250.0, 4900.0, 210, 40, 8, 209, 39, 7),
        ("FL-103", "BA-179", "BA", "LHR", "JFK", "2026-09-29T10:00:00Z", "2026-09-29T13:00:00Z", "Boeing 787-9", "SCHEDULED", 670.0, 2450.0, 5300.0, 180, 36, 8, 180, 36, 8),
        ("FL-201", "EK-202", "EK", "JFK", "DXB", "2026-09-28T23:00:00Z", "2026-09-29T19:30:00Z", "Airbus A380-800", "SCHEDULED", 920.0, 3800.0, 8500.0, 399, 76, 14, 395, 74, 13),
        ("FL-202", "EK-201", "EK", "DXB", "JFK", "2026-09-30T08:30:00Z", "2026-09-30T14:15:00Z", "Airbus A380-800", "SCHEDULED", 940.0, 3900.0, 8600.0, 399, 76, 14, 398, 75, 14),
        ("FL-301", "NH-107", "NH", "SFO", "HND", "2026-09-28T11:45:00Z", "2026-09-29T15:00:00Z", "Boeing 787-9", "SCHEDULED", 1150.0, 4200.0, 7900.0, 180, 36, 8, 175, 34, 8),
        ("FL-302", "DL-27", "DL", "SFO", "HND", "2026-09-29T13:15:00Z", "2026-09-30T16:30:00Z", "Airbus A350-900", "SCHEDULED", 1100.0, 4100.0, 7700.0, 220, 32, 0, 218, 30, 0),
        ("FL-401", "AA-288", "AA", "ORD", "LHR", "2026-09-28T16:00:00Z", "2026-09-29T06:00:00Z", "Boeing 787-8", "SCHEDULED", 580.0, 2100.0, 4600.0, 170, 28, 0, 168, 27, 0),
        ("FL-402", "BA-296", "BA", "ORD", "LHR", "2026-09-29T20:15:00Z", "2026-09-30T10:15:00Z", "Boeing 787-9", "SCHEDULED", 610.0, 2300.0, 5000.0, 180, 36, 8, 179, 36, 8),
        ("FL-501", "DL-120", "DL", "LAX", "CDG", "2026-09-28T15:30:00Z", "2026-09-29T11:20:00Z", "Airbus A350-900", "SCHEDULED", 820.0, 3100.0, 6800.0, 220, 32, 0, 216, 31, 0),
        ("FL-502", "LH-456", "LH", "LAX", "FRA", "2026-09-29T14:40:00Z", "2026-09-30T10:30:00Z", "Boeing 747-8", "SCHEDULED", 850.0, 3300.0, 7200.0, 244, 80, 8, 240, 78, 7),
        ("FL-601", "EK-354", "EK", "DXB", "SIN", "2026-09-28T03:15:00Z", "2026-09-28T14:40:00Z", "Boeing 777-300ER", "SCHEDULED", 490.0, 1800.0, 3900.0, 304, 42, 8, 300, 40, 8),
    ]
    conn.executemany(
        "INSERT INTO flights VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        flights_data
    )

    # 4. Seats generation for each flight
    seats = []
    for f in flights_data:
        fid = f[0]
        # First class (rows 1-2, A/B/E/F)
        if f[14] > 0:
            for r in range(1, 3):
                for col in ["A", "B", "E", "F"]:
                    seats.append((fid, f"{r}{col}", "FIRST", 1, None))
        # Business class (rows 5-10, A/B/D/E/F/K)
        for r in range(5, 11):
            for col in ["A", "B", "D", "E", "F", "K"]:
                seats.append((fid, f"{r}{col}", "BUSINESS", 1, None))
        # Economy class (rows 15-40, A/B/C/D/E/F)
        for r in range(15, 41):
            for col in ["A", "B", "C", "D", "E", "F"]:
                seats.append((fid, f"{r}{col}", "ECONOMY", 1, None))

    conn.executemany(
        "INSERT INTO seats VALUES (?, ?, ?, ?, ?)",
        seats
    )

    # 5. Pre-seed a few sample bookings to make data realistic
    sample_bookings = [
        ("BK-7F9A1", "FL-101", "Alex Smith", "alex.smith@example.com", "P987654321", "ECONOMY", "15A", "CONFIRMED", "idemp-init-001", 650.0, "2026-09-25T14:20:00Z", "2026-09-25T14:20:00Z"),
        ("BK-7F9A2", "FL-101", "Sophia Patel", "sophia.p@example.com", "P123456789", "BUSINESS", "5A", "CONFIRMED", "idemp-init-002", 2400.0, "2026-09-26T09:10:00Z", "2026-09-26T09:10:00Z"),
        ("BK-8B3C4", "FL-201", "Marcus Vance", "marcus.v@example.com", "P556677889", "FIRST", "1A", "CONFIRMED", "idemp-init-003", 8500.0, "2026-09-26T11:45:00Z", "2026-09-26T11:45:00Z"),
    ]
    conn.executemany(
        "INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        sample_bookings
    )

    # Mark booked seats as unavailable
    for b in sample_bookings:
        conn.execute(
            "UPDATE seats SET is_available = 0, passenger_name = ? WHERE flight_id = ? AND seat_number = ?",
            (b[2], b[1], b[6])
        )

    # 6. Default API keys
    for key, info in settings.api_keys.items():
        conn.execute(
            """INSERT OR REPLACE INTO api_keys 
               (api_key, actor_id, tenant_id, scopes, is_admin, rate_limit_rpm, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (key, info.actor_id, info.tenant_id, ",".join(info.scopes), int(info.is_admin), info.rate_limit_rpm)
        )


def search_flights_db(
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    departure_date: Optional[str] = None,
    cabin_class: str = "ECONOMY",
    max_price: Optional[float] = None,
    direct_only: bool = True,
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Searches flights matching search criteria."""
    query = """
    SELECT f.*, al.name AS airline_name, 
           orig.name AS origin_name, orig.city AS origin_city,
           dest.name AS destination_name, dest.city AS destination_city
    FROM flights f
    JOIN airlines al ON f.airline_code = al.code
    JOIN airports orig ON f.origin = orig.code
    JOIN airports dest ON f.destination = dest.code
    WHERE 1=1
    """
    params: List[Any] = []

    if origin:
        query += " AND f.origin = ?"
        params.append(origin.strip().upper())
    if destination:
        query += " AND f.destination = ?"
        params.append(destination.strip().upper())
    if departure_date:
        query += " AND f.departure_time LIKE ?"
        params.append(f"{departure_date}%")
    
    cabin_lower = cabin_class.strip().lower()
    if cabin_lower == "business":
        query += " AND f.available_business > 0"
        if max_price:
            query += " AND f.business_price <= ?"
            params.append(max_price)
    elif cabin_lower == "first":
        query += " AND f.available_first > 0"
        if max_price:
            query += " AND f.first_price <= ?"
            params.append(max_price)
    else:
        query += " AND f.available_economy > 0"
        if max_price:
            query += " AND f.economy_price <= ?"
            params.append(max_price)

    query += " ORDER BY f.departure_time ASC LIMIT ?"
    params.append(limit)

    conn = get_connection(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_flight_details_db(flight_id_or_number: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves single flight details."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT f.*, al.name AS airline_name, al.rating AS airline_rating,
                   orig.name AS origin_name, orig.city AS origin_city, orig.weather_condition AS origin_weather,
                   dest.name AS destination_name, dest.city AS destination_city, dest.weather_condition AS dest_weather
            FROM flights f
            JOIN airlines al ON f.airline_code = al.code
            JOIN airports orig ON f.origin = orig.code
            JOIN airports dest ON f.destination = dest.code
            WHERE f.flight_id = ? OR f.flight_number = ?
            """,
            (flight_id_or_number, flight_id_or_number)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def check_seat_availability_db(
    flight_id: str,
    cabin_class: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Retrieves seat map breakdown for a flight."""
    conn = get_connection(db_path)
    try:
        flight = conn.execute("SELECT flight_id, flight_number, aircraft_model FROM flights WHERE flight_id = ?", (flight_id,)).fetchone()
        if not flight:
            return {"error": f"Flight '{flight_id}' not found"}

        query = "SELECT seat_number, cabin_class, is_available FROM seats WHERE flight_id = ?"
        params = [flight_id]
        if cabin_class:
            query += " AND cabin_class = ?"
            params.append(cabin_class.strip().upper())
        query += " ORDER BY seat_number ASC"

        rows = conn.execute(query, params).fetchall()
        seats_list = [dict(r) for r in rows]
        available_seats = [s["seat_number"] for s in seats_list if s["is_available"] == 1]

        return {
            "flight_id": flight["flight_id"],
            "flight_number": flight["flight_number"],
            "aircraft_model": flight["aircraft_model"],
            "total_queried": len(seats_list),
            "available_count": len(available_seats),
            "available_seats": available_seats[:50],  # Return up to 50 available seats
        }
    finally:
        conn.close()


def create_booking_atomic(
    flight_id: str,
    passenger_name: str,
    passenger_email: str,
    passport_num: str,
    seat_number: str,
    cabin_class: str = "ECONOMY",
    idempotency_key: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Atomically creates a booking and reserves the selected seat."""
    cabin_class = cabin_class.strip().upper()
    seat_number = seat_number.strip().upper()

    conn = get_connection(db_path)
    try:
        with conn:
            # 1. Idempotency Check
            if idempotency_key:
                existing = conn.execute(
                    "SELECT * FROM bookings WHERE idempotency_key = ?",
                    (idempotency_key,)
                ).fetchone()
                if existing:
                    return {
                        "status": "EXISTING_IDEMPOTENT",
                        "booking": dict(existing),
                        "message": "Returned existing booking matching idempotency key",
                    }

            # 2. Check Flight existence and price
            flight = conn.execute(
                "SELECT * FROM flights WHERE flight_id = ?",
                (flight_id,)
            ).fetchone()
            if not flight:
                raise ValueError(f"Flight '{flight_id}' does not exist.")

            if flight["status"] == "CANCELLED":
                raise ValueError(f"Flight '{flight_id}' is cancelled.")

            price_field = f"{cabin_class.lower()}_price"
            total_price = flight[price_field] if price_field in flight.keys() else flight["economy_price"]

            # 3. Check Seat Availability
            seat = conn.execute(
                "SELECT is_available, cabin_class FROM seats WHERE flight_id = ? AND seat_number = ?",
                (flight_id, seat_number)
            ).fetchone()
            if not seat:
                raise ValueError(f"Seat '{seat_number}' does not exist on flight '{flight_id}'.")
            if seat["is_available"] == 0:
                raise ValueError(f"Seat '{seat_number}' is already occupied.")

            # 4. Generate reference and timestamp
            booking_ref = f"BK-{uuid.uuid4().hex[:6].upper()}"
            now_iso = datetime.now(timezone.utc).isoformat()

            # 5. Insert Booking
            conn.execute(
                """
                INSERT INTO bookings 
                (booking_reference, flight_id, passenger_name, passenger_email, passport_num, 
                 cabin_class, seat_number, status, idempotency_key, total_price, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'CONFIRMED', ?, ?, ?, ?)
                """,
                (booking_ref, flight_id, passenger_name, passenger_email, passport_num,
                 cabin_class, seat_number, idempotency_key, total_price, now_iso, now_iso)
            )

            # 6. Mark seat unavailable
            conn.execute(
                "UPDATE seats SET is_available = 0, passenger_name = ? WHERE flight_id = ? AND seat_number = ?",
                (passenger_name, flight_id, seat_number)
            )

            # 7. Update flight inventory
            avail_col = f"available_{cabin_class.lower()}"
            if avail_col in flight.keys():
                conn.execute(
                    f"UPDATE flights SET {avail_col} = MAX(0, {avail_col} - 1) WHERE flight_id = ?",
                    (flight_id,)
                )

            return {
                "status": "CONFIRMED",
                "booking_reference": booking_ref,
                "flight_id": flight_id,
                "flight_number": flight["flight_number"],
                "passenger_name": passenger_name,
                "seat_number": seat_number,
                "cabin_class": cabin_class,
                "total_price": total_price,
                "created_at": now_iso,
            }
    finally:
        conn.close()


def get_booking_db(booking_reference: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieves a booking with flight details."""
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            """
            SELECT b.*, f.flight_number, f.airline_code, f.origin, f.destination,
                   f.departure_time, f.arrival_time, f.aircraft_model, f.status AS flight_status
            FROM bookings b
            JOIN flights f ON b.flight_id = f.flight_id
            WHERE b.booking_reference = ?
            """,
            (booking_reference.strip().upper(),)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def cancel_booking_atomic(booking_reference: str, reason: str = "Customer requested", db_path: Optional[str] = None) -> Dict[str, Any]:
    """Cancels a booking and restores seat inventory."""
    conn = get_connection(db_path)
    try:
        with conn:
            booking = conn.execute(
                "SELECT * FROM bookings WHERE booking_reference = ?",
                (booking_reference.strip().upper(),)
            ).fetchone()
            if not booking:
                raise ValueError(f"Booking reference '{booking_reference}' not found.")
            if booking["status"] == "CANCELLED":
                return {"status": "ALREADY_CANCELLED", "message": "Booking was already cancelled."}

            now_iso = datetime.now(timezone.utc).isoformat()

            # 1. Update Booking status
            conn.execute(
                "UPDATE bookings SET status = 'CANCELLED', updated_at = ? WHERE booking_reference = ?",
                (now_iso, booking["booking_reference"])
            )

            # 2. Release seat
            conn.execute(
                "UPDATE seats SET is_available = 1, passenger_name = NULL WHERE flight_id = ? AND seat_number = ?",
                (booking["flight_id"], booking["seat_number"])
            )

            # 3. Increment inventory count
            cabin_col = f"available_{booking['cabin_class'].lower()}"
            conn.execute(
                f"UPDATE flights SET {cabin_col} = {cabin_col} + 1 WHERE flight_id = ?",
                (booking["flight_id"],)
            )

            return {
                "status": "CANCELLED",
                "booking_reference": booking["booking_reference"],
                "flight_id": booking["flight_id"],
                "seat_released": booking["seat_number"],
                "refund_amount": booking["total_price"],
                "reason": reason,
                "cancelled_at": now_iso,
            }
    finally:
        conn.close()


def modify_booking_seat_atomic(
    booking_reference: str,
    new_seat_number: str,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Changes the assigned seat for an active booking."""
    new_seat = new_seat_number.strip().upper()
    conn = get_connection(db_path)
    try:
        with conn:
            booking = conn.execute(
                "SELECT * FROM bookings WHERE booking_reference = ?",
                (booking_reference.strip().upper(),)
            ).fetchone()
            if not booking:
                raise ValueError(f"Booking reference '{booking_reference}' not found.")
            if booking["status"] != "CONFIRMED":
                raise ValueError(f"Cannot modify booking in '{booking['status']}' state.")

            old_seat = booking["seat_number"]
            if old_seat == new_seat:
                return {"status": "NO_CHANGE", "message": f"Seat is already {new_seat}"}

            flight_id = booking["flight_id"]

            # Check new seat
            target_seat = conn.execute(
                "SELECT is_available, cabin_class FROM seats WHERE flight_id = ? AND seat_number = ?",
                (flight_id, new_seat)
            ).fetchone()
            if not target_seat:
                raise ValueError(f"Seat '{new_seat}' does not exist on flight '{flight_id}'.")
            if target_seat["is_available"] == 0:
                raise ValueError(f"Seat '{new_seat}' is already occupied.")
            if target_seat["cabin_class"] != booking["cabin_class"]:
                raise ValueError(
                    f"Seat '{new_seat}' is {target_seat['cabin_class']}, but booking is for {booking['cabin_class']}."
                )

            now_iso = datetime.now(timezone.utc).isoformat()

            # Release old seat
            conn.execute(
                "UPDATE seats SET is_available = 1, passenger_name = NULL WHERE flight_id = ? AND seat_number = ?",
                (flight_id, old_seat)
            )

            # Assign new seat
            conn.execute(
                "UPDATE seats SET is_available = 0, passenger_name = ? WHERE flight_id = ? AND seat_number = ?",
                (booking["passenger_name"], flight_id, new_seat)
            )

            # Update booking
            conn.execute(
                "UPDATE bookings SET seat_number = ?, updated_at = ? WHERE booking_reference = ?",
                (new_seat, now_iso, booking["booking_reference"])
            )

            return {
                "status": "MODIFIED",
                "booking_reference": booking["booking_reference"],
                "old_seat": old_seat,
                "new_seat": new_seat,
                "updated_at": now_iso,
            }
    finally:
        conn.close()


def record_audit(
    actor_id: str,
    capability_scope: str,
    tool_name: str,
    parameters: Dict[str, Any],
    execution_ms: float,
    status: str,
    sla_breached: bool,
    details: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """Inserts a structured compliance audit trail record."""
    conn = get_connection(db_path)
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO audit_logs 
                (timestamp, actor_id, capability_scope, tool_name, parameters, execution_ms, status, sla_breached, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    actor_id,
                    capability_scope,
                    tool_name,
                    json.dumps(parameters, default=str),
                    round(execution_ms, 2),
                    status,
                    1 if sla_breached else 0,
                    details,
                )
            )
    finally:
        conn.close()


def fetch_audit_logs(
    limit: int = 50,
    tool_filter: Optional[str] = None,
    actor_filter: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieves recent audit log records."""
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params: List[Any] = []
    if tool_filter:
        query += " AND tool_name = ?"
        params.append(tool_filter)
    if actor_filter:
        query += " AND actor_id = ?"
        params.append(actor_filter)

    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    conn = get_connection(db_path)
    try:
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["parameters"] = json.loads(d["parameters"])
            except Exception:
                pass
            result.append(d)
        return result
    finally:
        conn.close()


def execute_readonly_query(sql_query: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Executes a read-only SQL query."""
    conn = get_connection(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(sql_query)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_db_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Returns database summary statistics for health telemetry."""
    conn = get_connection(db_path)
    try:
        airports_count = conn.execute("SELECT COUNT(*) FROM airports").fetchone()[0]
        flights_count = conn.execute("SELECT COUNT(*) FROM flights").fetchone()[0]
        bookings_count = conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'CONFIRMED'").fetchone()[0]
        audit_count = conn.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
        return {
            "airports": airports_count,
            "flights": flights_count,
            "active_bookings": bookings_count,
            "audit_records": audit_count,
            "database_connected": True,
        }
    except Exception as exc:
        return {
            "database_connected": False,
            "error": str(exc),
        }
    finally:
        conn.close()
