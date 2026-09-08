from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from lib import (
    UBER_GREEN,
    delta_pct,
    fmt_money,
    fmt_num,
    fmt_pct,
    header,
    page_setup,
    sidebar_filters,
    style_fig,
)

from src.insights import generate_wbr
from src.queries import competitor_overlay, rollup_city_day, rollup_totals

page_setup("WBR")
filters = sidebar_filters()
header(
    "Weekly Business Review",
    "NYC marketplace health",
    "Completed trips, take rate, wait, and mix — defined once in the metric layer, sliced here.",
)

try:
    packet = generate_wbr(platform=filters.platform)
except Exception as exc:
    st.warning(f"WBR narrative needs two complete weeks in the warehouse. {exc}")
    packet = None

totals = rollup_totals(filters)
daily = rollup_city_day(filters)

# Headline KPIs use the sidebar window so filters still work; WBR deltas use complete weeks.
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Completed trips", fmt_num(totals.get("trips"), 1))
c2.metric("Take rate", fmt_pct(totals.get("take_rate")))
c3.metric("Avg wait", f"{totals.get('avg_wait_minutes'):.1f} min" if totals.get("avg_wait_minutes") is not None else "—")
c4.metric("Airport share", fmt_pct(totals.get("airport_share")))
c5.metric("Driver pay / hour", fmt_money(totals.get("driver_pay_per_hour")))

c6, c7, c8, c9, c10 = st.columns(5)
c6.metric("Avg trip time", f"{totals['avg_trip_minutes']:.1f} min" if totals.get("avg_trip_minutes") is not None else "—")
c7.metric("Avg trip miles", f"{totals['avg_trip_miles']:.1f} mi" if totals.get("avg_trip_miles") is not None else "—")
c8.metric("Shared match rate", fmt_pct(totals.get("shared_match_rate")))
c9.metric("Tip rate", fmt_pct(totals.get("tip_rate")))
c10.metric("Avg passenger fare", fmt_money(totals.get("avg_passenger_fare")))
st.caption(
    "Rates are recomputed from sums on the current filters — never averaged from pre-baked percentages. "
    "Driver pay / hour is on-trip time only (not true online hours)."
)

if packet is not None:
    st.markdown(
        f"**Complete week** {packet.current_week.date()} vs prior {packet.prior_week.date()} "
        f"({filters.platform} citywide, unfiltered)."
    )
    w1, w2, w3, w4 = st.columns(4)
    w1.metric(
        "WoW trips",
        fmt_num(packet.current["trips"]),
        delta_pct(packet.current["trips"], packet.prior["trips"]),
    )
    w2.metric(
        "WoW take rate",
        fmt_pct(packet.current["take_rate"]),
        (
            f"{packet.wow['take_rate'] * 10000:+.0f} bps"
            if packet.wow.get("take_rate") is not None
            else None
        ),
    )
    w3.metric(
        "WoW wait",
        f"{packet.current['avg_wait_minutes']:.1f} min",
        delta_pct(packet.current["avg_wait_minutes"], packet.prior["avg_wait_minutes"]),
        delta_color="inverse",
    )
    w4.metric(
        "WoW pay / hour",
        fmt_money(packet.current["driver_pay_per_hour"]),
        delta_pct(packet.current["driver_pay_per_hour"], packet.prior["driver_pay_per_hour"]),
    )

    st.markdown("#### This week’s read")
    cols = st.columns(3)
    for col, ins in zip(cols, packet.insights):
        col.markdown(
            f"<div class='insight-card {ins.severity}'>"
            f"<div class='sev'>{ins.severity}</div><h4>{ins.title}</h4><p>{ins.body}</p></div>",
            unsafe_allow_html=True,
        )
    st.markdown("#### Recommended actions")
    acols = st.columns(2)
    for col, action in zip(acols, packet.actions):
        col.markdown(
            f"<div class='action-card'><h4>Do this</h4><p>{action}</p></div>",
            unsafe_allow_html=True,
        )

st.markdown("#### Trend in the selected window")
if daily.empty:
    st.info("No trips for these filters.")
else:
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=daily["pickup_date"],
            y=daily["trips"],
            name="Completed trips",
            marker_color="#238636",
            opacity=0.85,
        )
    )
    fig.add_trace(
        go.Scatter(
            x=daily["pickup_date"],
            y=daily["take_rate"] * 100,
            name="Take rate (%)",
            yaxis="y2",
            line=dict(color="#E6EDF3", width=2),
        )
    )
    fig.update_layout(
        yaxis2=dict(overlaying="y", side="right", showgrid=False, ticksuffix="%"),
    )
    st.plotly_chart(
        style_fig(fig, "Completed trips and take rate", "Completed trips", "Pickup date"),
        use_container_width=True,
    )

    fig2 = go.Figure()
    fig2.add_trace(
        go.Scatter(
            x=daily["pickup_date"],
            y=daily["avg_wait_minutes"],
            name="Avg wait (min)",
            line=dict(color=UBER_GREEN, width=2),
        )
    )
    fig2.add_trace(
        go.Scatter(
            x=daily["pickup_date"],
            y=daily["airport_share"] * 100,
            name="Airport share (%)",
            yaxis="y2",
            line=dict(color="#F5A623", width=2),
        )
    )
    fig2.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, ticksuffix="%"))
    st.plotly_chart(
        style_fig(fig2, "Wait time vs airport mix", "Avg wait (minutes)", "Pickup date"),
        use_container_width=True,
    )

st.markdown("#### Competitor overlay")
st.caption("Lyft is a benchmark, not a residual. Same filters, both platforms.")
comp = competitor_overlay(filters)
if comp.empty:
    st.info("No competitor series for these filters.")
else:
    fig3 = go.Figure()
    for platform, color in [("Uber", UBER_GREEN), ("Lyft", "#4C9BE8")]:
        part = comp[comp["platform"] == platform]
        fig3.add_trace(
            go.Scatter(
                x=part["pickup_date"],
                y=part["take_rate"] * 100,
                name=f"{platform} take rate",
                line=dict(color=color, width=2),
            )
        )
    st.plotly_chart(
        style_fig(fig3, "Take rate: Uber vs Lyft", "Take rate (%)", "Pickup date"),
        use_container_width=True,
    )
