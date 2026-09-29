select *
from {{ ref('silver_trips_quarantine') }}
where reject_reason not in (
    'zone_not_in_lookup',
    'nonpositive_duration',
    'duration_outside_bounds',
    'trip_miles_outside_bounds',
    'reported_trip_time_nonpositive',
    'average_speed_outside_bounds',
    'negative_base_passenger_fare',
    'negative_driver_pay',
    'pickup_before_partition_tolerance',
    'pickup_after_partition_tolerance',
    'duplicate_composite_key'
)
