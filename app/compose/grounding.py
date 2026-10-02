"""
Grounding checker.

Verifies that every number in the LLM's draft reply exists in the
weather data or SOP thresholds. Also catches leaked SOP IDs.
"""

from __future__ import annotations

import re
from typing import Any


def _extract_numbers(text: str) -> list[float]:
    """
    Extract all numbers from text.

    Handles: 12, 12.5, 12%, "12 km/h", -5.3, etc.
    """
    # Match integers and decimals, possibly negative, possibly followed by units
    pattern = r'-?\d+\.?\d*'
    matches = re.findall(pattern, text)
    return [float(m) for m in matches]


def _build_allowed_set(
    metric_values: dict[str, Any],
    sop_thresholds: list[float],
    user_numbers: list[float],
) -> set[float]:
    """Build the set of allowed numbers."""
    allowed = set()

    # Add metric values (rounded to 0 and 1 decimal)
    for key, value in metric_values.items():
        if value is not None and isinstance(value, (int, float)):
            allowed.add(float(value))
            allowed.add(round(float(value), 1))
            allowed.add(round(float(value), 0))

    # Add SOP threshold values
    for t in sop_thresholds:
        allowed.add(float(t))
        allowed.add(round(float(t), 1))
        allowed.add(round(float(t), 0))

    # Add user-typed numbers
    for n in user_numbers:
        allowed.add(n)

    # Add common contextual numbers (hours, years, etc.)
    # Time-related numbers that are not weather data
    for h in range(0, 25):
        allowed.add(float(h))
    # Common durations / context
    allowed.add(30.0)  # "30 minutes"
    allowed.add(15.0)  # "15 minutes"
    allowed.add(60.0)  # "60 minutes"

    return allowed


def check_grounding(
    draft: str,
    metric_values: dict[str, Any],
    sop_thresholds: list[float],
    user_message: str,
) -> dict[str, Any]:
    """
    Check that all numbers in the draft reply are grounded in data.

    Also checks for leaked SOP IDs.

    Args:
        draft: The LLM's draft reply text.
        metric_values: Dict of metric name -> value.
        sop_thresholds: List of threshold values from matched SOPs.
        user_message: The user's original message.

    Returns:
        Dict with:
            - passed: bool
            - violations: list of strings describing violations
    """
    violations = []

    # Check for leaked SOP IDs
    sop_pattern = r'SOP-\d+'
    sop_matches = re.findall(sop_pattern, draft, re.IGNORECASE)
    if sop_matches:
        violations.append(
            f"Draft contains SOP ID(s): {', '.join(sop_matches)}. "
            f"SOP citations are added by code, not the LLM."
        )

    # Extract numbers from draft and user message
    draft_numbers = _extract_numbers(draft)
    user_numbers = _extract_numbers(user_message)

    # Build allowed set
    allowed = _build_allowed_set(metric_values, sop_thresholds, user_numbers)

    # Check each number in the draft
    ungrounded = []
    for num in draft_numbers:
        if num not in allowed:
            # Check with some tolerance for floating point
            found = False
            for a in allowed:
                if abs(num - a) < 0.15:
                    found = True
                    break
            if not found:
                ungrounded.append(num)

    if ungrounded:
        violations.append(
            f"Ungrounded numbers in draft: {ungrounded}. "
            f"Only numbers from weather data and SOP thresholds are allowed."
        )

    return {
        "passed": len(violations) == 0,
        "violations": violations,
    }
