{{ config(materialized='view') }}

select
    cast(weather_time_local as timestamp) as weather_datetime_local,
    temperature_2m_c,
    precipitation_mm,
    snowfall_cm,
    wind_speed_10m_kmh,
    timezone,
    year as ingestion_year,
    lpad(month, 2, '0') as ingestion_month_number,
    cast(year as varchar) || '-' || lpad(month, 2, '0') as ingestion_month
from (
    select
        weather_time_local,
        temperature_2m as temperature_2m_c,
        precipitation as precipitation_mm,
        snowfall as snowfall_cm,
        wind_speed_10m as wind_speed_10m_kmh,
        timezone,
        year,
        month
    from read_parquet('{{ var("weather_glob") }}', hive_partitioning = true)
)
