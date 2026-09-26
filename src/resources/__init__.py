"""src/resources/__init__.py — Registers all MCP resources."""

from src.resources.airport_info import (
    get_airport_resource,
    get_analytics_summary_resource,
    get_cancellation_policies_resource,
)

__all__ = [
    "get_airport_resource",
    "get_cancellation_policies_resource",
    "get_analytics_summary_resource",
]
