{{ config(materialized='view') }}

with trips as (
    select * from {{ ref('stg_hvfhv_trips') }}
),

classified as (
    select
        trips.*,
        pickup_zone.borough as pickup_borough,
        dropoff_zone.borough as dropoff_borough,
        pickup_zone.zone_name as pickup_zone_name,
        dropoff_zone.zone_name as dropoff_zone_name,
        case
            when pickup_zone.zone_id is null or dropoff_zone.zone_id is null then 'zone_not_in_lookup'
            when dropoff_datetime <= pickup_datetime then 'nonpositive_duration'
            when actual_trip_seconds < {{ var('min_trip_seconds') }} or actual_trip_seconds > {{ var('max_trip_seconds') }} then 'duration_outside_bounds'
            when trip_miles <= 0 or trip_miles >= {{ var('max_trip_miles') }} then 'trip_miles_outside_bounds'
            when reported_trip_seconds <= 0 then 'reported_trip_time_nonpositive'
            when average_speed_mph >= {{ var('max_average_speed_mph') }} then 'average_speed_outside_bounds'
            when base_passenger_fare < 0 then 'negative_base_passenger_fare'
            when driver_pay < 0 then 'negative_driver_pay'
            when pickup_datetime < make_date(ingestion_year, cast(ingestion_month_number as integer), 1) - interval '{{ var("month_boundary_tolerance_hours") }} hours' then 'pickup_before_partition_tolerance'
            when pickup_datetime >= make_date(ingestion_year, cast(ingestion_month_number as integer), 1) + interval '1 month' + interval '{{ var("month_boundary_tolerance_hours") }} hours' then 'pickup_after_partition_tolerance'
            when duplicate_rank > 1 then 'duplicate_composite_key'
            else null
        end as reject_reason,
        pickup_zone_id in (264, 265) or dropoff_zone_id in (264, 265) as is_unknown_or_outside_nyc
    from trips
    left join {{ ref('stg_zone_lookup') }} as pickup_zone on trips.pickup_zone_id = pickup_zone.zone_id
    left join {{ ref('stg_zone_lookup') }} as dropoff_zone on trips.dropoff_zone_id = dropoff_zone.zone_id
)

select * from classified
