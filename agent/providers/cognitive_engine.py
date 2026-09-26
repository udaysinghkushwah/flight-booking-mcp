"""Deterministic ReAct cognitive engine for zero-key execution & offline testing."""

from __future__ import annotations

import logging
import re
import uuid
from typing import List

from agent.models import AgentStep, Message, ToolCall, ToolDefinition
from agent.providers.base import LLMProvider

logger = logging.getLogger("agent.provider.cognitive")


class CognitiveEngineProvider(LLMProvider):
    """Rule-based ReAct state machine simulating multi-turn flight booking reasoning."""

    def __init__(self, model_name: str = "flight-cognitive-v1"):
        super().__init__(model_name=model_name)

    def generate_step(
        self,
        messages: List[Message],
        tools: List[ToolDefinition],
    ) -> AgentStep:
        # Extract the original user intent
        user_prompt = ""
        for m in messages:
            if m.role == "user" and m.content:
                user_prompt = m.content
                break

        # Count completed tool calls in history
        completed_tool_results = [m for m in messages if m.role == "tool"]
        step_number = len(completed_tool_results)

        # Step 0: Extract origin, destination, and date -> search_flights_tool
        if step_number == 0:
            codes = re.findall(r"\b(JFK|LHR|DXB|HND|CDG|SFO|LAX|SIN)\b", user_prompt.upper())
            origin = codes[0] if len(codes) >= 1 else "JFK"
            dest = codes[1] if len(codes) >= 2 else "LHR"

            date_match = re.search(r"(\d{4}-\d{2}-\d{2})", user_prompt)
            dep_date = date_match.group(1) if date_match else "2026-09-28"

            return AgentStep(
                thought=f"I need to search for available flights from {origin} to {dest} on {dep_date}.",
                tool_calls=[ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="search_flights_tool",
                    arguments={
                        "origin": origin,
                        "destination": dest,
                        "departure_date": dep_date,
                        "cabin_class": "ECONOMY",
                    },
                )],
                is_complete=False,
            )

        # Step 1: Inspect search results -> check_seat_availability_tool
        elif step_number == 1:
            last_res = completed_tool_results[-1].content
            flights = last_res.get("flights", []) if isinstance(last_res, dict) else []
            if not flights:
                return AgentStep(
                    final_response="I searched for available flights between those airports, but no direct flights were found matching your criteria.",
                    is_complete=True,
                )
            selected_flight = flights[0]
            flight_id = selected_flight.get("flight_id", "FL-101")

            return AgentStep(
                thought=f"Flight {flight_id} found. Now inspecting available seats in Economy class.",
                tool_calls=[ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="check_seat_availability_tool",
                    arguments={
                        "flight_id": flight_id,
                        "cabin_class": "ECONOMY",
                    },
                )],
                is_complete=False,
            )

        # Step 2: Select seat and extract passenger details -> create_booking_tool
        elif step_number == 2:
            seat_res = completed_tool_results[-1].content
            avail_seats = []
            flight_id = "FL-101"
            if isinstance(seat_res, dict):
                avail_seats = seat_res.get("available_seats") or seat_res.get("available_seat_numbers") or []
                flight_id = seat_res.get("flight_id", "FL-101")

            chosen_seat = avail_seats[0] if avail_seats else "15B"

            # Parse passenger details
            name_match = re.search(r"(?:for|passenger|name:?)\s+([A-Za-z\.\s]+?)(?:\(|\,|$|passport|email)", user_prompt, re.IGNORECASE)
            name = name_match.group(1).strip() if name_match else "Dr. Robert McCall"

            email_match = re.search(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", user_prompt)
            email = email_match.group(1) if email_match else "robert.mccall@equalizer.org"

            passport_match = re.search(r"\b([A-Z0-9]{7,10})\b", user_prompt)
            passport = passport_match.group(1) if passport_match else "P88776655"

            return AgentStep(
                thought=f"Selected seat {chosen_seat}. Booking flight {flight_id} for {name}.",
                tool_calls=[ToolCall(
                    id=f"call_{uuid.uuid4().hex[:8]}",
                    name="create_booking_tool",
                    arguments={
                        "flight_id": flight_id,
                        "passenger_name": name,
                        "passenger_email": email,
                        "passport_num": passport,
                        "seat_number": chosen_seat,
                        "cabin_class": "ECONOMY",
                    },
                )],
                is_complete=False,
            )

        # Step 3: Parse confirmation and synthesize final response
        else:
            booking_res = completed_tool_results[-1].content
            if not isinstance(booking_res, dict):
                booking_res = {}

            b_ref = booking_res.get("booking_reference") or "BK-CONFIRMED"
            f_num = booking_res.get("flight_number") or "BA-178"
            route = f"{booking_res.get('origin', 'JFK')} ➔ {booking_res.get('destination', 'LHR')}"
            seat = booking_res.get("seat_number") or "15B"
            price = booking_res.get("total_price", 650.0)
            p_name = booking_res.get("passenger_name", "Dr. Robert McCall")

            final_text = (
                f"🎉 **Flight Booking Confirmed!**\n\n"
                f"• **Passenger:** {p_name}\n"
                f"• **Booking Reference (PNR):** `{b_ref}`\n"
                f"• **Flight Number:** {f_num} ({route})\n"
                f"• **Seat Allocated:** {seat} (Economy)\n"
                f"• **Total Fare:** ${price:,.2f} USD\n"
                f"• **Status:** CONFIRMED & TICKETED\n\n"
                f"Your reservation is safely committed to the AWS database. Have a pleasant flight!"
            )
            return AgentStep(final_response=final_text, is_complete=True)
