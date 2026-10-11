"""Small, dependency-free checks for dashboard presentation helpers."""

from dashboard.app import as_percent, metric_rows


def test_as_percent() -> None:
    assert as_percent(0.125) == "12.5%"


def test_metric_rows_preserves_metric_names() -> None:
    result = metric_rows({"mae": 2.5, "wape": 0.1})
    assert result.to_dict("records") == [
        {"metric": "mae", "value": 2.5},
        {"metric": "wape", "value": 0.1},
    ]
