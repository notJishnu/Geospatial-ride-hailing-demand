{{ config(materialized='table') }}

select
    weather.weather_datetime_local as date_hour,
    cast(weather.weather_datetime_local as date) as calendar_date,
    extract(hour from weather.weather_datetime_local) as hour_of_day,
    extract(dow from weather.weather_datetime_local) as day_of_week,
    extract(dow from weather.weather_datetime_local) in (0, 6) as is_weekend,
    calendar.is_holiday,
    calendar.holiday_name,
    calendar.event_name,
    calendar.event_borough,
    calendar.event_notes,
    weather.temperature_2m_c,
    weather.precipitation_mm,
    weather.snowfall_cm,
    weather.wind_speed_10m_kmh,
    weather.timezone,
    weather.ingestion_month
from {{ ref('silver_weather_hourly') }} as weather
left join {{ ref('stg_calendar_dates') }} as calendar
    on cast(weather.weather_datetime_local as date) = calendar.calendar_date
