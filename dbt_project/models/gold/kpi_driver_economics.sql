{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='economics_day_id', on_schema_change='fail') }}

select
    md5(concat_ws('||', hvfhs_license_num, dispatching_base_num, cast(pickup_datetime as date))) as economics_day_id,
    hvfhs_license_num, dispatching_base_num, cast(pickup_datetime as date) as service_date, count(*) as trip_count,
    sum(trip_miles) as trip_miles_total, sum(actual_trip_seconds) / 60.0 as trip_minutes_total,
    sum(base_passenger_fare) as base_passenger_fare_total, sum(driver_pay) as driver_pay_total,
    sum(platform_take_approx) as platform_take_approx_total,
    sum(driver_pay) / nullif(sum(trip_miles), 0) as driver_pay_per_mile,
    sum(driver_pay) / nullif(sum(actual_trip_seconds) / 60.0, 0) as driver_pay_per_minute,
    sum(platform_take_approx) / nullif(sum(base_passenger_fare), 0) as platform_take_rate_approx,
    sum(tips) as tips_total, ingestion_month
from {{ ref('fct_trips') }}
where {{ month_filter('ingestion_month') }}
group by hvfhs_license_num, dispatching_base_num, cast(pickup_datetime as date), ingestion_month
