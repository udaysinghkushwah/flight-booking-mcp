"""Platform Observability, SLA Telemetry, and Prometheus Metrics for Flight Booking MCP Server."""

from __future__ import annotations

import os
import resource
import statistics
import time
from typing import Any, Dict, List

from src.db.session import fetch_audit_logs, get_db_stats

SERVER_START_TIME = time.time()


def get_sla_metrics(sample_size: int = 100) -> Dict[str, Any]:
    """Computes real-time SLA metrics, latencies (P50/P95/P99), and error breakdown."""
    logs = fetch_audit_logs(limit=sample_size)
    if not logs:
        return {
            "sample_size": 0,
            "sla_adherence_percent": 100.0,
            "avg_latency_ms": 0.0,
            "p50_latency_ms": 0.0,
            "p95_latency_ms": 0.0,
            "p99_latency_ms": 0.0,
            "total_breaches": 0,
            "status_breakdown": {},
        }

    latencies = [log["execution_ms"] for log in logs]
    breaches = sum(1 for log in logs if log["sla_breached"] == 1)
    status_counts: Dict[str, int] = {}
    for log in logs:
        st = log["status"]
        status_counts[st] = status_counts.get(st, 0) + 1

    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)
    p50 = statistics.median(sorted_latencies)
    p95 = sorted_latencies[min(int(n * 0.95), n - 1)]
    p99 = sorted_latencies[min(int(n * 0.99), n - 1)]
    sla_adherence = round(((n - breaches) / n) * 100.0, 2)

    return {
        "sample_size": n,
        "sla_adherence_percent": sla_adherence,
        "avg_latency_ms": round(statistics.mean(latencies), 2),
        "p50_latency_ms": round(p50, 2),
        "p95_latency_ms": round(p95, 2),
        "p99_latency_ms": round(p99, 2),
        "total_breaches": breaches,
        "status_breakdown": status_counts,
    }


def get_platform_health_report() -> Dict[str, Any]:
    """Generates an operational health status report."""
    uptime_seconds = round(time.time() - SERVER_START_TIME, 1)
    sla_stats = get_sla_metrics(sample_size=50)
    db_stats = get_db_stats()

    # Memory usage in MB
    try:
        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # On macOS ru_maxrss is in bytes, on Linux in KB
        memory_mb = round(max_rss / (1024 * 1024) if "darwin" in os.sys.platform else max_rss / 1024, 2)
    except Exception:
        memory_mb = 0.0

    adherence = sla_stats["sla_adherence_percent"]
    db_ok = db_stats.get("database_connected", False)

    if db_ok and adherence >= 95.0:
        health_state = "HEALTHY"
    elif db_ok and adherence >= 80.0:
        health_state = "DEGRADED"
    else:
        health_state = "UNHEALTHY"

    return {
        "status": health_state,
        "service": "flight-booking-mcp-server",
        "version": "1.0.0",
        "environment": "production-aws",
        "uptime_seconds": uptime_seconds,
        "memory_mb": memory_mb,
        "database": db_stats,
        "sla_metrics": sla_stats,
    }


def get_prometheus_metrics() -> str:
    """Renders Prometheus plain text exposition format."""
    health = get_platform_health_report()
    sla = health["sla_metrics"]
    db = health["database"]
    lines = []

    lines.append("# HELP flight_mcp_uptime_seconds Total server uptime in seconds.")
    lines.append("# TYPE flight_mcp_uptime_seconds gauge")
    lines.append(f"flight_mcp_uptime_seconds {health['uptime_seconds']}")

    lines.append("# HELP flight_mcp_memory_usage_mb Server memory consumption in MB.")
    lines.append("# TYPE flight_mcp_memory_usage_mb gauge")
    lines.append(f"flight_mcp_memory_usage_mb {health['memory_mb']}")

    lines.append("# HELP flight_mcp_database_connected SQLite database connectivity status (1=up, 0=down).")
    lines.append("# TYPE flight_mcp_database_connected gauge")
    lines.append(f"flight_mcp_database_connected {1 if db.get('database_connected') else 0}")

    lines.append("# HELP flight_mcp_active_bookings Current total active confirmed bookings.")
    lines.append("# TYPE flight_mcp_active_bookings gauge")
    lines.append(f"flight_mcp_active_bookings {db.get('active_bookings', 0)}")

    lines.append("# HELP flight_mcp_sla_adherence_ratio SLA compliance percentage ratio (0.0 - 1.0).")
    lines.append("# TYPE flight_mcp_sla_adherence_ratio gauge")
    lines.append(f"flight_mcp_sla_adherence_ratio {round(sla['sla_adherence_percent'] / 100.0, 4)}")

    lines.append("# HELP flight_mcp_latency_ms Execution latency percentiles in milliseconds.")
    lines.append("# TYPE flight_mcp_latency_ms gauge")
    lines.append(f'flight_mcp_latency_ms{{quantile="0.5"}} {sla["p50_latency_ms"]}')
    lines.append(f'flight_mcp_latency_ms{{quantile="0.95"}} {sla["p95_latency_ms"]}')
    lines.append(f'flight_mcp_latency_ms{{quantile="0.99"}} {sla["p99_latency_ms"]}')

    lines.append("# HELP flight_mcp_requests_total Total requests processed broken down by status.")
    lines.append("# TYPE flight_mcp_requests_total counter")
    for st, count in sla.get("status_breakdown", {}).items():
        lines.append(f'flight_mcp_requests_total{{status="{st}"}} {count}')

    return "\n".join(lines) + "\n"
