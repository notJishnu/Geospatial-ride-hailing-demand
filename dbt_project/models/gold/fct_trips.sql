{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='trip_id', on_schema_change='fail') }}

select
    trips.trip_id, trips.hvfhs_license_num, trips.dispatching_base_num, trips.originating_base_num,
    trips.request_datetime, trips.on_scene_datetime, trips.pickup_datetime, trips.dropoff_datetime,
    date_trunc('hour', trips.pickup_datetime) as pickup_date_hour,
    trips.pickup_zone_id, trips.dropoff_zone_id, trips.pickup_borough, trips.dropoff_borough,
    trips.pickup_zone_name, trips.dropoff_zone_name, trips.is_unknown_or_outside_nyc,
    trips.trip_miles, trips.reported_trip_seconds, trips.actual_trip_seconds, trips.wait_seconds,
    trips.driver_arrival_delay_seconds, trips.average_speed_mph, trips.base_passenger_fare,
    trips.tolls, trips.bcf, trips.sales_tax, trips.congestion_surcharge, trips.airport_fee, trips.tips,
    trips.driver_pay, trips.base_passenger_fare - trips.driver_pay as platform_take_approx,
    trips.driver_pay / nullif(trips.trip_miles, 0) as driver_pay_per_mile,
    trips.driver_pay / nullif(trips.actual_trip_seconds / 60.0, 0) as driver_pay_per_minute,
    trips.shared_request_flag = 'Y' as is_shared_request,
    trips.shared_match_flag = 'Y' as is_shared_match,
    trips.access_a_ride_flag = 'Y' as is_access_a_ride,
    trips.wav_request_flag = 'Y' as is_wav_request,
    trips.wav_match_flag = 'Y' as is_wav_match,
    calendar.is_holiday, calendar.holiday_name, calendar.event_name,
    weather.temperature_2m_c, weather.precipitation_mm, weather.snowfall_cm, weather.wind_speed_10m_kmh,
    trips.ingestion_year, trips.ingestion_month_number, trips.ingestion_month
from {{ ref('silver_trips_valid') }} as trips
left join {{ ref('silver_weather_hourly') }} as weather
    on date_trunc('hour', trips.pickup_datetime) = weather.weather_datetime_local
left join {{ ref('stg_calendar_dates') }} as calendar
    on cast(trips.pickup_datetime as date) = calendar.calendar_date
where {{ month_filter('trips.ingestion_month') }}
