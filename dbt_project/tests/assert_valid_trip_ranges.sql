select *
from {{ ref('silver_trips_valid') }}
where actual_trip_seconds < {{ var('min_trip_seconds') }}
   or actual_trip_seconds > {{ var('max_trip_seconds') }}
   or trip_miles <= 0
   or trip_miles >= {{ var('max_trip_miles') }}
   or average_speed_mph >= {{ var('max_average_speed_mph') }}
   or base_passenger_fare < 0
   or driver_pay < 0
