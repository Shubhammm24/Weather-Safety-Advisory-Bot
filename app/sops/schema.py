"""
Pydantic schema for Standard Operating Procedures (SOPs).

SOPs are YAML data files. This module validates them at load time.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, model_validator


# --- Allowed metrics (computed by code in metrics.py) ---
ALLOWED_METRICS = frozenset([
    "max_precip_prob",
    "total_precip",
    "max_wind_speed",
    "max_wind_gust",
    "max_uv",
    "min_apparent_temp",
    "max_apparent_temp",
    "precip_sum_24h",
    "precip_sum_72h",
    "has_thunderstorm",
])

# --- Allowed activities ---
ALLOWED_ACTIVITIES = frozenset([
    "cycling",
    "two_wheeler",
    "running",
    "walking",
    "hiking",
    "picnic",
    "outdoor_play",
    "travel_road",
    "other",
    "*",  # wildcard
])

# --- Allowed groups ---
ALLOWED_GROUPS = frozenset([
    "children",
    "elderly",
    "pets",
    "general",
    "*",  # wildcard
])

# --- Allowed severity levels ---
ALLOWED_SEVERITIES = frozenset(["info", "low", "moderate", "high", "critical"])

SEVERITY_RANK = {
    "info": 0,
    "low": 1,
    "moderate": 2,
    "high": 3,
    "critical": 4,
}

# --- Allowed operators ---
ALLOWED_OPS = frozenset([">", ">=", "<", "<=", "between", "=="])


class ThresholdCondition(BaseModel):
    """A single condition in a threshold-based SOP match."""
    metric: str
    op: str
    value: Union[float, int, bool, list[float]]  # list for 'between'

    @model_validator(mode="after")
    def validate_condition(self):
        if self.metric not in ALLOWED_METRICS:
            raise ValueError(
                f"Unknown metric '{self.metric}'. "
                f"Allowed: {sorted(ALLOWED_METRICS)}"
            )
        if self.op not in ALLOWED_OPS:
            raise ValueError(
                f"Unknown operator '{self.op}'. Allowed: {sorted(ALLOWED_OPS)}"
            )
        if self.op == "between":
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError(
                    "'between' operator requires a list of exactly 2 values."
                )
        return self


class ThresholdMatch(BaseModel):
    """Threshold-based matching: all/any conditions must be true."""
    type: Literal["threshold"] = "threshold"
    combine: Literal["all", "any"] = "all"
    conditions: list[ThresholdCondition]


class RubricCriterion(BaseModel):
    """A single criterion in a rubric-based SOP."""
    metric: str
    op: str
    value: Union[float, int, bool, list[float]]
    points: int

    @model_validator(mode="after")
    def validate_criterion(self):
        if self.metric not in ALLOWED_METRICS:
            raise ValueError(
                f"Unknown metric '{self.metric}'. "
                f"Allowed: {sorted(ALLOWED_METRICS)}"
            )
        if self.op not in ALLOWED_OPS:
            raise ValueError(
                f"Unknown operator '{self.op}'. Allowed: {sorted(ALLOWED_OPS)}"
            )
        return self


class RubricBand(BaseModel):
    """A score band for rubric-based SOPs."""
    min_points: int
    max_points: int
    verdict: str
    guidance: str


class RubricMatch(BaseModel):
    """Rubric-based matching: sum points from criteria, pick a band."""
    type: Literal["rubric"] = "rubric"
    criteria: list[RubricCriterion]
    bands: list[RubricBand]


class AppliesTo(BaseModel):
    """Specifies which activities and groups an SOP targets."""
    activities: list[str] = Field(default=["*"])
    groups: list[str] = Field(default=["*"])

    @model_validator(mode="after")
    def validate_applies_to(self):
        for act in self.activities:
            if act not in ALLOWED_ACTIVITIES:
                raise ValueError(
                    f"Unknown activity '{act}'. "
                    f"Allowed: {sorted(ALLOWED_ACTIVITIES)}"
                )
        for grp in self.groups:
            if grp not in ALLOWED_GROUPS:
                raise ValueError(
                    f"Unknown group '{grp}'. "
                    f"Allowed: {sorted(ALLOWED_GROUPS)}"
                )
        return self


class SOPDefinition(BaseModel):
    """
    A Standard Operating Procedure definition.

    SOPs are stored as YAML files and loaded/validated at request time.
    """
    id: str
    title: str
    version: str = "1.0"
    category: str
    severity: str
    lead: bool = False
    applies_to: AppliesTo = Field(default_factory=AppliesTo)
    match: Union[ThresholdMatch, RubricMatch] = Field(discriminator="type")
    guidance: str
    rationale: str

    @model_validator(mode="after")
    def validate_sop(self):
        if self.severity not in ALLOWED_SEVERITIES:
            raise ValueError(
                f"Unknown severity '{self.severity}'. "
                f"Allowed: {sorted(ALLOWED_SEVERITIES)}"
            )
        return self
