"""
LangGraph graph construction and run_turn entry point.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import GraphState, SessionFacts
from app.graph.nodes import (
    parse_intent,
    route_after_intent,
    scope_reply,
    ask_location,
    resolve_location,
    route_after_location,
    fetch_weather_node,
    route_after_weather,
    match_sops_node,
    route_after_match,
    no_sop_reply,
    compose_reply,
    check_grounding_node,
    route_after_grounding_check,
    template_reply,
    honest_failure,
)


def build_graph() -> StateGraph:
    """
    Build the LangGraph graph for the weather advisory bot.

    Graph shape:
        parse_intent
          |-- off-topic ---------> scope_reply --> END
          |-- no location -------> ask_location --> END
          '--> resolve_location
                 |-- fail --------> honest_failure --> END
                 '--> fetch_weather
                        |-- fail --> honest_failure --> END
                        '--> match_sops
                               |-- none --> no_sop_reply --> END
                               '--> compose_reply --> check_grounding
                                                        |-- pass --> END
                                                        |-- retry --> compose_reply
                                                        '--> template_reply --> END
    """
    graph = StateGraph(GraphState)

    # Add nodes
    graph.add_node("parse_intent", parse_intent)
    graph.add_node("scope_reply", scope_reply)
    graph.add_node("ask_location", ask_location)
    graph.add_node("resolve_location", resolve_location)
    graph.add_node("fetch_weather", fetch_weather_node)
    graph.add_node("match_sops", match_sops_node)
    graph.add_node("no_sop_reply", no_sop_reply)
    graph.add_node("compose_reply", compose_reply)
    graph.add_node("check_grounding", check_grounding_node)
    graph.add_node("template_reply", template_reply)
    graph.add_node("honest_failure", honest_failure)

    # Set entry point
    graph.set_entry_point("parse_intent")

    # Add edges
    graph.add_conditional_edges(
        "parse_intent",
        route_after_intent,
        {
            "scope_reply": "scope_reply",
            "ask_location": "ask_location",
            "resolve_location": "resolve_location",
        },
    )

    graph.add_edge("scope_reply", END)
    graph.add_edge("ask_location", END)

    graph.add_conditional_edges(
        "resolve_location",
        route_after_location,
        {
            "honest_failure": "honest_failure",
            "fetch_weather": "fetch_weather",
        },
    )

    graph.add_conditional_edges(
        "fetch_weather",
        route_after_weather,
        {
            "honest_failure": "honest_failure",
            "fetch_weather": "fetch_weather",
            "match_sops": "match_sops",
        },
    )

    graph.add_conditional_edges(
        "match_sops",
        route_after_match,
        {
            "no_sop_reply": "no_sop_reply",
            "compose_reply": "compose_reply",
        },
    )

    graph.add_edge("no_sop_reply", END)
    graph.add_edge("honest_failure", END)

    graph.add_edge("compose_reply", "check_grounding")

    graph.add_conditional_edges(
        "check_grounding",
        route_after_grounding_check,
        {
            "__end__": END,
            "compose_reply": "compose_reply",
            "template_reply": "template_reply",
        },
    )

    graph.add_edge("template_reply", END)

    return graph


# In-memory checkpointer (resets on restart — that's intentional)
_checkpointer = MemorySaver()
_compiled_graph = None


def _get_compiled_graph():
    """Get or compile the graph (lazy singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_graph()
        _compiled_graph = graph.compile(checkpointer=_checkpointer)
    return _compiled_graph


def run_turn(session_id: str, user_message: str, user_coords: dict = None) -> dict:
    """
    Run one conversation turn.

    Args:
        session_id: Session/thread ID for memory.
        user_message: The user's message text.
        user_coords: Optional dict with 'latitude' and 'longitude' from browser geolocation.

    Returns:
        Dict with 'reply' and 'trace' keys.
    """
    from langchain_core.messages import HumanMessage

    compiled = _get_compiled_graph()

    config = {"configurable": {"thread_id": session_id}}

    # Build initial state
    initial_state = {"messages": [HumanMessage(content=user_message)]}
    if user_coords:
        initial_state["user_coords"] = user_coords

    # Invoke the graph
    result = compiled.invoke(
        initial_state,
        config=config,
    )

    # Extract reply
    final_reply = result.get("final_reply", "I'm sorry, something went wrong.")

    # Build trace
    trace = {
        "route": result.get("route", []),
        "intent": None,
        "matched_sops": [],
        "skipped_sops": [],
        "grounding_attempts": result.get("grounding_attempts", 0),
        "metrics": None,
    }

    if result.get("intent"):
        intent = result["intent"]
        trace["intent"] = {
            "location": intent.location,
            "activity": intent.activity,
            "groups": intent.groups,
            "time_window": intent.time_window,
            "in_scope": intent.in_scope,
        }

    if result.get("match_result"):
        match_result = result["match_result"]
        for m in match_result.matched:
            trace["matched_sops"].append({
                "id": m.sop.id,
                "title": m.sop.title,
                "severity": m.sop.severity,
                "conditions": [
                    {
                        "metric": c.metric,
                        "op": c.op,
                        "threshold": c.threshold,
                        "actual": c.actual_value,
                        "passed": c.passed,
                    }
                    for c in m.conditions_fired
                ],
                "verdict": m.verdict,
                "points": m.total_points,
            })
        for s in match_result.skipped:
            trace["skipped_sops"].append({
                "id": s.sop.id,
                "title": s.sop.title,
                "reason": s.skip_reason,
            })

    if result.get("metrics"):
        trace["metrics"] = result["metrics"]["metrics"]
        trace["window_description"] = result["metrics"].get("window_description", "")

    # Extract weather_code for frontend overlay (Step 4)
    # Use current weather code from forecast, or dominant code from metrics
    weather_code = None
    forecast = result.get("forecast")
    if forecast and isinstance(forecast, dict):
        raw = forecast.get("raw", {})
        current = raw.get("current", {})
        weather_code = current.get("weather_code")

    # Fallback: check if metrics has it
    if weather_code is None and result.get("metrics"):
        metrics = result["metrics"].get("metrics", {})
        if metrics.get("has_thunderstorm"):
            weather_code = 95
        elif metrics.get("dominant_weather_code") is not None:
            weather_code = metrics["dominant_weather_code"]

    trace["weather_code"] = weather_code

    # Update session facts for next turn
    _update_session_facts(session_id, result, compiled)

    return {
        "reply": final_reply,
        "trace": trace,
    }


def _update_session_facts(session_id: str, result: dict, compiled):
    """Update session facts after a successful turn."""
    intent = result.get("intent")
    resolved = result.get("resolved_sops")

    if intent:
        # We can't directly update the checkpointed state easily,
        # so we store session facts in a module-level dict
        facts = SessionFacts(
            last_location=intent.location,
            last_activity=intent.activity,
            last_groups=intent.groups,
            last_time_window=intent.time_window,
            last_primary_sop_id=(
                resolved.primary.sop.id
                if resolved and resolved.primary
                else None
            ),
        )
        _session_facts_store[session_id] = facts


def reset_session(session_id: str):
    """Reset a session's memory."""
    _session_facts_store.pop(session_id, None)


# Module-level session facts store
_session_facts_store: dict[str, SessionFacts] = {}


def get_session_facts(session_id: str) -> SessionFacts:
    """Get session facts for a session."""
    return _session_facts_store.get(session_id, SessionFacts())

