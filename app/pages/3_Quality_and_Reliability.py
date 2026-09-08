from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from lib import UBER_GREEN, AMBER, header, page_setup, sidebar_filters, style_fig
from src.queries import rollup_borough, rollup_city_day, rollup_hour, rollup_totals, rollup_zone

page_setup("Quality")
filters = sidebar_filters()
header(
    "Quality and reliability",
    "Wait, trip time, miles, and shared-ride mix",
    "Wait is request timestamp → pickup timestamp. TLC does not publish ETAs, cancellations, or idle time.",
)

totals = rollup_totals(filters)
k1, k2, k3, k4 = st.columns(4)
k1.metric(
    "Avg wait",
    f"{totals['avg_wait_minutes']:.1f} min" if totals.get("avg_wait_minutes") is not None else "—",
)
k2.metric(
    "Avg trip time",
    f"{totals['avg_trip_minutes']:.1f} min" if totals.get("avg_trip_minutes") is not None else "—",
)
k3.metric(
    "Avg trip miles",
    f"{totals['avg_trip_miles']:.1f} mi" if totals.get("avg_trip_miles") is not None else "—",
)
k4.metric("Shared match rate", f"{totals['shared_match_rate'] * 100:.1f}%" if totals.get("shared_match_rate") is not None else "—")

daily = rollup_city_day(filters)
if daily.empty:
    st.info("No trips for these filters.")
    st.stop()

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["avg_wait_minutes"],
        name="Avg wait",
        line=dict(color=UBER_GREEN, width=2),
    )
)
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["avg_trip_minutes"],
        name="Avg trip time",
        line=dict(color=AMBER, width=2),
    )
)
st.plotly_chart(
    style_fig(fig, "Wait vs in-trip time", "Minutes", "Pickup date"),
    use_container_width=True,
)

col1, col2 = st.columns(2)
with col1:
    by_h = rollup_hour(filters)
    fig = go.Figure(
        go.Bar(
            x=by_h["pickup_hour"],
            y=by_h["avg_wait_minutes"],
            marker_color="#238636",
            name="Avg wait",
        )
    )
    st.plotly_chart(
        style_fig(fig, "Average wait by hour", "Minutes", "Hour of day"),
        use_container_width=True,
    )
with col2:
    by_b = rollup_borough(filters)
    fig = go.Figure(
        go.Bar(
            x=by_b["avg_wait_minutes"],
            y=by_b["borough"],
            orientation="h",
            marker_color="#388BFD",
            customdata=by_b["trips"],
            hovertemplate="%{y}<br>Wait=%{x:.1f} min<br>Trips=%{customdata:,.0f}<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(style_fig(fig, "Average wait by borough", "Minutes"), use_container_width=True)

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["avg_trip_miles"],
        name="Avg miles",
        line=dict(color="#C084FC", width=2),
    )
)
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["shared_match_rate"] * 100,
        name="Shared match %",
        yaxis="y2",
        line=dict(color="#4C9BE8", width=2),
    )
)
fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, ticksuffix="%"))
st.plotly_chart(
    style_fig(fig, "Trip length and shared-ride match rate", "Average miles", "Pickup date"),
    use_container_width=True,
)

st.markdown("#### Night vs weekend mix")
st.caption("Night is 22:00–04:59. Weekend is Saturday–Sunday (ISO). Both are mix shifts that move wait and miles.")
m1, m2 = st.columns(2)
night_share = totals["night_trips"] / totals["trips"] if totals.get("trips") else None
weekend_share = totals["weekend_trips"] / totals["trips"] if totals.get("trips") else None
m1.metric("Night trips", f"{night_share * 100:.1f}%" if night_share is not None else "—")
m2.metric("Weekend trips", f"{weekend_share * 100:.1f}%" if weekend_share is not None else "—")

st.markdown("#### Zone outliers")
st.caption("Highest wait among the busiest 25 pickup zones in the current filter. Slow and small is noise; slow and large is a problem.")
z = rollup_zone(filters, limit=25)
if z.empty:
    st.info("No zone rows.")
else:
    z = z.sort_values("avg_wait_minutes", ascending=False)
    show = z[
        [
            "zone_name",
            "borough",
            "trips",
            "avg_wait_minutes",
            "wait_p90_minutes",
            "avg_trip_minutes",
            "trip_time_p90_minutes",
            "take_rate",
        ]
    ].rename(
        columns={
            "zone_name": "Zone",
            "borough": "Borough",
            "trips": "Trips",
            "avg_wait_minutes": "Avg wait (min)",
            "wait_p90_minutes": "Wait p90 (min)",
            "avg_trip_minutes": "Avg trip (min)",
            "trip_time_p90_minutes": "Trip p90 (min)",
            "take_rate": "Take rate",
        }
    )
    show["Take rate"] = show["Take rate"].map(lambda x: f"{x * 100:.1f}%")
    st.dataframe(show, use_container_width=True, hide_index=True)
