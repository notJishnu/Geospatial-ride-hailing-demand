select * from {{ ref('agg_zone_hour_demand') }} where zone_id in (264, 265)
