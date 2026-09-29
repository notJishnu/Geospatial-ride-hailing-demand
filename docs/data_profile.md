# HVFHV Data Profile — 2024-01

Generated 2026-09-29T11:54:47.626100+00:00 from immutable Bronze source `data\bronze\hvfhv\year=2024\month=01\fhvhv_tripdata_2024-01.parquet`. This is descriptive profiling, not causal analysis.

## Volume and time coverage

| Metric | Value |
|---|---:|
| Rows | 19,663,930 |
| Earliest request | 2023-12-31 23:01:55 |
| Latest request | 2024-02-01 00:07:07 |
| Composite-key duplicate rows | 4 (0.0000%) |

## Candidate cleaning-rule evidence

| Check | Rows | Rate |
|---|---:|---:|
| Non-positive duration | 2 | 0.0000% |
| Duration outside 60 sec–6 hr | 1,730 | 0.0088% |
| Miles outside (0, 200) | 3,385 | 0.0172% |
| Speed ≥80 mph | 27 | 0.0001% |
| Negative passenger fare | 191 | 0.0010% |
| Negative driver pay | 137 | 0.0007% |
| Actual vs reported duration differs by >60 sec | 0 | 0.0000% |

Observed percentiles: duration p01/p50/p99 = 191.0/912.0/3794.0 seconds; miles p01/p50/p99 = 0.47/2.83/26.38; speed p99 = 38.11 mph.

Recommendation: retain the configured thresholds as initial Silver quarantine rules, not silent drops. Confirm final thresholds after more months and explicitly handle zone IDs 264/265 as unknown/outside-NYC categories.

## Zone checks

| Check | Rows | Rate |
|---|---:|---:|
| pickup_not_in_lookup | 0 | 0.0000% |
| dropoff_not_in_lookup | 0 | 0.0000% |
| pickup_unknown_or_outside | 765 | 0.0039% |
| dropoff_unknown_or_outside | 741,161 | 3.7691% |

## Ten busiest pickup zones

| Pickup zone ID | Trips |
|---:|---:|
| 132 | 374,293 |
| 138 | 345,116 |
| 79 | 269,982 |
| 61 | 256,556 |
| 230 | 246,353 |
| 161 | 242,893 |
| 231 | 232,205 |
| 68 | 219,684 |
| 246 | 218,496 |
| 234 | 218,090 |

## Schema

| Column | DuckDB type |
|---|---|
| `hvfhs_license_num` | `VARCHAR` |
| `dispatching_base_num` | `VARCHAR` |
| `originating_base_num` | `VARCHAR` |
| `request_datetime` | `TIMESTAMP` |
| `on_scene_datetime` | `TIMESTAMP` |
| `pickup_datetime` | `TIMESTAMP` |
| `dropoff_datetime` | `TIMESTAMP` |
| `PULocationID` | `INTEGER` |
| `DOLocationID` | `INTEGER` |
| `trip_miles` | `DOUBLE` |
| `trip_time` | `BIGINT` |
| `base_passenger_fare` | `DOUBLE` |
| `tolls` | `DOUBLE` |
| `bcf` | `DOUBLE` |
| `sales_tax` | `DOUBLE` |
| `congestion_surcharge` | `DOUBLE` |
| `airport_fee` | `DOUBLE` |
| `tips` | `DOUBLE` |
| `driver_pay` | `DOUBLE` |
| `shared_request_flag` | `VARCHAR` |
| `shared_match_flag` | `VARCHAR` |
| `access_a_ride_flag` | `VARCHAR` |
| `wav_request_flag` | `VARCHAR` |
| `wav_match_flag` | `VARCHAR` |
| `month` | `VARCHAR` |
| `year` | `BIGINT` |

## Null counts

| Column | Null rows | Rate |
|---|---:|---:|
| `hvfhs_license_num` | 0 | 0.0000% |
| `dispatching_base_num` | 0 | 0.0000% |
| `originating_base_num` | 5,218,737 | 26.5396% |
| `request_datetime` | 0 | 0.0000% |
| `on_scene_datetime` | 5,218,737 | 26.5396% |
| `pickup_datetime` | 0 | 0.0000% |
| `dropoff_datetime` | 0 | 0.0000% |
| `PULocationID` | 0 | 0.0000% |
| `DOLocationID` | 0 | 0.0000% |
| `trip_miles` | 0 | 0.0000% |
| `trip_time` | 0 | 0.0000% |
| `base_passenger_fare` | 0 | 0.0000% |
| `tolls` | 0 | 0.0000% |
| `bcf` | 0 | 0.0000% |
| `sales_tax` | 0 | 0.0000% |
| `congestion_surcharge` | 0 | 0.0000% |
| `airport_fee` | 0 | 0.0000% |
| `tips` | 0 | 0.0000% |
| `driver_pay` | 0 | 0.0000% |
| `shared_request_flag` | 0 | 0.0000% |
| `shared_match_flag` | 0 | 0.0000% |
| `access_a_ride_flag` | 0 | 0.0000% |
| `wav_request_flag` | 0 | 0.0000% |
| `wav_match_flag` | 0 | 0.0000% |
| `month` | 0 | 0.0000% |
| `year` | 0 | 0.0000% |

## Limitations

TLC location fields are zone IDs, not GPS coordinates, and no driver or rider identities are present. These checks identify data-quality patterns only; they do not establish causes.
