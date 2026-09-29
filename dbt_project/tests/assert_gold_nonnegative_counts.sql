select * from {{ ref('agg_zone_hour_demand') }} where trip_count < 0
