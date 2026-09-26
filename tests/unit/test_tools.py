"""Unit tests for Flight Booking Tools."""

import os
import tempfile
import unittest

from src.db.session import init_db
from src.middleware.rbac import ActorContext, CapabilityScope, set_current_actor
from src.tools import (
    cancel_booking,
    check_seat_availability,
    create_booking,
    get_audit_trail,
    get_booking,
    get_flight_details,
    modify_booking_seat,
    query_flight_database,
    search_flights,
)


class TestFlightTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use isolated test DB for tools tests
        cls.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        cls.db_path = cls.temp_file.name
        cls.temp_file.close()

        import src.config
        cls._original_db_path = src.config.settings.db_path  # stash
        src.config.settings.db_path = cls.db_path
        init_db(cls.db_path)

        # Set default admin actor
        set_current_actor(ActorContext(
            actor_id="test-suite-admin",
            scopes={
                CapabilityScope.FLIGHT_READ.value,
                CapabilityScope.FLIGHT_BOOK.value,
                CapabilityScope.FLIGHT_ADMIN.value,
                CapabilityScope.SQL_READONLY.value,
            },
            is_admin=True,
        ))

    @classmethod
    def tearDownClass(cls):
        # Restore original db_path so downstream integration tests work
        import src.config
        src.config.settings.db_path = cls._original_db_path
        if os.path.exists(cls.db_path):
            os.remove(cls.db_path)

    def test_search_flights(self):
        res = search_flights(origin="JFK", destination="LHR")
        self.assertGreaterEqual(res["count"], 1)
        self.assertIn("flights", res)

    def test_get_flight_details(self):
        details = get_flight_details("FL-101")
        self.assertNotIn("error", details)
        self.assertEqual(details["flight_number"], "BA-178")
        self.assertEqual(details["origin"], "JFK")

    def test_check_seat_availability(self):
        seats = check_seat_availability("FL-101", cabin_class="ECONOMY")
        self.assertGreater(seats["available_count"], 0)
        self.assertIsInstance(seats["available_seats"], list)

    def test_booking_lifecycle(self):
        # 1. Create booking
        booking = create_booking(
            flight_id="FL-101",
            passenger_name="Emma Watson",
            passenger_email="emma.w@example.com",
            passport_num="GB-5544332",
            seat_number="22A",
            cabin_class="ECONOMY",
            idempotency_key="idemp-tool-001",
        )
        self.assertEqual(booking["status"], "CONFIRMED")
        ref = booking["booking_reference"]

        # 2. Retrieve booking
        fetched = get_booking(ref)
        self.assertEqual(fetched["passenger_name"], "Emma Watson")
        self.assertEqual(fetched["seat_number"], "22A")

        # 3. Modify seat
        mod = modify_booking_seat(ref, "22B")
        self.assertEqual(mod["status"], "MODIFIED")
        self.assertEqual(mod["new_seat"], "22B")

        # 4. Cancel booking
        cancel = cancel_booking(ref, reason="Traveler cancelled")
        self.assertEqual(cancel["status"], "CANCELLED")
        self.assertEqual(cancel["seat_released"], "22B")

    def test_query_flight_database(self):
        res = query_flight_database("SELECT code, name, city FROM airports WHERE code = 'JFK'")
        self.assertEqual(res["row_count"], 1)
        self.assertEqual(res["rows"][0]["city"], "New York")

    def test_get_audit_trail(self):
        logs = get_audit_trail(limit=10)
        self.assertIsInstance(logs, list)
        self.assertGreaterEqual(len(logs), 1)


if __name__ == "__main__":
    unittest.main()
