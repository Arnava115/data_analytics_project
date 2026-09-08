from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import header, load_geojson, page_setup, sidebar_filters, style_fig
from src.queries import (
    all_zones_for_map,
    borough_hour_heatmap,
    coverage_gaps,
    rollup_hour,
    zone_hour_heatmap,
)

page_setup("Supply vs demand")
filters = sidebar_filters()
header(
    "Supply vs demand",
    "Where volume concentrates — and where peak hours look thin",
    "Zone-hour grain. Demand intensity is trips; constrained hours are the top decile of that hour’s distribution.",
)

zones = all_zones_for_map(filters)
geojson = load_geojson()

left, right = st.columns((1.4, 1))
with left:
    if geojson and not zones.empty:
        fig = px.choropleth_map(
            zones,
            geojson=geojson,
            locations="pu_location_id",
            featureidkey="properties.location_id",
            color="trips",
            hover_name="zone_name",
            hover_data={"borough": True, "trips": ":,.0f", "avg_wait_minutes": ":.1f", "pu_location_id": False},
            color_continuous_scale=["#0D1117", "#0E4429", "#238636", "#3FB950", "#56D364"],
            map_style="carto-darkmatter",
            zoom=9.25,
            center={"lat": 40.73, "lon": -73.94},
            opacity=0.78,
        )
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=0, r=0, t=40, b=0),
            font=dict(color="#E6EDF3"),
            title="Completed trips by pickup zone",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Map needs taxi-zone GeoJSON from ingest and at least one zone with trips.")

with right:
    by_hour = rollup_hour(filters)
    fig = go.Figure(
        go.Bar(x=by_hour["pickup_hour"], y=by_hour["trips"], marker_color="#238636", name="Trips")
    )
    st.plotly_chart(
        style_fig(fig, "Trips by pickup hour", "Completed trips", "Hour of day (local)"),
        use_container_width=True,
    )

bh = borough_hour_heatmap(filters)
if not bh.empty:
    pivot = bh.pivot_table(index="borough", columns="pickup_hour", values="trips", aggfunc="sum").fillna(0)
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns),
            y=list(pivot.index),
            colorscale=[[0, "#0D1117"], [0.4, "#0E4429"], [1, "#3FB950"]],
            hovertemplate="Borough=%{y}<br>Hour=%{x}<br>Trips=%{z:,.0f}<extra></extra>",
        )
    )
    st.plotly_chart(
        style_fig(fig, "Borough × hour demand", None, "Hour of day"),
        use_container_width=True,
    )

zh = zone_hour_heatmap(filters, top_n=18)
if not zh.empty:
    pivot = zh.pivot_table(index="zone_name", columns="pickup_hour", values="trips", aggfunc="sum").fillna(0)
    order = zh.groupby("zone_name")["trips"].sum().sort_values(ascending=False).index
    pivot = pivot.reindex(order)
    fig = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=list(pivot.columns),
            y=list(pivot.index),
            colorscale=[[0, "#0D1117"], [0.45, "#0E4429"], [1, "#56D364"]],
            hovertemplate="Zone=%{y}<br>Hour=%{x}<br>Trips=%{z:,.0f}<extra></extra>",
        )
    )
    st.plotly_chart(
        style_fig(fig, "Top 18 pickup zones × hour", None, "Hour of day"),
        use_container_width=True,
    )

st.markdown("#### Thin coverage in peak hours")
st.caption(
    "Peak hours are 7–9 and 17–19. Zones in the bottom quartile of peak volume are the ones a City GM should stare at — "
    "not the already-busy airports."
)
gaps = coverage_gaps(filters)
if gaps.empty:
    st.info("No coverage-gap rows for these filters.")
else:
    show = gaps.rename(
        columns={
            "zone_name": "Zone",
            "borough": "Borough",
            "peak_trips": "Peak-hour trips",
            "avg_wait_minutes": "Avg wait (min)",
        }
    )[["Zone", "Borough", "Peak-hour trips", "Avg wait (min)"]]
    st.dataframe(show, use_container_width=True, hide_index=True)
