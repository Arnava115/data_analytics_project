from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from lib import UBER_GREEN, BLUE, fmt_money, fmt_pct, header, page_setup, sidebar_filters, style_fig
from src.queries import competitor_overlay, rollup_borough, rollup_city_day, rollup_hour, rollup_totals

page_setup("Economics")
filters = sidebar_filters()
header(
    "Marketplace economics",
    "Take rate, driver pay, and fare mix",
    "Take rate = (passenger fare − driver pay) / passenger fare. Fare is TLC base passenger fare before tips and tolls.",
)

totals = rollup_totals(filters)
k1, k2, k3, k4 = st.columns(4)
k1.metric("Take rate", fmt_pct(totals.get("take_rate")))
k2.metric("Avg passenger fare", fmt_money(totals.get("avg_passenger_fare")))
k3.metric("Avg driver pay", fmt_money(totals.get("avg_driver_pay")))
k4.metric("Driver pay / hour", fmt_money(totals.get("driver_pay_per_hour")))
st.caption(
    "A rising take rate is not automatically good: if driver pay per hour falls, supply will eventually leave. "
    "Both series are on this page on purpose."
)

daily = rollup_city_day(filters)
if daily.empty:
    st.info("No trips for these filters.")
    st.stop()

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["avg_passenger_fare"],
        name="Avg passenger fare",
        line=dict(color="#E6EDF3", width=2),
    )
)
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["avg_driver_pay"],
        name="Avg driver pay",
        line=dict(color=UBER_GREEN, width=2),
    )
)
st.plotly_chart(
    style_fig(fig, "Average fare vs driver pay per trip", "USD per trip", "Pickup date"),
    use_container_width=True,
)

fig = go.Figure()
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["take_rate"] * 100,
        name="Take rate",
        line=dict(color=UBER_GREEN, width=2),
    )
)
fig.add_trace(
    go.Scatter(
        x=daily["pickup_date"],
        y=daily["driver_pay_per_hour"],
        name="Driver pay / hour (proxy)",
        yaxis="y2",
        line=dict(color="#F5A623", width=2),
    )
)
fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, tickprefix="$"))
st.plotly_chart(
    style_fig(fig, "Take rate vs on-trip driver pay per hour", "Take rate (%)", "Pickup date"),
    use_container_width=True,
)

col1, col2 = st.columns(2)
with col1:
    by_b = rollup_borough(filters)
    fig = go.Figure(
        go.Bar(
            x=by_b["take_rate"] * 100,
            y=by_b["borough"],
            orientation="h",
            marker_color="#238636",
            customdata=by_b["trips"],
            hovertemplate="%{y}<br>Take rate=%{x:.1f}%<br>Trips=%{customdata:,.0f}<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(style_fig(fig, "Take rate by pickup borough", "Take rate (%)"), use_container_width=True)

with col2:
    by_h = rollup_hour(filters)
    fig = go.Figure(
        go.Scatter(
            x=by_h["pickup_hour"],
            y=by_h["take_rate"] * 100,
            mode="lines+markers",
            line=dict(color=UBER_GREEN, width=2),
            name="Take rate",
        )
    )
    st.plotly_chart(
        style_fig(fig, "Take rate by hour of day", "Take rate (%)", "Hour of day"),
        use_container_width=True,
    )

fig = go.Figure()
fig.add_trace(
    go.Bar(x=daily["pickup_date"], y=daily["tip_rate"] * 100, name="Tip rate", marker_color="#388BFD")
)
st.plotly_chart(
    style_fig(fig, "Tips as a share of passenger fare", "Tip rate (%)", "Pickup date"),
    use_container_width=True,
)

st.markdown("#### Uber vs Lyft")
comp = competitor_overlay(filters)
fig = go.Figure()
for platform, color in [("Uber", UBER_GREEN), ("Lyft", BLUE)]:
    part = comp[comp["platform"] == platform]
    fig.add_trace(
        go.Scatter(
            x=part["pickup_date"],
            y=part["driver_pay_per_hour"],
            name=f"{platform} pay / hour",
            line=dict(color=color, width=2),
        )
    )
st.plotly_chart(
    style_fig(fig, "On-trip driver pay per hour: Uber vs Lyft", "USD per on-trip hour", "Pickup date"),
    use_container_width=True,
)
