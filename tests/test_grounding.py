"""
Tests for the grounding checker.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.compose.grounding import check_grounding


class TestGrounding:
    """Tests for the grounding checker."""

    def test_correct_numbers_pass(self):
        """A draft with only allowed numbers should pass."""
        result = check_grounding(
            draft="Wind gusts are 45.0 km/h and temperature is 32.5 degrees.",
            metric_values={"max_wind_gust": 45.0, "max_apparent_temp": 32.5},
            sop_thresholds=[50.0],
            user_message="Is it safe to cycle?",
        )
        assert result["passed"] is True
        assert len(result["violations"]) == 0

    def test_fake_number_fails(self):
        """A draft with a number not in the data should fail."""
        result = check_grounding(
            draft="Wind gusts are expected to reach 85.0 km/h, which is very dangerous.",
            metric_values={"max_wind_gust": 45.0},
            sop_thresholds=[50.0],
            user_message="Is it safe?",
        )
        assert result["passed"] is False
        assert len(result["violations"]) > 0
        assert any("85.0" in str(v) for v in result["violations"])

    def test_leaked_sop_id_fails(self):
        """A draft containing an SOP ID should fail."""
        result = check_grounding(
            draft="According to SOP-001, you should avoid cycling.",
            metric_values={"max_wind_gust": 45.0},
            sop_thresholds=[50.0],
            user_message="Is it safe?",
        )
        assert result["passed"] is False
        assert any("SOP" in v for v in result["violations"])

    def test_user_typed_numbers_allowed(self):
        """Numbers the user typed should be in the allowed set."""
        result = check_grounding(
            draft="You asked about your 4 year old child.",
            metric_values={},
            sop_thresholds=[],
            user_message="Can my 4 year old play outside?",
        )
        assert result["passed"] is True

    def test_threshold_values_allowed(self):
        """SOP threshold values should be in the allowed set."""
        result = check_grounding(
            draft="Gusts above 50.0 km/h are dangerous for cycling.",
            metric_values={"max_wind_gust": 45.0},
            sop_thresholds=[50.0],
            user_message="Is it safe?",
        )
        assert result["passed"] is True
