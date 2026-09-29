{{ config(materialized='incremental', incremental_strategy='delete+insert', unique_key='weather_datetime_local', on_schema_change='fail') }}

select
    weather_datetime_local,
    temperature_2m_c,
    precipitation_mm,
    snowfall_cm,
    wind_speed_10m_kmh,
    timezone,
    ingestion_year,
    ingestion_month_number,
    ingestion_month
from {{ ref('stg_weather_hourly') }}
where {{ month_filter('ingestion_month') }}
