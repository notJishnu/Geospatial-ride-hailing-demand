import pandas as pd

from ml.features_eta import build_point_in_time_eta_features, eta_feature_columns


def _eta_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trip_id": ["a", "b", "c", "d"],
            "pickup_datetime": pd.to_datetime(
                ["2024-01-01 08:05", "2024-01-01 08:30", "2024-01-01 09:05", "2024-01-01 10:05"]
            ),
            "pickup_zone_id": [1, 1, 1, 1],
            "dropoff_zone_id": [2, 2, 2, 2],
            "actual_trip_seconds": [600, 900, 1200, 1500],
            "trip_miles": [2.0, 4.0, 6.0, 8.0],
        }
    )


def test_eta_history_only_uses_completed_prior_hours() -> None:
    featured = build_point_in_time_eta_features(_eta_frame())
    assert featured.loc[0, "od_history_count"] == 0
    assert featured.loc[2, "od_history_count"] == 2
    assert featured.loc[2, "historical_od_duration_seconds"] == 750
    assert featured.loc[2, "historical_od_distance_miles"] == 3


def test_future_eta_targets_do_not_change_prior_features() -> None:
    original = build_point_in_time_eta_features(_eta_frame())
    changed = _eta_frame()
    changed.loc[3, ["actual_trip_seconds", "trip_miles"]] = [99_999, 999.0]
    recomputed = build_point_in_time_eta_features(changed)
    pd.testing.assert_frame_equal(original.iloc[:3], recomputed.iloc[:3])


def test_eta_feature_columns_exclude_actual_trip_miles_and_target() -> None:
    featured = build_point_in_time_eta_features(_eta_frame())
    columns = eta_feature_columns(featured)
    assert "trip_miles" not in columns
    assert "actual_trip_seconds" not in columns
    assert "historical_od_distance_miles" in columns
