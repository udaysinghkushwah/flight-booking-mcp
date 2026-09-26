"""Human-in-the-Loop (HITL) Safety Gate and Execution Guardrails."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from agent.models import RiskLevel

logger = logging.getLogger("agent.safety")


class HumanInTheLoopGate:
    """Production policy gate requiring explicit human or policy approval for mutating actions."""

    # Registry of tool risk levels and business impact descriptions
    TOOL_RISK_REGISTRY: Dict[str, tuple[RiskLevel, str]] = {
        "search_flights_tool": (RiskLevel.READ_ONLY, "Search public flight schedules."),
        "get_flight_details_tool": (RiskLevel.READ_ONLY, "Inspect flight and airport details."),
        "check_seat_availability_tool": (RiskLevel.READ_ONLY, "Check remaining seat inventory."),
        "get_booking_tool": (RiskLevel.READ_ONLY, "Retrieve existing booking details."),
        "query_flight_database_tool": (RiskLevel.READ_ONLY, "Safe read-only SQL query."),
        "get_audit_trail_tool": (RiskLevel.READ_ONLY, "Privileged audit log query."),
        "create_booking_tool": (RiskLevel.MUTATION_CRITICAL, "Charges ticket payment and reserves seat inventory."),
        "cancel_booking_tool": (RiskLevel.MUTATION_CRITICAL, "Cancels ticket reservation and issues refund."),
        "modify_booking_seat_tool": (RiskLevel.MUTATION_MEDIUM, "Changes seat allocation on confirmed booking."),
    }

    def __init__(
        self,
        auto_approve: bool = False,
        custom_approver: Optional[Callable[[str, Dict[str, Any], str], bool]] = None,
    ):
        self.auto_approve = auto_approve
        self.custom_approver = custom_approver

    def get_risk_level(self, tool_name: str) -> RiskLevel:
        entry = self.TOOL_RISK_REGISTRY.get(tool_name)
        return entry[0] if entry else RiskLevel.MUTATION_MEDIUM

    def get_action_description(self, tool_name: str) -> str:
        entry = self.TOOL_RISK_REGISTRY.get(tool_name)
        return entry[1] if entry else "Executes server state change."

    def authorize(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Check whether execution is authorized. Returns True if approved, False otherwise."""
        risk = self.get_risk_level(tool_name)

        # Read-only operations proceed autonomously
        if risk == RiskLevel.READ_ONLY:
            return True

        action_desc = self.get_action_description(tool_name)

        # Custom approval callback (e.g. Slack bot, webhook, UI modal)
        if self.custom_approver is not None:
            return self.custom_approver(tool_name, arguments, action_desc)

        # Auto-approval flag (for test automation / headless runs)
        if self.auto_approve:
            logger.info(f"🛡️  [HITL AUTO-APPROVED] Action {tool_name} approved by policy.")
            return True

        # Interactive terminal prompt
        print("\n" + "=" * 65)
        print("⚠️   HUMAN-IN-THE-LOOP (HITL) SAFETY GATE TRIGGERED")
        print(f"Action:      {tool_name}")
        print(f"Risk Tier:   {risk.value}")
        print(f"Impact:      {action_desc}")
        print(f"Parameters:  {json.dumps(arguments, indent=2)}")
        print("=" * 65)

        while True:
            try:
                response = input("Authorize this transaction on AWS? [y/N]: ").strip().lower()
                if response in ("y", "yes"):
                    logger.info(f"Action {tool_name} approved by operator.")
                    return True
                if response in ("n", "no", ""):
                    logger.warning(f"Action {tool_name} rejected by operator.")
                    return False
            except (EOFError, KeyboardInterrupt):
                print("\n🛑 Transaction cancelled.")
                return False
