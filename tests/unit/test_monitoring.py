"""Unit tests for monitoring thresholds without requiring a local warehouse."""

import pytest

from monitoring.dq_checks import eta_mae_alert, quality_status
from monitoring.drift_report import drift_status, find_drift_share, validate_month


def test_quality_status_flags_reject_rate_and_duplicates() -> None:
    alerts = quality_status(reject_rate=0.03, duplicate_trip_ids=2, max_reject_rate=0.02)
    assert len(alerts) == 2
    assert "reject rate" in alerts[0]


def test_drift_status_requires_distinct_months() -> None:
    assert drift_status("2024-01", "2024-01") == "waiting_for_distinct_comparison_month"
    assert drift_status("2024-01", "2024-02") == "ready"


def test_validate_month_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="YYYY-MM"):
        validate_month("January 2024")


def test_eta_mae_alert_uses_configured_tolerance() -> None:
    assert eta_mae_alert(260, 224, 0.15) is not None
    assert eta_mae_alert(250, 224, 0.15) is None


def test_find_drift_share_handles_evidently_report_structure() -> None:
    assert find_drift_share({"metrics": [{"result": {"share_of_drifted_columns": 0.4}}]}) == 0.4
