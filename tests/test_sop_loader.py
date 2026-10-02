"""
Tests for SOP loader.

Verifies that:
1. All valid SOP files load successfully.
2. A broken file fails with a clear error message.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sops.loader import load_sops
from app import config


class TestSOPLoader:
    """Tests for the SOP loader."""

    def test_all_sops_load_successfully(self):
        """All SOP files in the sops/ directory should load without errors."""
        sops = load_sops()
        assert len(sops) >= 12, f"Expected at least 12 SOPs, got {len(sops)}"

        # Check that all expected IDs are present
        ids = {s.id for s in sops}
        expected_ids = {f"SOP-{i:03d}" for i in range(1, 13)}
        missing = expected_ids - ids
        assert not missing, f"Missing SOP IDs: {missing}"

    def test_no_duplicate_ids(self):
        """All SOP IDs should be unique."""
        sops = load_sops()
        ids = [s.id for s in sops]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {ids}"

    def test_all_sops_have_required_fields(self):
        """Every SOP should have all required fields."""
        sops = load_sops()
        for sop in sops:
            assert sop.id, f"SOP missing id"
            assert sop.title, f"SOP {sop.id} missing title"
            assert sop.category, f"SOP {sop.id} missing category"
            assert sop.severity, f"SOP {sop.id} missing severity"
            assert sop.guidance, f"SOP {sop.id} missing guidance"
            assert sop.rationale, f"SOP {sop.id} missing rationale"

    def test_severity_spread(self):
        """SOPs should cover multiple severity levels."""
        sops = load_sops()
        severities = {s.severity for s in sops}
        assert len(severities) >= 3, (
            f"Expected at least 3 severity levels, got {severities}"
        )

    def test_broken_file_raises_clear_error(self):
        """A broken YAML file should raise ValueError naming the file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a valid SOP
            valid_path = Path(tmpdir) / "valid.yaml"
            valid_path.write_text("""
id: SOP-TEST
title: Test SOP
version: "1.0"
category: test
severity: info
applies_to:
  activities: ["*"]
  groups: ["*"]
match:
  type: threshold
  combine: all
  conditions:
    - metric: max_wind_gust
      op: "<"
      value: 999
guidance: Test guidance
rationale: Test rationale
""", encoding="utf-8")

            # Write a broken file
            broken_path = Path(tmpdir) / "broken.yaml"
            broken_path.write_text("""
id: SOP-BROKEN
title: Broken
severity: INVALID_SEVERITY
category: test
match:
  type: threshold
  combine: all
  conditions:
    - metric: fake_metric
      op: "<"
      value: 10
guidance: test
rationale: test
""", encoding="utf-8")

            with pytest.raises(ValueError) as exc_info:
                load_sops(Path(tmpdir))

            error_msg = str(exc_info.value)
            assert "broken.yaml" in error_msg, (
                f"Error should name the broken file. Got: {error_msg}"
            )

    def test_empty_directory(self):
        """An empty SOPs directory should return an empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sops = load_sops(Path(tmpdir))
            assert sops == []

    def test_missing_directory_raises(self):
        """A nonexistent directory should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_sops(Path("/nonexistent/path/sops"))
