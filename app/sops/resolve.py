"""
SOP conflict resolution.

Rules:
1. Any SOP marked lead=True goes first.
2. Remaining SOPs sorted by severity rank descending, then by id for stable order.
3. Primary SOP = first in the resolved list.
4. Secondary SOPs = next up to 2.
5. Info-level "all clear" SOPs are dropped if any higher-severity SOP also matched.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.sops.schema import SEVERITY_RANK
from app.sops.matcher import SOPMatchDetail


@dataclass
class ResolvedSOPs:
    """Result of conflict resolution."""
    primary: SOPMatchDetail | None = None
    secondary: list[SOPMatchDetail] = field(default_factory=list)
    dropped_info: list[SOPMatchDetail] = field(default_factory=list)


def resolve_conflicts(matched: list[SOPMatchDetail]) -> ResolvedSOPs:
    """
    Resolve conflicts among matched SOPs.

    Args:
        matched: List of SOPMatchDetail where matched=True.

    Returns:
        ResolvedSOPs with primary, secondary (max 2), and dropped info SOPs.
    """
    if not matched:
        return ResolvedSOPs()

    # Separate info-level SOPs
    info_sops = [m for m in matched if m.sop.severity == "info"]
    non_info_sops = [m for m in matched if m.sop.severity != "info"]

    # If there are non-info SOPs, drop the info ones
    dropped_info = []
    if non_info_sops:
        dropped_info = info_sops
        working_list = non_info_sops
    else:
        working_list = info_sops

    # Sort: lead SOPs first, then by severity rank descending, then by id
    def sort_key(m: SOPMatchDetail) -> tuple:
        return (
            0 if m.sop.lead else 1,                      # lead first
            -SEVERITY_RANK.get(m.sop.severity, 0),        # highest severity first
            m.sop.id,                                      # stable tie-break
        )

    working_list.sort(key=sort_key)

    primary = working_list[0] if working_list else None
    secondary = working_list[1:3]  # max 2

    return ResolvedSOPs(
        primary=primary,
        secondary=secondary,
        dropped_info=dropped_info,
    )
