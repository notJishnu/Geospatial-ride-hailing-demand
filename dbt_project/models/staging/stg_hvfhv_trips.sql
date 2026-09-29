{{ config(materialized='view') }}

with raw_trips as (
    select
        hvfhs_license_num,
        dispatching_base_num,
        originating_base_num,
        request_datetime,
        on_scene_datetime,
        pickup_datetime,
        dropoff_datetime,
        PULocationID as pickup_zone_id,
        DOLocationID as dropoff_zone_id,
        trip_miles,
        trip_time as reported_trip_seconds,
        base_passenger_fare,
        tolls,
        bcf,
        sales_tax,
        congestion_surcharge,
        airport_fee,
        tips,
        driver_pay,
        shared_request_flag,
        shared_match_flag,
        access_a_ride_flag,
        wav_request_flag,
        wav_match_flag,
        year as ingestion_year,
        lpad(month, 2, '0') as ingestion_month_number
    from read_parquet('{{ var("bronze_hvfhv_glob") }}', hive_partitioning = true)
),

typed as (
    select
        *,
        cast(ingestion_year as varchar) || '-' || ingestion_month_number as ingestion_month,
        datediff('second', pickup_datetime, dropoff_datetime) as actual_trip_seconds,
        datediff('second', request_datetime, pickup_datetime) as wait_seconds,
        datediff('second', request_datetime, on_scene_datetime) as driver_arrival_delay_seconds,
        trip_miles / nullif(reported_trip_seconds / 3600.0, 0) as average_speed_mph,
        row_number() over (
            partition by
                hvfhs_license_num,
                request_datetime,
                pickup_datetime,
                pickup_zone_id,
                dropoff_zone_id,
                base_passenger_fare
            order by dropoff_datetime, dispatching_base_num, driver_pay
        ) as duplicate_rank
    from raw_trips
)

select
    md5(concat_ws('||',
        coalesce(hvfhs_license_num, ''),
        coalesce(cast(request_datetime as varchar), ''),
        coalesce(cast(pickup_datetime as varchar), ''),
        coalesce(cast(pickup_zone_id as varchar), ''),
        coalesce(cast(dropoff_zone_id as varchar), ''),
        coalesce(cast(base_passenger_fare as varchar), ''),
        cast(duplicate_rank as varchar)
    )) as trip_id,
    hvfhs_license_num,
    dispatching_base_num,
    originating_base_num,
    request_datetime,
    on_scene_datetime,
    pickup_datetime,
    dropoff_datetime,
    pickup_zone_id,
    dropoff_zone_id,
    trip_miles,
    reported_trip_seconds,
    actual_trip_seconds,
    wait_seconds,
    driver_arrival_delay_seconds,
    average_speed_mph,
    base_passenger_fare,
    tolls,
    bcf,
    sales_tax,
    congestion_surcharge,
    airport_fee,
    tips,
    driver_pay,
    shared_request_flag,
    shared_match_flag,
    access_a_ride_flag,
    wav_request_flag,
    wav_match_flag,
    ingestion_year,
    ingestion_month_number,
    ingestion_month,
    duplicate_rank
from typed
