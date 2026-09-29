{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='zone_hour_id', on_schema_change='fail') }}

select
    md5(concat_ws('||', cast(pickup_zone_id as varchar), cast(pickup_date_hour as varchar))) as zone_hour_id,
    pickup_zone_id as zone_id, pickup_date_hour as date_hour, count(*) as trip_count,
    avg(wait_seconds) as average_wait_seconds, avg(base_passenger_fare) as average_base_passenger_fare,
    avg(trip_miles) as average_trip_miles, avg(actual_trip_seconds) as average_trip_seconds,
    avg(is_shared_request::integer) as shared_request_share,
    avg(is_shared_match::integer) as shared_match_share,
    sum(driver_pay) as driver_pay_total, sum(platform_take_approx) as platform_take_approx_total,
    max(precipitation_mm) as precipitation_mm, max(is_holiday::integer)::boolean as is_holiday,
    max(event_name) as event_name, ingestion_month
from {{ ref('fct_trips') }}
where pickup_zone_id not in (264, 265) and {{ month_filter('ingestion_month') }}
group by pickup_zone_id, pickup_date_hour, ingestion_month
