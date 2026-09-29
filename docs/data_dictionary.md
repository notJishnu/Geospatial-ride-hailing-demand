# Data Dictionary

## Bronze

`data/bronze/hvfhv/year=YYYY/month=MM/fhvhv_tripdata_YYYY-MM.parquet` is the untouched official TLC source. Download manifests record the source URL, file size, and SHA-256 digest separately under `data/manifests/`.

## Silver tables

### `silver_trips_valid`

One cleaned HVFHV trip per `trip_id`. `actual_trip_seconds` is calculated from `dropoff_datetime - pickup_datetime`; `reported_trip_seconds` preserves TLC's `trip_time` for reconciliation. `wait_seconds` and `driver_arrival_delay_seconds` are nullable when their source timestamps are unavailable. `average_speed_mph` uses reported trip seconds.

`is_unknown_or_outside_nyc` is true when either zone is 264 or 265. Those records are retained because the zones exist in the TLC lookup, but they must be excluded from map and zone-level ML features where a specific NYC geography is required.

### `silver_trips_quarantine`

Every row failed exactly one first-match validation rule, exposed as `reject_reason`. The original Bronze file is never edited or deleted. Reasons include duration, miles, speed, negative monetary values, source-zone lookup failures, boundary-month violations, and composite-key duplicates.

### `silver_weather_hourly`

Hourly Open-Meteo measurements, keyed by local `weather_datetime_local` with the source timezone retained. Weather joins must use NYC local timestamps and require an explicit daylight-saving-time test before production use.

### `silver_zone_geometry`

One TLC zone polygon reference row per `zone_id`, with WGS84 centroid longitude/latitude and an H3 resolution-8 cell calculated from that centroid. This is a zone-level display/indexing aid; it is not individual trip GPS data.

## Gold tables

`fct_trips` retains one validated trip and adds pickup-hour weather, date flags, driver economics, and the documented approximate platform take (`base_passenger_fare - driver_pay`). It is not a verified platform-margin measure.

`dim_zone` exposes zone lookup and display-centroid attributes; `dim_date_hour` provides local-time weather, holiday, and manual-event attributes.

`agg_zone_hour_demand`, `agg_od_matrix`, and `kpi_zone_daily` exclude zone IDs 264/265 from geographic aggregation. `kpi_driver_economics` is grouped by licensed HVFHS base/day, not individual drivers, because the source contains no driver identities.
