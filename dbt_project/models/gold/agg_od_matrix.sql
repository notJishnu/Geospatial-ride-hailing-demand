{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='od_hour_id', on_schema_change='fail') }}

select
    md5(concat_ws('||', cast(pickup_zone_id as varchar), cast(dropoff_zone_id as varchar), cast(pickup_date_hour as varchar))) as od_hour_id,
    pickup_zone_id, dropoff_zone_id, pickup_date_hour as date_hour, count(*) as trip_count,
    avg(actual_trip_seconds) as average_trip_seconds, avg(trip_miles) as average_trip_miles,
    avg(base_passenger_fare) as average_base_passenger_fare, ingestion_month
from {{ ref('fct_trips') }}
where pickup_zone_id not in (264, 265) and dropoff_zone_id not in (264, 265)
  and {{ month_filter('ingestion_month') }}
group by pickup_zone_id, dropoff_zone_id, pickup_date_hour, ingestion_month
