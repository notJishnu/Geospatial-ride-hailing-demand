from datetime import datetime

from orchestration.dagster_project.assets import month_from_partition_key
from orchestration.dagster_project.definitions import previous_month_partition_key


def test_monthly_partition_converts_to_source_month() -> None:
    assert month_from_partition_key("2024-01-01") == "2024-01"


def test_monthly_schedule_targets_prior_completed_month() -> None:
    scheduled = datetime(2024, 3, 5, 8, 0)
    assert previous_month_partition_key(scheduled) == "2024-02-01"
