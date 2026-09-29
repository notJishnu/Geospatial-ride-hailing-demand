"""Build a reusable zone geometry dimension with H3 zone-centroid cells."""

import geopandas as gpd
import h3


def model(dbt, session):
    """Read TLC polygons and emit WGS84 centroids and H3 indices for display and joins."""
    dbt.config(materialized="table")
    geometry_path = dbt.config.get("zone_shapefile_path")
    resolution = int(dbt.config.get("h3_resolution"))
    zones = gpd.read_file(geometry_path).to_crs("EPSG:2263")
    centroids = zones.geometry.centroid.to_crs("EPSG:4326")
    # The official polygon source does not carry the lookup CSV's service_zone field.
    result = zones[["LocationID", "borough", "zone"]].copy()
    result["zone_id"] = result.pop("LocationID").astype(int)
    result["centroid_longitude"] = centroids.x
    result["centroid_latitude"] = centroids.y
    result["h3_r8"] = [
        h3.latlng_to_cell(latitude, longitude, resolution)
        for latitude, longitude in zip(
            result["centroid_latitude"], result["centroid_longitude"], strict=True
        )
    ]
    for column in ("borough", "zone", "h3_r8"):
        result[column] = result[column].astype(object)
    return result
