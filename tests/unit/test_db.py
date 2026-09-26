"""Unit tests for SQLite database layer."""

import os
import tempfile
import unittest

from src.db.session import (
    cancel_booking_atomic,
    check_seat_availability_db,
    create_booking_atomic,
    fetch_audit_logs,
    get_booking_db,
    get_db_stats,
    get_flight_details_db,
    init_db,
    modify_booking_seat_atomic,
    record_audit,
    search_flights_db,
)


class TestDatabaseLayer(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        init_db(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_init_db_and_stats(self):
        stats = get_db_stats(self.db_path)
        self.assertTrue(stats["database_connected"])
        self.assertGreaterEqual(stats["airports"], 10)
        self.assertGreaterEqual(stats["flights"], 10)

    def test_search_flights(self):
        flights = search_flights_db(origin="JFK", destination="LHR", db_path=self.db_path)
        self.assertGreaterEqual(len(flights), 1)
        self.assertEqual(flights[0]["origin"], "JFK")
        self.assertEqual(flights[0]["destination"], "LHR")

    def test_create_and_get_booking(self):
        booking = create_booking_atomic(
            flight_id="FL-101",
            passenger_name="Alice Walker",
            passenger_email="alice@example.com",
            passport_num="US-1234567",
            seat_number="18A",
            cabin_class="ECONOMY",
            idempotency_key="idemp-test-01",
            db_path=self.db_path,
        )
        self.assertEqual(booking["status"], "CONFIRMED")
        ref = booking["booking_reference"]
        self.assertTrue(ref.startswith("BK-"))

        # Retrieve booking
        fetched = get_booking_db(ref, db_path=self.db_path)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["passenger_name"], "Alice Walker")
        self.assertEqual(fetched["seat_number"], "18A")

    def test_idempotency(self):
        booking1 = create_booking_atomic(
            flight_id="FL-101",
            passenger_name="Bob Miller",
            passenger_email="bob@example.com",
            passport_num="US-7654321",
            seat_number="19B",
            cabin_class="ECONOMY",
            idempotency_key="idemp-repeat-test",
            db_path=self.db_path,
        )
        self.assertEqual(booking1["status"], "CONFIRMED")

        # Second call with same idempotency key
        booking2 = create_booking_atomic(
            flight_id="FL-101",
            passenger_name="Bob Miller",
            passenger_email="bob@example.com",
            passport_num="US-7654321",
            seat_number="19B",
            cabin_class="ECONOMY",
            idempotency_key="idemp-repeat-test",
            db_path=self.db_path,
        )
        self.assertEqual(booking2["status"], "EXISTING_IDEMPOTENT")
        self.assertEqual(booking2["booking"]["booking_reference"], booking1["booking_reference"])

    def test_cancel_booking(self):
        booking = create_booking_atomic(
            flight_id="FL-102",
            passenger_name="Charlie Cox",
            passenger_email="charlie@example.com",
            passport_num="UK-998877",
            seat_number="20C",
            cabin_class="ECONOMY",
            db_path=self.db_path,
        )
        ref = booking["booking_reference"]
        cancelled = cancel_booking_atomic(ref, reason="Schedule change", db_path=self.db_path)
        self.assertEqual(cancelled["status"], "CANCELLED")

        # Verify seat is available again
        seats = check_seat_availability_db("FL-102", cabin_class="ECONOMY", db_path=self.db_path)
        self.assertIn("20C", seats["available_seats"])

    def test_modify_seat(self):
        booking = create_booking_atomic(
            flight_id="FL-101",
            passenger_name="David King",
            passenger_email="david@example.com",
            passport_num="CA-112233",
            seat_number="21A",
            cabin_class="ECONOMY",
            db_path=self.db_path,
        )
        ref = booking["booking_reference"]
        modified = modify_booking_seat_atomic(ref, "21B", db_path=self.db_path)
        self.assertEqual(modified["status"], "MODIFIED")
        self.assertEqual(modified["new_seat"], "21B")

    def test_audit_logs(self):
        record_audit(
            actor_id="test-actor",
            capability_scope="flight:read",
            tool_name="search_flights",
            parameters={"origin": "JFK"},
            execution_ms=12.5,
            status="SUCCESS",
            sla_breached=False,
            db_path=self.db_path,
        )
        logs = fetch_audit_logs(limit=5, db_path=self.db_path)
        self.assertGreaterEqual(len(logs), 1)
        self.assertEqual(logs[0]["tool_name"], "search_flights")
        self.assertEqual(logs[0]["actor_id"], "test-actor")


if __name__ == "__main__":
    unittest.main()
