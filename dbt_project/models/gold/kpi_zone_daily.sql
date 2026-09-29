{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='zone_day_id', on_schema_change='fail') }}

select
    md5(concat_ws('||', cast(pickup_zone_id as varchar), cast(pickup_datetime as date))) as zone_day_id,
    pickup_zone_id as zone_id, cast(pickup_datetime as date) as service_date, count(*) as trip_count,
    sum(base_passenger_fare) as base_passenger_fare_total, sum(driver_pay) as driver_pay_total,
    sum(platform_take_approx) as platform_take_approx_total, avg(wait_seconds) as average_wait_seconds,
    avg(actual_trip_seconds) as average_trip_seconds, avg(driver_pay_per_mile) as average_driver_pay_per_mile,
    avg(driver_pay_per_minute) as average_driver_pay_per_minute,
    avg(is_shared_request::integer) as shared_request_share, ingestion_month
from {{ ref('fct_trips') }}
where pickup_zone_id not in (264, 265) and {{ month_filter('ingestion_month') }}
group by pickup_zone_id, cast(pickup_datetime as date), ingestion_month
