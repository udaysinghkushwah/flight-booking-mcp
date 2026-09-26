"""Production Configuration for Flight Booking MCP Server."""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Set


@dataclass
class APIKeyInfo:
    actor_id: str
    tenant_id: str
    scopes: Set[str]
    is_admin: bool = False
    rate_limit_rpm: int = 120


@dataclass
class Settings:
    host: str = os.getenv("MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("MCP_PORT", "8080"))
    db_path: str = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "flight_booking.db"))  # workspace root
    
    # Transport Security
    raw_allowed_hosts: str = os.getenv("MCP_ALLOWED_HOSTS", "*")
    raw_allowed_origins: str = os.getenv("MCP_ALLOWED_ORIGINS", "")
    disable_dns_rebinding: bool = (
        os.getenv("MCP_DISABLE_DNS_REBINDING", "false").lower() in ("true", "1", "yes")
        or os.getenv("MCP_ALLOWED_HOSTS", "*").strip() == "*"
    )
    
    # Rate Limiting
    rate_limit_capacity: int = int(os.getenv("RATE_LIMIT_CAPACITY", "60"))
    rate_limit_refill_per_sec: float = float(os.getenv("RATE_LIMIT_REFILL_PER_SEC", "1.0"))
    
    # Authentication
    auth_enabled: bool = os.getenv("MCP_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")
    
    # Pre-configured API keys for production environments
    api_keys: Dict[str, APIKeyInfo] = field(default_factory=lambda: {
        "flight-agent-key-secret": APIKeyInfo(
            actor_id="agent-booking-bot",
            tenant_id="travel-partner-global",
            scopes={"flight:read", "flight:book"},
            is_admin=False,
            rate_limit_rpm=120,
        ),
        "flight-admin-key-secret": APIKeyInfo(
            actor_id="admin-flight-ops",
            tenant_id="internal-operations",
            scopes={"flight:read", "flight:book", "flight:admin", "sql:readonly"},
            is_admin=True,
            rate_limit_rpm=300,
        ),
        "flight-viewer-key-secret": APIKeyInfo(
            actor_id="viewer-readonly",
            tenant_id="partner-affiliate",
            scopes={"flight:read"},
            is_admin=False,
            rate_limit_rpm=60,
        ),
    })

    @property
    def allowed_hosts(self) -> List[str]:
        return [h.strip() for h in self.raw_allowed_hosts.split(",") if h.strip()]

    @property
    def allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.raw_allowed_origins.split(",") if o.strip()]


settings = Settings()
