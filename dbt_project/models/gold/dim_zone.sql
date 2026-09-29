{{ config(materialized='table') }}

select
    geometry.zone_id,
    lookup.borough,
    lookup.zone_name,
    lookup.service_zone,
    geometry.centroid_longitude,
    geometry.centroid_latitude,
    geometry.h3_r8,
    geometry.zone_id in (264, 265) as is_unknown_or_outside_nyc
from {{ ref('silver_zone_geometry') }} as geometry
inner join {{ ref('stg_zone_lookup') }} as lookup using (zone_id)
