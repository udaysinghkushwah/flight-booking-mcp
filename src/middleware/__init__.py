"""src/middleware package — authentication, RBAC, rate limiting, and audit logging."""

from src.middleware.auth import AuthenticationMiddleware
from src.middleware.rbac import (
    ActorContext,
    CapabilityScope,
    GuardrailViolation,
    RateLimitExceeded,
    RateLimiter,
    SQLSafetyValidator,
    SQLSecurityViolation,
    ScopeUnauthorized,
    get_current_actor,
    guarded_tool,
    set_current_actor,
    GLOBAL_RATE_LIMITER,
)

__all__ = [
    "AuthenticationMiddleware",
    "ActorContext",
    "CapabilityScope",
    "GuardrailViolation",
    "RateLimitExceeded",
    "RateLimiter",
    "SQLSafetyValidator",
    "SQLSecurityViolation",
    "ScopeUnauthorized",
    "get_current_actor",
    "guarded_tool",
    "set_current_actor",
    "GLOBAL_RATE_LIMITER",
]
