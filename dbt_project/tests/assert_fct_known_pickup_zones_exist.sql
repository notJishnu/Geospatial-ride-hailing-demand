select trips.*
from {{ ref('fct_trips') }} as trips
left join {{ ref('dim_zone') }} as zones on trips.pickup_zone_id = zones.zone_id
where trips.pickup_zone_id not in (264, 265)
  and zones.zone_id is null
