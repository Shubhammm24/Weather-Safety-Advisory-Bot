"""
Graph node functions.

Each node takes state dict and returns a partial state update.
Fixed-text nodes (honest_failure, scope_reply, etc.) use no LLM.

NOTE: LangGraph passes state as a plain dict, not a Pydantic object.
All state access uses dict indexing: state["key"], not state.key.
"""

from __future__ import annotations

import re
from typing import Any

from langchain_core.messages import AIMessage

from app.graph.state import IntentResult, SessionFacts
from app.graph.intent import extract_intent, merge_with_session
from app.weather.client import geocode, reverse_geocode, fetch_forecast
from app.weather.errors import LocationNotFound, WeatherUnavailable
from app.sops.loader import load_sops
from app.sops.metrics import compute_metrics
from app.sops.matcher import match_sops
from app.sops.resolve import resolve_conflicts
from app.compose.prompts import compose_advisory_reply
from app.compose.grounding import check_grounding


def _get(state: dict, key: str, default=None):
    """Safely get a value from the state dict."""
    return state.get(key, default)


# --- Node: parse_intent ---

def parse_intent(state: dict) -> dict:
    """Extract structured intent from the user's latest message."""
    messages = state.get("messages", [])
    user_message = messages[-1].content if messages else ""

    intent = extract_intent(user_message)

    # Merge with session facts
    sf = state.get("session_facts") or SessionFacts()
    if isinstance(sf, dict):
        sf = SessionFacts(**sf)
    session_dict = {
        "last_location": sf.last_location,
        "last_activity": sf.last_activity,
        "last_groups": sf.last_groups,
        "last_time_window": sf.last_time_window,
    }
    merged_intent = merge_with_session(intent, session_dict)

    # Default unspecified time to "now" on first turn
    if merged_intent.time_window == "unspecified":
        merged_intent.time_window = "now"

    return {
        "intent": merged_intent,
        "route": state.get("route", []) + ["parse_intent"],
    }


def route_after_intent(state: dict) -> str:
    """Route after intent extraction."""
    intent = state.get("intent")
    if intent and not intent.in_scope:
        return "scope_reply"
    if intent and not intent.location:
        # If browser coords are available, use them instead of asking
        if state.get("user_coords"):
            return "resolve_location"
        return "ask_location"
    return "resolve_location"





# --- Node: scope_reply (fixed text, no LLM) ---

def scope_reply(state: dict) -> dict:
    """Reply when the question is out of scope."""
    reply = (
        "I'm a weather safety advisor for outdoor activities. "
        "I can help you decide if it's safe to cycle, walk, run, hike, "
        "have a picnic, travel by road, or do other outdoor activities "
        "based on current weather conditions.\n\n"
        "Could you ask me about an outdoor activity? For example: "
        "\"Is it safe to cycle in Bhopal today?\""
    )
    return {
        "final_reply": reply,
        "route": state.get("route", []) + ["scope_reply"],
        "messages": [AIMessage(content=reply)],
    }


# --- Node: ask_location (fixed text, no LLM) ---

def ask_location(state: dict) -> dict:
    """Ask the user for their location."""
    intent = state.get("intent")
    activity = intent.activity if intent else "your activity"
    reply = (
        f"I'd like to check the weather for {activity}, but I need to know "
        f"your location. Which city or town are you in?"
    )
    return {
        "final_reply": reply,
        "route": state.get("route", []) + ["ask_location"],
        "messages": [AIMessage(content=reply)],
    }


# --- Node: resolve_location ---

def resolve_location(state: dict) -> dict:
    """Geocode the user's location (from text or browser coords)."""
    intent = state.get("intent")
    location_name = intent.location if intent else ""
    user_coords = state.get("user_coords")

    try:
        if location_name:
            # User mentioned a location by name — forward geocode
            location = geocode(location_name)
        elif user_coords:
            # No text location but browser coords available — reverse geocode
            location = reverse_geocode(
                user_coords["latitude"],
                user_coords["longitude"],
            )
            # Update the intent with the resolved location name
            if intent:
                intent.location = location["name"]
        else:
            raise LocationNotFound("No location provided")

        return {
            "location": location,
            "intent": intent,
            "route": state.get("route", []) + ["resolve_location"],
        }
    except LocationNotFound:
        return {
            "error_kind": "location_not_found",
            "route": state.get("route", []) + ["resolve_location"],
        }
    except WeatherUnavailable:
        return {
            "error_kind": "weather_unavailable",
            "route": state.get("route", []) + ["resolve_location"],
        }


def route_after_location(state: dict) -> str:
    """Route after location resolution."""
    if state.get("error_kind"):
        return "honest_failure"
    return "fetch_weather"


# --- Node: fetch_weather ---

def fetch_weather_node(state: dict) -> dict:
    """Fetch weather forecast for the resolved location."""
    location = state.get("location", {})
    try:
        forecast = fetch_forecast(
            location["latitude"],
            location["longitude"],
        )
        return {
            "forecast": forecast,
            "route": state.get("route", []) + ["fetch_weather"],
        }
    except WeatherUnavailable:
        return {
            "error_kind": "weather_unavailable",
            "route": state.get("route", []) + ["fetch_weather"],
        }


def route_after_weather(state: dict) -> str:
    """Route after weather fetch."""
    if state.get("error_kind"):
        return "honest_failure"
    return "match_sops"


# --- Node: match_sops ---

def match_sops_node(state: dict) -> dict:
    """Compute metrics and match SOPs."""
    intent = state.get("intent")
    forecast = state.get("forecast", {})

    time_window = intent.time_window if intent else "now"
    metrics_result = compute_metrics(forecast["raw"], time_window)

    sops = load_sops()

    activity = intent.activity if intent else "other"
    groups = intent.groups if intent else ["general"]
    match_result = match_sops(sops, metrics_result["metrics"], activity, groups)

    resolved = resolve_conflicts(match_result.matched)

    return {
        "metrics": metrics_result,
        "match_result": match_result,
        "resolved_sops": resolved,
        "route": state.get("route", []) + ["match_sops"],
    }


def route_after_match(state: dict) -> str:
    """Route after SOP matching."""
    resolved = state.get("resolved_sops")
    if not resolved or not resolved.primary:
        return "no_sop_reply"
    return "compose_reply"


# --- Node: no_sop_reply (fixed text, no LLM) ---

def no_sop_reply(state: dict) -> dict:
    """Reply when no SOP matches."""
    intent = state.get("intent")
    location = state.get("location")
    activity = intent.activity if intent else "this activity"
    location_name = location.get("name", "your location") if location else "your location"

    reply = (
        f"I don't have a specific safety policy for {activity} in the current "
        f"weather conditions at {location_name}. This doesn't mean it's safe or "
        f"unsafe — it means this activity isn't covered by my advisory policies.\n\n"
        f"Please use your own judgment and check local weather reports."
    )
    return {
        "final_reply": reply,
        "route": state.get("route", []) + ["no_sop_reply"],
        "messages": [AIMessage(content=reply)],
    }


# --- Node: honest_failure (fixed text, no LLM) ---

def honest_failure(state: dict) -> dict:
    """Reply when something failed (location not found, weather unavailable)."""
    error = state.get("error_kind", "unknown")
    intent = state.get("intent")

    if error == "location_not_found":
        location_name = intent.location if intent else "that location"
        reply = (
            f"I couldn't find a location matching \"{location_name}\". "
            f"Please try a different city or town name. "
            f"I'm not providing any weather forecast or safety advice for this request."
        )
    elif error == "weather_unavailable":
        reply = (
            "The weather service is currently unavailable. "
            "I cannot provide any forecast or safety advice without reliable weather data. "
            "Please try again in a few minutes."
        )
    else:
        reply = (
            "Something went wrong while processing your request. "
            "I cannot provide safety advice without complete data. "
            "Please try again."
        )

    return {
        "final_reply": reply,
        "route": state.get("route", []) + ["honest_failure"],
        "messages": [AIMessage(content=reply)],
    }


# --- Node: compose_reply (LLM) ---

def _fill_placeholders(guidance: str, metric_values: dict) -> str:
    """Replace {metric_name} placeholders in guidance with actual values."""
    for key, value in metric_values.items():
        if value is not None:
            if isinstance(value, float):
                formatted = f"{value:.1f}" if value != int(value) else str(int(value))
            else:
                formatted = str(value)
            guidance = guidance.replace(f"{{{key}}}", formatted)
    return guidance


def compose_reply(state: dict) -> dict:
    """Use the LLM to compose a natural language advisory reply."""
    resolved = state.get("resolved_sops")
    metrics = state.get("metrics", {})
    location = state.get("location", {})
    intent = state.get("intent")
    messages = state.get("messages", [])

    metric_values = metrics.get("metrics", {}) if isinstance(metrics, dict) else {}

    primary = resolved.primary if resolved else None
    primary_guidance = ""
    if primary:
        if primary.rubric_guidance:
            primary_guidance = _fill_placeholders(primary.rubric_guidance, metric_values)
        else:
            primary_guidance = _fill_placeholders(primary.sop.guidance, metric_values)

    secondary_list = []
    if resolved:
        for sec in resolved.secondary:
            if sec.rubric_guidance:
                g = _fill_placeholders(sec.rubric_guidance, metric_values)
            else:
                g = _fill_placeholders(sec.sop.guidance, metric_values)
            secondary_list.append({
                "title": sec.sop.title,
                "severity": sec.sop.severity,
                "guidance": g,
            })

    draft = compose_advisory_reply(
        user_question=messages[-1].content if messages else "",
        primary_title=primary.sop.title if primary else "",
        primary_severity=primary.sop.severity if primary else "",
        primary_guidance=primary_guidance,
        primary_verdict=primary.verdict if primary else None,
        secondary_sops=secondary_list,
        metric_values=metric_values,
        location_name=location.get("name", "") if isinstance(location, dict) else "",
        time_window=intent.time_window if intent else "now",
        window_description=metrics.get("window_description", "") if isinstance(metrics, dict) else "",
    )

    return {
        "draft_reply": draft,
        "route": state.get("route", []) + ["compose_reply"],
    }


def check_grounding_node(state: dict) -> dict:
    """Check grounding and update state."""
    metrics = state.get("metrics", {})
    messages = state.get("messages", [])
    metric_values = metrics.get("metrics", {}) if isinstance(metrics, dict) else {}

    result = check_grounding(
        draft=state.get("draft_reply", ""),
        metric_values=metric_values,
        sop_thresholds=_collect_thresholds(state),
        user_message=messages[-1].content if messages else "",
    )

    if result["passed"]:
        final_reply = _add_citation(state)
        return {
            "final_reply": final_reply,
            "grounding_attempts": state.get("grounding_attempts", 0) + 1,
            "route": state.get("route", []) + ["check_grounding"],
            "messages": [AIMessage(content=final_reply)],
        }
    else:
        return {
            "grounding_attempts": state.get("grounding_attempts", 0) + 1,
            "route": state.get("route", []) + ["check_grounding_fail"],
        }


def route_after_grounding_check(state: dict) -> str:
    """Route after grounding check node."""
    route = state.get("route", [])

    # If last route entry is "check_grounding" (not "check_grounding_fail"), grounding passed
    if route and route[-1] == "check_grounding":
        return "__end__"

    # Check if we already retried
    if state.get("grounding_attempts", 0) > 1:
        return "template_reply"

    return "compose_reply"


# --- Node: template_reply (fixed text, no LLM) ---

def template_reply(state: dict) -> dict:
    """Fallback template reply when grounding fails twice."""
    resolved = state.get("resolved_sops")
    metrics = state.get("metrics", {})
    metric_values = metrics.get("metrics", {}) if isinstance(metrics, dict) else {}

    primary = resolved.primary if resolved else None

    if not primary:
        reply = "Unable to compose a verified response. Please try again."
    else:
        severity_label = primary.sop.severity.upper()
        title = primary.sop.title

        guidance = primary.sop.guidance
        if primary.rubric_guidance:
            guidance = primary.rubric_guidance
        guidance = _fill_placeholders(guidance, metric_values)

        facts_lines = []
        for key, value in sorted(metric_values.items()):
            if value is not None:
                facts_lines.append(f"  {key}: {value}")

        reply = (
            f"⚠️ [{severity_label}] {title}\n\n"
            f"{guidance.strip()}\n\n"
            f"Weather facts:\n"
            + "\n".join(facts_lines)
        )

    final_reply = reply + "\n\n" + _build_citation(state)

    return {
        "final_reply": final_reply,
        "route": state.get("route", []) + ["template_reply"],
        "messages": [AIMessage(content=final_reply)],
    }


# --- Helper functions ---

def _collect_thresholds(state: dict) -> list[float]:
    """Collect all threshold values from matched SOPs."""
    thresholds = []
    resolved = state.get("resolved_sops")
    if resolved:
        all_details = []
        if resolved.primary:
            all_details.append(resolved.primary)
        all_details.extend(resolved.secondary)
        for detail in all_details:
            if hasattr(detail.sop.match, 'conditions'):
                for cond in detail.sop.match.conditions:
                    if isinstance(cond.value, list):
                        thresholds.extend(cond.value)
                    elif isinstance(cond.value, (int, float)):
                        thresholds.append(float(cond.value))
    return thresholds


def _build_citation(state: dict) -> str:
    """Build the citation line (appended by code, never by the LLM)."""
    resolved = state.get("resolved_sops")
    location = state.get("location")
    forecast = state.get("forecast")
    intent = state.get("intent")

    parts = []

    if resolved and resolved.primary:
        primary = resolved.primary.sop
        parts.append(
            f"Policy: {primary.id} {primary.title} (v{primary.version})"
        )
        if resolved.secondary:
            also = ", ".join(f"{s.sop.id}" for s in resolved.secondary)
            parts.append(f"Also applies: {also}")

    if location and isinstance(location, dict):
        lat = location.get("latitude", "?")
        lon = location.get("longitude", "?")
        name = location.get("name", "?")
        parts.append(f"Weather: Open-Meteo, {name} ({lat}, {lon})")

    if forecast and isinstance(forecast, dict):
        parts.append(f"fetched {forecast.get('fetched_at', '?')}")

    if intent:
        parts.append(f"window {intent.time_window}")

    return " | ".join(parts)


def _add_citation(state: dict) -> str:
    """Add citation to the draft reply."""
    draft = state.get("draft_reply", "")
    citation = _build_citation(state)
    return f"{draft}\n\n---\n{citation}"
