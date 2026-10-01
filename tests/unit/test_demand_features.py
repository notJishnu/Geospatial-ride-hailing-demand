import pandas as pd

from ml.features import build_demand_features


def test_demand_lag_never_reads_current_target() -> None:
    frame = pd.DataFrame(
        {
            "zone_id": [1, 1, 1],
            "date_hour": pd.date_range("2024-01-01", periods=3, freq="h"),
            "trip_count": [10, 20, 30],
            "precipitation_mm": [1.0, 2.0, 3.0],
        }
    )
    featured = build_demand_features(frame, lags=[1], rolling_windows=[2])
    assert pd.isna(featured.loc[0, "lag_1h"])
    assert featured.loc[1, "lag_1h"] == 10
    assert featured.loc[2, "rolling_mean_2h"] == 15
    assert featured.loc[2, "precipitation_mm_lag_1h"] == 2.0


def test_future_target_does_not_change_available_features() -> None:
    frame = pd.DataFrame(
        {
            "zone_id": [1, 1, 1, 1],
            "date_hour": pd.date_range("2024-01-01", periods=4, freq="h"),
            "trip_count": [10, 20, 30, 40],
            "precipitation_mm": [0.0, 1.0, 0.0, 2.0],
        }
    )
    original = build_demand_features(frame, lags=[1], rolling_windows=[2])
    changed = frame.copy()
    changed.loc[3, "trip_count"] = 9_999
    recomputed = build_demand_features(changed, lags=[1], rolling_windows=[2])
    pd.testing.assert_frame_equal(original.iloc[:3], recomputed.iloc[:3])
