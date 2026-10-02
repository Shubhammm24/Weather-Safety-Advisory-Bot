"""
Tests for the SOP matcher and conflict resolution.

Each test uses a hand-made fixture — no network calls.
"""

import sys
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sops.loader import load_sops
from app.sops.metrics import compute_metrics
from app.sops.matcher import match_sops
from app.sops.resolve import resolve_conflicts
from tests.fixtures.weather_fixtures import (
    calm_day,
    high_wind,
    high_uv_noon,
    heavy_multiday_rain,
    thunderstorm,
    missing_uv,
    extreme_heat,
    high_wind_and_uv,
)


@pytest.fixture
def sops():
    """Load all SOPs."""
    return load_sops()


class TestMetrics:
    """Test metric computation from fixtures."""

    @patch("app.sops.metrics.datetime")
    def test_calm_day_metrics(self, mock_dt):
        """Calm day should have low values across the board."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(calm_day(), "today")
        m = metrics_result["metrics"]

        assert m["max_wind_gust"] == 10.0
        assert m["max_precip_prob"] == 0
        assert m["has_thunderstorm"] is False
        assert m["total_precip"] == 0.0

    @patch("app.sops.metrics.datetime")
    def test_high_wind_metrics(self, mock_dt):
        """High wind fixture should show gusts at 60."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(high_wind(), "today")
        m = metrics_result["metrics"]

        assert m["max_wind_gust"] >= 55.0
        assert m["max_wind_speed"] >= 40.0

    @patch("app.sops.metrics.datetime")
    def test_thunderstorm_detection(self, mock_dt):
        """Thunderstorm fixture should set has_thunderstorm=True."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(thunderstorm(), "today")
        m = metrics_result["metrics"]

        assert m["has_thunderstorm"] is True


class TestMatcher:
    """Test SOP matching against fixtures."""

    @patch("app.sops.metrics.datetime")
    def test_calm_day_cycling_matches_all_clear(self, mock_dt, sops):
        """Calm day + cycling should match the exercise all-clear SOP."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(calm_day(), "today")
        result = match_sops(sops, metrics_result["metrics"], "cycling", ["general"])

        matched_ids = {m.sop.id for m in result.matched}
        assert "SOP-011" in matched_ids, (
            f"Expected SOP-011 (exercise all clear). Matched: {matched_ids}"
        )

    @patch("app.sops.metrics.datetime")
    def test_high_wind_cycling_matches_wind_sop(self, mock_dt, sops):
        """High wind + cycling should match the wind SOP (SOP-002)."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(high_wind(), "today")
        result = match_sops(sops, metrics_result["metrics"], "cycling", ["general"])

        matched_ids = {m.sop.id for m in result.matched}
        assert "SOP-002" in matched_ids, (
            f"Expected SOP-002 (high wind). Matched: {matched_ids}"
        )

    @patch("app.sops.metrics.datetime")
    def test_high_uv_running_afternoon_matches_uv_sop(self, mock_dt, sops):
        """High UV at noon + running in afternoon should match UV SOP (SOP-003)."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(high_uv_noon(), "afternoon")
        result = match_sops(sops, metrics_result["metrics"], "running", ["general"])

        matched_ids = {m.sop.id for m in result.matched}
        assert "SOP-003" in matched_ids, (
            f"Expected SOP-003 (UV). Matched: {matched_ids}"
        )

    @patch("app.sops.metrics.datetime")
    def test_heavy_rain_matches_lead_sop(self, mock_dt, sops):
        """Heavy multi-day rain should match lead SOP-001."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(heavy_multiday_rain(), "today")
        result = match_sops(sops, metrics_result["metrics"], "cycling", ["general"])

        matched_ids = {m.sop.id for m in result.matched}
        assert "SOP-001" in matched_ids, (
            f"Expected SOP-001 (heavy rain). Matched: {matched_ids}"
        )

        # Lead SOP should be first in resolved
        resolved = resolve_conflicts(result.matched)
        assert resolved.primary is not None
        assert resolved.primary.sop.id == "SOP-001", (
            f"Expected SOP-001 as primary. Got: {resolved.primary.sop.id}"
        )

    @patch("app.sops.metrics.datetime")
    def test_thunderstorm_matches(self, mock_dt, sops):
        """Thunderstorm should match SOP-005."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(thunderstorm(), "today")
        result = match_sops(sops, metrics_result["metrics"], "walking", ["general"])

        matched_ids = {m.sop.id for m in result.matched}
        assert "SOP-005" in matched_ids, (
            f"Expected SOP-005 (thunderstorm). Matched: {matched_ids}"
        )

    @patch("app.sops.metrics.datetime")
    def test_extreme_heat_elderly_matches_heat_sop(self, mock_dt, sops):
        """Extreme heat + elderly should match SOP-004."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(extreme_heat(), "today")
        result = match_sops(sops, metrics_result["metrics"], "walking", ["elderly"])

        matched_ids = {m.sop.id for m in result.matched}
        assert "SOP-004" in matched_ids, (
            f"Expected SOP-004 (heat vulnerable). Matched: {matched_ids}"
        )

    @patch("app.sops.metrics.datetime")
    def test_conflict_resolution_highest_severity_first(self, mock_dt, sops):
        """When multiple SOPs match, highest severity should be primary."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(high_wind_and_uv(), "today")
        result = match_sops(sops, metrics_result["metrics"], "cycling", ["general"])
        resolved = resolve_conflicts(result.matched)

        assert resolved.primary is not None
        # Wind SOP (high) should be primary over UV SOP (moderate)
        from app.sops.schema import SEVERITY_RANK
        primary_rank = SEVERITY_RANK[resolved.primary.sop.severity]
        for sec in resolved.secondary:
            sec_rank = SEVERITY_RANK[sec.sop.severity]
            assert primary_rank >= sec_rank, (
                f"Primary {resolved.primary.sop.id} ({resolved.primary.sop.severity}) "
                f"should have higher or equal severity than secondary {sec.sop.id} ({sec.sop.severity})"
            )

    @patch("app.sops.metrics.datetime")
    def test_info_sops_dropped_when_higher_severity_present(self, mock_dt, sops):
        """Info SOPs should be dropped when a higher-severity SOP also matches."""
        mock_dt.now.return_value = datetime(2026, 10, 2, 10, 0)
        mock_dt.fromisoformat = datetime.fromisoformat

        metrics_result = compute_metrics(high_wind(), "today")
        result = match_sops(sops, metrics_result["metrics"], "cycling", ["general"])
        resolved = resolve_conflicts(result.matched)

        # Check that no info-level SOPs are in primary or secondary
        if resolved.primary:
            assert resolved.primary.sop.severity != "info"
        for sec in resolved.secondary:
            assert sec.sop.severity != "info"
