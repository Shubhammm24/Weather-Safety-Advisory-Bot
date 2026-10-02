"""
LangGraph state definition for the Weather-Advisory Support Bot.
"""

from __future__ import annotations

from typing import Any, Optional, Literal
from pydantic import BaseModel, Field
from langgraph.graph import MessagesState


class SessionFacts(BaseModel):
    """Persisted facts from previous turns in the same session."""
    last_location: Optional[str] = None
    last_activity: Optional[str] = None
    last_groups: list[str] = Field(default_factory=list)
    last_time_window: Optional[str] = None
    last_primary_sop_id: Optional[str] = None


class IntentResult(BaseModel):
    """Structured output from the intent extraction step."""
    location: Optional[str] = None
    activity: str = "other"
    groups: list[str] = Field(default_factory=lambda: ["general"])
    time_window: str = "now"
    in_scope: bool = True


class GraphState(MessagesState):
    """Full state for the LangGraph graph."""
    # Intent
    intent: Optional[IntentResult] = None
    session_facts: SessionFacts = Field(default_factory=SessionFacts)

    # Location & Weather
    user_coords: Optional[dict[str, float]] = None  # {latitude, longitude} from browser
    location: Optional[dict[str, Any]] = None  # from geocode()
    forecast: Optional[dict[str, Any]] = None   # from fetch_forecast()

    # Matching
    metrics: Optional[dict[str, Any]] = None     # from compute_metrics()
    match_result: Optional[Any] = None           # MatchResult
    resolved_sops: Optional[Any] = None          # ResolvedSOPs

    # Reply
    draft_reply: Optional[str] = None
    final_reply: Optional[str] = None

    # Routing
    error_kind: Optional[str] = None  # "location_not_found", "weather_unavailable"
    route: list[str] = Field(default_factory=list)  # trace of nodes visited
    grounding_attempts: int = 0
