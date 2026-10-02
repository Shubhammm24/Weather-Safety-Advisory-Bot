"""
SOP matcher: evaluates conditions and rubrics against computed metrics.
Pure Python, no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.sops.schema import (
    SOPDefinition,
    ThresholdMatch,
    RubricMatch,
    ThresholdCondition,
    SEVERITY_RANK,
)


@dataclass
class ConditionResult:
    """Result of evaluating a single condition."""
    metric: str
    op: str
    threshold: Any
    actual_value: Any
    passed: bool
    reason: str = ""


@dataclass
class SOPMatchDetail:
    """Details of how an SOP matched (or didn't)."""
    sop: SOPDefinition
    matched: bool
    conditions_fired: list[ConditionResult] = field(default_factory=list)
    # For rubric SOPs
    total_points: Optional[int] = None
    verdict: Optional[str] = None
    rubric_guidance: Optional[str] = None
    skip_reason: Optional[str] = None


@dataclass
class MatchResult:
    """Complete result of matching all SOPs against metrics."""
    matched: list[SOPMatchDetail] = field(default_factory=list)
    skipped: list[SOPMatchDetail] = field(default_factory=list)


def _evaluate_condition(
    condition: ThresholdCondition, metrics: dict[str, Any]
) -> ConditionResult:
    """Evaluate a single threshold condition against computed metrics."""
    metric_name = condition.metric
    actual = metrics.get(metric_name)

    if actual is None:
        return ConditionResult(
            metric=metric_name,
            op=condition.op,
            threshold=condition.value,
            actual_value=None,
            passed=False,
            reason=f"Metric '{metric_name}' is missing (null/unavailable).",
        )

    op = condition.op
    threshold = condition.value
    passed = False

    if op == ">":
        passed = actual > threshold
    elif op == ">=":
        passed = actual >= threshold
    elif op == "<":
        passed = actual < threshold
    elif op == "<=":
        passed = actual <= threshold
    elif op == "==":
        passed = actual == threshold
    elif op == "between":
        if isinstance(threshold, list) and len(threshold) == 2:
            passed = threshold[0] <= actual <= threshold[1]

    return ConditionResult(
        metric=metric_name,
        op=op,
        threshold=threshold,
        actual_value=actual,
        passed=passed,
    )


def _activity_matches(sop: SOPDefinition, activity: str) -> bool:
    """Check if an SOP applies to the given activity."""
    sop_activities = sop.applies_to.activities
    return "*" in sop_activities or activity in sop_activities


def _group_matches(sop: SOPDefinition, groups: list[str]) -> bool:
    """Check if an SOP applies to any of the given groups."""
    sop_groups = sop.applies_to.groups
    if "*" in sop_groups:
        return True
    return any(g in sop_groups for g in groups)


def match_sops(
    sops: list[SOPDefinition],
    metrics: dict[str, Any],
    activity: str,
    groups: list[str],
) -> MatchResult:
    """
    Match SOPs against computed metrics for a given activity and groups.

    Args:
        sops: List of loaded SOP definitions.
        metrics: Dict of metric_name -> value from compute_metrics().
        activity: The user's activity (from vocabulary).
        groups: The user's groups (from vocabulary).

    Returns:
        MatchResult with matched and skipped SOPs.
    """
    result = MatchResult()

    if not groups:
        groups = ["general"]

    for sop in sops:
        # Filter by activity
        if not _activity_matches(sop, activity):
            result.skipped.append(SOPMatchDetail(
                sop=sop,
                matched=False,
                skip_reason=f"Activity '{activity}' not in {sop.applies_to.activities}",
            ))
            continue

        # Filter by group
        if not _group_matches(sop, groups):
            result.skipped.append(SOPMatchDetail(
                sop=sop,
                matched=False,
                skip_reason=f"Groups {groups} not in {sop.applies_to.groups}",
            ))
            continue

        # Evaluate match
        match_config = sop.match

        if isinstance(match_config, ThresholdMatch):
            conditions_results = [
                _evaluate_condition(cond, metrics)
                for cond in match_config.conditions
            ]

            # Check for missing metrics
            missing = [r for r in conditions_results if r.actual_value is None]
            if missing:
                result.skipped.append(SOPMatchDetail(
                    sop=sop,
                    matched=False,
                    conditions_fired=conditions_results,
                    skip_reason=(
                        f"Metric(s) unavailable: "
                        f"{', '.join(r.metric for r in missing)}"
                    ),
                ))
                continue

            if match_config.combine == "all":
                matched = all(r.passed for r in conditions_results)
            else:  # "any"
                matched = any(r.passed for r in conditions_results)

            detail = SOPMatchDetail(
                sop=sop,
                matched=matched,
                conditions_fired=conditions_results,
            )

            if matched:
                result.matched.append(detail)
            else:
                detail.skip_reason = "Conditions not met"
                result.skipped.append(detail)

        elif isinstance(match_config, RubricMatch):
            total_points = 0
            conditions_results = []

            for criterion in match_config.criteria:
                cond = ThresholdCondition(
                    metric=criterion.metric,
                    op=criterion.op,
                    value=criterion.value,
                )
                cond_result = _evaluate_condition(cond, metrics)
                conditions_results.append(cond_result)

                if cond_result.passed:
                    total_points += criterion.points

            # Find the matching band
            verdict = None
            rubric_guidance = None
            for band in match_config.bands:
                if band.min_points <= total_points <= band.max_points:
                    verdict = band.verdict
                    rubric_guidance = band.guidance
                    break

            # Rubric SOPs always "match" — they produce a verdict
            detail = SOPMatchDetail(
                sop=sop,
                matched=True,
                conditions_fired=conditions_results,
                total_points=total_points,
                verdict=verdict,
                rubric_guidance=rubric_guidance,
            )
            result.matched.append(detail)

    return result
