"""Unit tests for Guardrails, Scopes, Rate Limiter, and SQL Safety."""

import unittest

from src.middleware.rbac import (
    ActorContext,
    CapabilityScope,
    RateLimiter,
    RateLimitExceeded,
    SQLSafetyValidator,
    SQLSecurityViolation,
    ScopeUnauthorized,
    get_current_actor,
    guarded_tool,
    set_current_actor,
)


class TestGuardrails(unittest.TestCase):
    def setUp(self):
        self.original_actor = get_current_actor()

    def tearDown(self):
        set_current_actor(self.original_actor)

    def test_actor_context_and_scopes(self):
        actor = ActorContext(
            actor_id="viewer-test",
            scopes={CapabilityScope.FLIGHT_READ.value},
            is_admin=False,
        )
        self.assertTrue(actor.has_scope(CapabilityScope.FLIGHT_READ.value))
        self.assertFalse(actor.has_scope(CapabilityScope.FLIGHT_BOOK.value))

        admin_actor = ActorContext(
            actor_id="admin-test",
            scopes=set(),
            is_admin=True,
        )
        self.assertTrue(admin_actor.has_scope(CapabilityScope.FLIGHT_BOOK.value))
        self.assertTrue(admin_actor.has_scope(CapabilityScope.FLIGHT_ADMIN.value))

    def test_guarded_tool_unauthorized_scope(self):
        @guarded_tool(required_scope=CapabilityScope.FLIGHT_ADMIN)
        def admin_action():
            return "ok"

        # Set user actor lacking admin scope
        set_current_actor(ActorContext(
            actor_id="user-non-admin",
            scopes={CapabilityScope.FLIGHT_READ.value},
        ))

        with self.assertRaises(ScopeUnauthorized):
            admin_action()

    def test_guarded_tool_authorized(self):
        @guarded_tool(required_scope=CapabilityScope.FLIGHT_READ)
        def read_action():
            return "success"

        set_current_actor(ActorContext(
            actor_id="user-reader",
            scopes={CapabilityScope.FLIGHT_READ.value},
        ))

        self.assertEqual(read_action(), "success")

    def test_rate_limiter(self):
        limiter = RateLimiter(capacity=3, refill_rate_per_sec=0.1)
        actor_id = "bot-burst"

        # First 3 should pass
        self.assertTrue(limiter.is_allowed(actor_id))
        self.assertTrue(limiter.is_allowed(actor_id))
        self.assertTrue(limiter.is_allowed(actor_id))

        # 4th should be blocked
        self.assertFalse(limiter.is_allowed(actor_id))

    def test_sql_safety_validator_allowed(self):
        valid_queries = [
            "SELECT * FROM flights;",
            "SELECT code, name FROM airports WHERE country = 'USA'",
            "SELECT origin, COUNT(*) FROM flights GROUP BY origin HAVING COUNT(*) > 1",
            "SELECT f.flight_number, al.name FROM flights f JOIN airlines al ON f.airline_code = al.code",
        ]
        for q in valid_queries:
            SQLSafetyValidator.validate_readonly_query(q)

    def test_sql_safety_validator_forbidden(self):
        malicious_queries = [
            "DROP TABLE flights;",
            "DELETE FROM bookings WHERE 1=1;",
            "INSERT INTO airports VALUES ('EVL', 'Evil', 'Evil', 'Evil', 'UTC', 'A', 'C', 1);",
            "UPDATE flights SET economy_price = 0;",
            "SELECT * FROM flights; DROP TABLE users;",
            "ATTACH DATABASE 'evil.db' AS evil;",
            "PRAGMA writable_schema = 1;",
        ]
        for q in malicious_queries:
            with self.assertRaises(SQLSecurityViolation, msg=f"Should reject: {q}"):
                SQLSafetyValidator.validate_readonly_query(q)


if __name__ == "__main__":
    unittest.main()
