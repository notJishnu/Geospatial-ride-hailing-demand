import pandas as pd

from ml.features import build_demand_features


def test_demand_lag_never_reads_current_target() -> None:
    frame = pd.DataFrame(
        {
            "zone_id": [1, 1, 1],
            "date_hour": pd.date_range("2024-01-01", periods=3, freq="h"),
            "trip_count": [10, 20, 30],
        }
    )
    featured = build_demand_features(frame, lags=[1], rolling_windows=[2])
    assert pd.isna(featured.loc[0, "lag_1h"])
    assert featured.loc[1, "lag_1h"] == 10
    assert featured.loc[2, "rolling_mean_2h"] == 15
