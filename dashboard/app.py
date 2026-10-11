"""Local Streamlit dashboard backed by the NYC mobility DuckDB warehouse."""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(os.environ.get("NYC_MOBILITY_ROOT", Path.cwd()))
WAREHOUSE = Path(os.environ.get("WAREHOUSE_PATH", ROOT / "data/warehouse/nyc_mobility.duckdb"))
DEMAND_METRICS = ROOT / "artifacts/demand/metrics.json"
ETA_METRICS = ROOT / "artifacts/eta/metrics.json"


def as_percent(value: float) -> str:
    """Format a rate for a concise dashboard metric."""
    return f"{value:.1%}"


def metric_rows(metrics: dict[str, float]) -> pd.DataFrame:
    """Turn a metric dictionary into a presentation-ready table."""
    return pd.DataFrame({"metric": list(metrics), "value": list(metrics.values())})


@st.cache_data(ttl=600, show_spinner=False)
def read_table(table_name: str) -> pd.DataFrame:
    """Read a permitted Gold/Silver table through a short-lived read-only connection."""
    allowed = {
        "agg_od_matrix",
        "agg_zone_hour_demand",
        "dim_zone",
        "fct_trips",
        "kpi_driver_economics",
        "kpi_zone_daily",
        "silver_trips_quarantine",
    }
    if table_name not in allowed:
        raise ValueError(f"Unsupported dashboard table: {table_name}")
    if not WAREHOUSE.exists():
        return pd.DataFrame()
    connection = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        return connection.sql(f"select * from {table_name}").df()
    except duckdb.CatalogException:
        return pd.DataFrame()
    finally:
        connection.close()


@st.cache_data(ttl=600, show_spinner=False)
def read_artifact(path: str) -> dict:
    """Read a model report only when its local artifact exists."""
    artifact = Path(path)
    if not artifact.exists():
        return {}
    return json.loads(artifact.read_text(encoding="utf-8"))


def prepare_datetime(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """Convert a timestamp column without modifying Streamlit's cached source frame."""
    prepared = frame.copy()
    prepared[column] = pd.to_datetime(prepared[column])
    return prepared


def render_demand_map() -> None:
    st.header("Demand map")
    demand = read_table("agg_zone_hour_demand")
    zones = read_table("dim_zone")
    if demand.empty or zones.empty:
        st.warning("Run the Gold dbt models before viewing demand.")
        return
    demand = prepare_datetime(demand, "date_hour")
    dates = sorted(demand["date_hour"].dt.date.unique())
    selected_date = st.sidebar.selectbox("Service date", dates, key="demand_date")
    selected_hour = st.sidebar.slider("Hour", 0, 23, 8, key="demand_hour")
    weather = st.sidebar.selectbox("Weather", ["All", "Dry", "Wet"], key="demand_weather")
    selected = demand[
        (demand["date_hour"].dt.date == selected_date)
        & (demand["date_hour"].dt.hour == selected_hour)
    ]
    if weather != "All":
        selected = selected[selected["precipitation_mm"].fillna(0).gt(0) == (weather == "Wet")]
    mapped = selected.merge(zones, on="zone_id", how="inner")
    columns = st.columns(3)
    columns[0].metric("Trips", f"{mapped['trip_count'].sum():,.0f}")
    columns[1].metric("Average wait", f"{mapped['average_wait_seconds'].mean() / 60:.1f} min")
    columns[2].metric("Shared-request share", as_percent(mapped["shared_request_share"].mean()))
    if mapped.empty:
        st.info("No zone-hour rows match these filters.")
        return
    layer = pdk.Layer(
        "ScatterplotLayer",
        mapped,
        get_position="[centroid_longitude, centroid_latitude]",
        get_radius="trip_count * 4 + 100",
        get_fill_color="[20, 120, 220, 170]",
        pickable=True,
    )
    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=pdk.ViewState(latitude=40.72, longitude=-73.95, zoom=9.8),
            tooltip={
                "text": "{zone_name}\nTrips: {trip_count}\nAvg wait: {average_wait_seconds} sec"
            },
        )
    )


def render_zone_explorer() -> None:
    st.header("Zone explorer")
    daily = read_table("kpi_zone_daily")
    zones = read_table("dim_zone")
    if daily.empty or zones.empty:
        st.warning("Run the Gold dbt models before viewing zone KPIs.")
        return
    report = prepare_datetime(daily.merge(zones, on="zone_id", how="inner"), "service_date")
    zone_names = sorted(report["zone_name"].unique())
    selected_name = st.selectbox("Zone", zone_names)
    zone = report[report["zone_name"] == selected_name].sort_values("service_date")
    latest = zone.iloc[-1]
    metrics = st.columns(3)
    metrics[0].metric("Trips", f"{latest.trip_count:,.0f}")
    metrics[1].metric("Average wait", f"{latest.average_wait_seconds / 60:.1f} min")
    metrics[2].metric("Driver pay / mile", f"${latest.average_driver_pay_per_mile:.2f}")
    st.line_chart(zone.set_index("service_date")[["trip_count", "average_wait_seconds"]])
    st.dataframe(
        zone[["service_date", "trip_count", "shared_request_share", "platform_take_approx_total"]],
        hide_index=True,
        use_container_width=True,
    )


def render_od_flows() -> None:
    st.header("Origin–destination flows")
    od = read_table("agg_od_matrix")
    zones = read_table("dim_zone")
    if od.empty or zones.empty:
        st.warning("Run the Gold dbt models before viewing OD flows.")
        return
    summary = od.groupby(["pickup_zone_id", "dropoff_zone_id"], as_index=False).agg(
        trip_count=("trip_count", "sum"), average_trip_seconds=("average_trip_seconds", "mean")
    )
    names = zones[["zone_id", "zone_name"]]
    summary = summary.merge(names, left_on="pickup_zone_id", right_on="zone_id", how="left").rename(
        columns={"zone_name": "pickup_zone"}
    )
    summary = summary.merge(
        names, left_on="dropoff_zone_id", right_on="zone_id", how="left"
    ).rename(columns={"zone_name": "dropoff_zone"})
    top_flows = summary.sort_values("trip_count", ascending=False).head(25)
    st.bar_chart(top_flows.set_index("pickup_zone")["trip_count"])
    st.dataframe(
        top_flows[["pickup_zone", "dropoff_zone", "trip_count", "average_trip_seconds"]],
        hide_index=True,
        use_container_width=True,
    )


def render_eta_performance() -> None:
    st.header("ETA model performance")
    metrics = read_artifact(str(ETA_METRICS))
    if not metrics:
        st.warning("Run `make train-eta` to create local ETA evaluation artifacts.")
        return
    test = metrics["test_lightgbm"]
    cards = st.columns(3)
    cards[0].metric("MAE", f"{test['mae_seconds'] / 60:.1f} min")
    cards[1].metric("P90 absolute error", f"{test['p90_absolute_error_seconds'] / 60:.1f} min")
    cards[2].metric("Within 5 minutes", as_percent(test["within_5_minutes"]))
    slice_name = st.selectbox("Slice", sorted(metrics["test_slices"]), key="eta_slice")
    slice_frame = (
        pd.DataFrame.from_dict(metrics["test_slices"][slice_name], orient="index")
        .rename_axis(slice_name)
        .reset_index()
    )
    st.bar_chart(slice_frame.set_index(slice_name)["mae_seconds"])
    st.dataframe(slice_frame, hide_index=True, use_container_width=True)


def render_forecast_evaluation() -> None:
    st.header("Forecast evaluation")
    metrics = read_artifact(str(DEMAND_METRICS))
    if not metrics:
        st.warning("Run `make train-demand` to create local demand evaluation artifacts.")
        return
    comparison = pd.DataFrame(
        [
            {"model": name.removeprefix("test_"), **values}
            for name, values in metrics.items()
            if name.startswith("test_") and isinstance(values, dict)
        ]
    )
    st.info(f"Final-holdout champion: {metrics['selection']['champion']} (selected on WAPE).")
    st.bar_chart(comparison.set_index("model")[["mae", "wape"]])
    st.dataframe(comparison, hide_index=True, use_container_width=True)
    st.caption(
        "This page reports observed rolling-origin and final-holdout evaluation; it does not present fabricated future forecasts."
    )


def render_data_health() -> None:
    st.header("Data health")
    trips = read_table("fct_trips")
    quarantine = read_table("silver_trips_quarantine")
    cards = st.columns(3)
    cards[0].metric("Gold trips", f"{len(trips):,}")
    cards[1].metric("Quarantined rows", f"{len(quarantine):,}")
    reject_rate = (
        len(quarantine) / (len(trips) + len(quarantine)) if len(trips) + len(quarantine) else 0.0
    )
    cards[2].metric("Reject rate", as_percent(reject_rate))
    status = pd.DataFrame(
        {
            "asset": ["DuckDB warehouse", "Demand metrics", "ETA metrics"],
            "available": [WAREHOUSE.exists(), DEMAND_METRICS.exists(), ETA_METRICS.exists()],
        }
    )
    st.dataframe(status, hide_index=True, use_container_width=True)
    st.caption(
        "Automated dbt-test history and drift alerts are added in Phase 10; this page currently shows available local artifacts and row counts."
    )


def main() -> None:
    """Render the dashboard and dispatch the selected analytical view."""
    st.set_page_config(page_title="NYC Mobility Analytics", page_icon="🚕", layout="wide")
    st.title("NYC Mobility Analytics")
    st.caption(
        "Local Gold marts, model evaluation artifacts, and observational operational metrics."
    )
    page = st.sidebar.radio(
        "Page",
        [
            "Demand map",
            "Zone explorer",
            "OD flows",
            "ETA performance",
            "Forecast evaluation",
            "Data health",
        ],
    )
    pages = {
        "Demand map": render_demand_map,
        "Zone explorer": render_zone_explorer,
        "OD flows": render_od_flows,
        "ETA performance": render_eta_performance,
        "Forecast evaluation": render_forecast_evaluation,
        "Data health": render_data_health,
    }
    pages[page]()


if __name__ == "__main__":
    main()
