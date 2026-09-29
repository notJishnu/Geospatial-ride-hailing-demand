import pytest

from ingestion.download_tlc import parse_month


@pytest.mark.parametrize("month", ["2024-01", "2019-12"])
def test_parse_month_accepts_valid_month(month: str) -> None:
    assert parse_month(month) == month


@pytest.mark.parametrize("month", ["2024-00", "2024-13", "January 2024"])
def test_parse_month_rejects_invalid_month(month: str) -> None:
    with pytest.raises(ValueError):
        parse_month(month)
