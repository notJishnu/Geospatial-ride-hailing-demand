{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='trip_id', on_schema_change='fail') }}

select
    trip_id,
    reject_reason,
    request_datetime,
    pickup_datetime,
    dropoff_datetime,
    pickup_zone_id,
    dropoff_zone_id,
    trip_miles,
    reported_trip_seconds,
    actual_trip_seconds,
    average_speed_mph,
    base_passenger_fare,
    driver_pay,
    ingestion_year,
    ingestion_month_number,
    ingestion_month
from {{ ref('silver_trips_classified') }}
where reject_reason is not null
  and {{ month_filter('ingestion_month') }}
