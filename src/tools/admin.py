"""src/tools/admin.py — Privileged admin tools: audit trail and SQL explorer."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.db.session import execute_readonly_query, fetch_audit_logs
from src.middleware.rbac import CapabilityScope, SQLSafetyValidator, guarded_tool


@guarded_tool(required_scope=CapabilityScope.FLIGHT_ADMIN, sla_threshold_ms=250.0)
def get_audit_trail(limit: int = 50, tool_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve compliance audit records, execution latencies, and SLA breach logs. (Privileged)

    Args:
        limit: Maximum number of audit records to retrieve (1–100).
        tool_filter: Optional filter by specific tool name.
    """
    clamped_limit = max(1, min(limit, 100))
    return fetch_audit_logs(limit=clamped_limit, tool_filter=tool_filter)


@guarded_tool(required_scope=CapabilityScope.SQL_READONLY, sla_threshold_ms=350.0)
def query_flight_database(sql_query: str) -> Dict[str, Any]:
    """Execute a read-only SQL SELECT query against the flight database with AST safety verification.

    Args:
        sql_query: Read-only SELECT query targeting airports, flights, airlines, or bookings tables.
    """
    SQLSafetyValidator.validate_readonly_query(sql_query)
    rows = execute_readonly_query(sql_query)
    return {
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "rows": rows[:100],  # Clamp to 100 rows max
    }
