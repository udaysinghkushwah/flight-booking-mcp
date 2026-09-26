"""Platform Guardrails, RBAC Scopes, Rate Limiting, and SQL AST Validator."""

from __future__ import annotations

import contextvars
import functools
import inspect
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import sqlparse
from src.db.session import record_audit


class CapabilityScope(str, Enum):
    """Fine-grained capability scopes for flight tools."""
    FLIGHT_READ = "flight:read"
    FLIGHT_BOOK = "flight:book"
    FLIGHT_ADMIN = "flight:admin"
    SQL_READONLY = "sql:readonly"


DEFAULT_TOOL_SLA_MS = 300.0


@dataclass
class ActorContext:
    """Security context of the calling actor/agent."""
    actor_id: str
    tenant_id: str = "travel-partner-default"
    scopes: Set[str] = field(default_factory=lambda: {
        CapabilityScope.FLIGHT_READ.value,
        CapabilityScope.FLIGHT_BOOK.value,
    })
    is_admin: bool = False
    rate_limit_rpm: int = 120

    def has_scope(self, scope: str) -> bool:
        if self.is_admin:
            return True
        return scope in self.scopes


class GuardrailViolation(Exception):
    """Base exception for guardrail violations."""
    pass


class ScopeUnauthorized(GuardrailViolation):
    """Raised when an actor lacks the required capability scope."""
    pass


class RateLimitExceeded(GuardrailViolation):
    """Raised when an actor exceeds allowed requests per window."""
    pass


class SQLSecurityViolation(GuardrailViolation):
    """Raised when an unsafe or non-readonly SQL statement is executed."""
    pass


# Global Token Bucket Rate Limiter
class RateLimiter:
    """Per-actor token-bucket rate limiter."""

    def __init__(self, capacity: int = 60, refill_rate_per_sec: float = 1.0) -> None:
        self.capacity = capacity
        self.refill_rate = refill_rate_per_sec
        self.tokens: Dict[str, float] = {}
        self.last_update: Dict[str, float] = {}

    def is_allowed(self, actor_id: str) -> bool:
        now = time.time()
        last = self.last_update.get(actor_id, now)
        elapsed = now - last
        self.last_update[actor_id] = now

        current_tokens = self.tokens.get(actor_id, float(self.capacity))
        current_tokens = min(float(self.capacity), current_tokens + elapsed * self.refill_rate)

        if current_tokens >= 1.0:
            self.tokens[actor_id] = current_tokens - 1.0
            return True
        self.tokens[actor_id] = current_tokens
        return False


GLOBAL_RATE_LIMITER = RateLimiter(capacity=60, refill_rate_per_sec=1.0)

# ContextVar for request-isolated actor context
_ACTOR_CONTEXT_VAR: contextvars.ContextVar[ActorContext] = contextvars.ContextVar(
    "current_actor",
    default=ActorContext(
        actor_id="default-flight-agent",
        tenant_id="default-tenant",
        scopes={
            CapabilityScope.FLIGHT_READ.value,
            CapabilityScope.FLIGHT_BOOK.value,
            CapabilityScope.FLIGHT_ADMIN.value,
            CapabilityScope.SQL_READONLY.value,
        },
        is_admin=True,
    )
)


def get_current_actor() -> ActorContext:
    return _ACTOR_CONTEXT_VAR.get()


def set_current_actor(actor: ActorContext) -> None:
    _ACTOR_CONTEXT_VAR.set(actor)


class SQLSafetyValidator:
    """Validates SQL statements to ensure read-only execution."""

    DISALLOWED_KEYWORDS = {
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "REPLACE",
        "TRUNCATE", "EXEC", "EXECUTE", "PRAGMA", "ATTACH", "DETACH", "VACUUM",
        "GRANT", "REVOKE", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT",
    }

    @classmethod
    def validate_readonly_query(cls, sql_query: str) -> None:
        """Parses and verifies that the query is strictly read-only."""
        cleaned = sql_query.strip()
        if not cleaned:
            raise SQLSecurityViolation("SQL query cannot be empty.")

        parsed = sqlparse.parse(cleaned)
        if not parsed:
            raise SQLSecurityViolation("Failed to parse SQL query.")

        # Ensure only 1 statement
        statements = [s for s in parsed if s.get_type() != "UNKNOWN" or s.tokens]
        if len(statements) > 1:
            raise SQLSecurityViolation("Multi-statement queries are strictly prohibited.")

        stmt = statements[0]
        stmt_type = stmt.get_type()
        if stmt_type not in ("SELECT",):
            raise SQLSecurityViolation(f"Only SELECT queries are permitted (got: '{stmt_type}').")

        # Scan all tokens for disallowed keywords or subquery write statements
        tokens_text = " ".join([t.value for t in stmt.flatten()]).upper()
        for word in re.findall(r"\b[A-Z]+\b", tokens_text):
            if word in cls.DISALLOWED_KEYWORDS:
                raise SQLSecurityViolation(f"Forbidden SQL operation detected: '{word}'.")


def guarded_tool(
    required_scope: CapabilityScope,
    sla_threshold_ms: float = DEFAULT_TOOL_SLA_MS,
    enable_rate_limit: bool = True,
):
    """Decorator to enforce enterprise guardrails on tool execution."""

    def decorator(fn: Callable[..., Any]):
        tool_name = fn.__name__
        is_coroutine = inspect.iscoroutinefunction(fn)

        if is_coroutine:
            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                actor = get_current_actor()
                start_time = time.perf_counter()
                status = "SUCCESS"
                error_details: Optional[str] = None

                try:
                    # 1. Rate Limit
                    if enable_rate_limit and not GLOBAL_RATE_LIMITER.is_allowed(actor.actor_id):
                        status = "BLOCKED_RATE_LIMIT"
                        error_details = f"Actor '{actor.actor_id}' exceeded rate limit."
                        raise RateLimitExceeded(error_details)

                    # 2. Scope AuthZ
                    if not actor.has_scope(required_scope.value):
                        status = "BLOCKED_UNAUTHORIZED"
                        error_details = (
                            f"Actor '{actor.actor_id}' lacks required scope '{required_scope.value}'. "
                            f"Granted scopes: {sorted(list(actor.scopes))}"
                        )
                        raise ScopeUnauthorized(error_details)

                    # 3. Execution
                    result = await fn(*args, **kwargs)
                    return result

                except Exception as exc:
                    if status == "SUCCESS":
                        status = "FAILED_EXCEPTION"
                        error_details = str(exc)
                    raise

                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    sla_breached = duration_ms > sla_threshold_ms
                    try:
                        call_params = inspect.getcallargs(fn, *args, **kwargs) if args or kwargs else {}
                        # Sanitize sensitive fields (passport, tokens, keys)
                        sanitized = {
                            k: ("***" if "passport" in k.lower() or "token" in k.lower() or "key" in k.lower() else v)
                            for k, v in call_params.items()
                        }
                        record_audit(
                            actor_id=actor.actor_id,
                            capability_scope=required_scope.value,
                            tool_name=tool_name,
                            parameters=sanitized,
                            execution_ms=duration_ms,
                            status=status,
                            sla_breached=sla_breached,
                            details=error_details,
                        )
                    except Exception as audit_err:
                        print(f"[GUARDRAIL_WARNING] Failed to record audit log: {audit_err}")

            return async_wrapper

        else:
            @functools.wraps(fn)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                actor = get_current_actor()
                start_time = time.perf_counter()
                status = "SUCCESS"
                error_details: Optional[str] = None

                try:
                    # 1. Rate Limit
                    if enable_rate_limit and not GLOBAL_RATE_LIMITER.is_allowed(actor.actor_id):
                        status = "BLOCKED_RATE_LIMIT"
                        error_details = f"Actor '{actor.actor_id}' exceeded rate limit."
                        raise RateLimitExceeded(error_details)

                    # 2. Scope AuthZ
                    if not actor.has_scope(required_scope.value):
                        status = "BLOCKED_UNAUTHORIZED"
                        error_details = (
                            f"Actor '{actor.actor_id}' lacks required scope '{required_scope.value}'. "
                            f"Granted scopes: {sorted(list(actor.scopes))}"
                        )
                        raise ScopeUnauthorized(error_details)

                    # 3. Execution
                    result = fn(*args, **kwargs)
                    return result

                except Exception as exc:
                    if status == "SUCCESS":
                        status = "FAILED_EXCEPTION"
                        error_details = str(exc)
                    raise

                finally:
                    duration_ms = (time.perf_counter() - start_time) * 1000.0
                    sla_breached = duration_ms > sla_threshold_ms
                    try:
                        call_params = inspect.getcallargs(fn, *args, **kwargs) if args or kwargs else {}
                        sanitized = {
                            k: ("***" if "passport" in k.lower() or "token" in k.lower() or "key" in k.lower() else v)
                            for k, v in call_params.items()
                        }
                        record_audit(
                            actor_id=actor.actor_id,
                            capability_scope=required_scope.value,
                            tool_name=tool_name,
                            parameters=sanitized,
                            execution_ms=duration_ms,
                            status=status,
                            sla_breached=sla_breached,
                            details=error_details,
                        )
                    except Exception as audit_err:
                        print(f"[GUARDRAIL_WARNING] Failed to record audit log: {audit_err}")

            return sync_wrapper

    return decorator
