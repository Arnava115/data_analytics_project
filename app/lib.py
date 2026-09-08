from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ingest import TAXI_ZONES_GEOJSON_PATH  # noqa: E402
from src.queries import Filters, warehouse_bounds  # noqa: E402

UBER_GREEN = "#06C167"
AMBER = "#F5A623"
RED = "#E85D4C"
BLUE = "#4C9BE8"
MUTED = "#8B949E"

PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#E6EDF3", family="Inter, Helvetica, sans-serif", size=13),
    margin=dict(l=16, r=16, t=48, b=32),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    xaxis=dict(gridcolor="#21262D", zeroline=False),
    yaxis=dict(gridcolor="#21262D", zeroline=False),
    colorway=[UBER_GREEN, BLUE, AMBER, RED, "#C084FC"],
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
html, body, [class*="css"]  { font-family: 'IBM Plex Sans', Helvetica, sans-serif; }
.block-container { padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1400px; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
.stDeployButton,
div[data-testid="stAppDeployButton"] { display: none !important; }
header[data-testid="stHeader"] {
    background-color: #0D1117 !important;
    height: auto !important;
}
[data-testid="stToolbar"] {
    display: flex !important;
    visibility: visible !important;
    min-height: 2.75rem;
}
[data-testid="stExpandSidebarButton"] {
    visibility: visible !important;
    display: flex !important;
    opacity: 1 !important;
    position: fixed !important;
    top: 0.55rem !important;
    left: 0.55rem !important;
    z-index: 2147483647 !important;
    width: 2.5rem !important;
    height: 2.5rem !important;
    background: #161B22 !important;
    border: 1px solid #06C167 !important;
    border-radius: 8px !important;
}
.cp-kicker {
    font-family: 'IBM Plex Mono', monospace;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-size: 0.72rem;
    color: #06C167;
    margin-bottom: 0.15rem;
}
.cp-title { font-size: 1.85rem; font-weight: 700; letter-spacing: -0.03em; margin: 0; }
.cp-sub { color: #8B949E; margin: 0.2rem 0 1.1rem; }
.insight-card, .action-card {
    border: 1px solid #21262D;
    background: #161B22;
    border-radius: 8px;
    padding: 1rem 1.1rem;
    height: 100%;
}
.insight-card.high { border-left: 3px solid #E85D4C; }
.insight-card.medium { border-left: 3px solid #F5A623; }
.insight-card.low { border-left: 3px solid #06C167; }
.insight-card h4, .action-card h4 { margin: 0 0 0.4rem; font-size: 0.95rem; }
.insight-card p, .action-card p { margin: 0; color: #C9D1D9; font-size: 0.9rem; line-height: 1.45; }
.sev { font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase; color: #8B949E; }
div[data-testid="stMetric"] {
    background: #161B22;
    border: 1px solid #21262D;
    padding: 0.75rem 0.9rem;
    border-radius: 8px;
}
div[data-testid="stMetric"] label { color: #8B949E; }
</style>
"""


def page_setup(title: str) -> None:
    st.set_page_config(
        page_title=f"{title} · City Pulse",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    # Same-origin iframe: pin a Menu control on the parent page when the sidebar is closed.
    components.html(
        """
        <script>
        (function () {
          const doc = window.parent.document;
          if (doc.getElementById("cp-open-nav")) return;
          const btn = doc.createElement("button");
          btn.id = "cp-open-nav";
          btn.type = "button";
          btn.textContent = "Menu";
          btn.setAttribute("aria-label", "Open navigation");
          btn.style.cssText = [
            "position:fixed",
            "top:10px",
            "left:10px",
            "z-index:2147483647",
            "display:none",
            "align-items:center",
            "justify-content:center",
            "height:36px",
            "padding:0 12px",
            "border:1px solid #06C167",
            "border-radius:8px",
            "background:#161B22",
            "color:#E6EDF3",
            "font:600 13px 'IBM Plex Sans', Helvetica, sans-serif",
            "cursor:pointer"
          ].join(";");
          btn.onclick = function () {
            const expand = doc.querySelector('[data-testid="stExpandSidebarButton"]');
            if (expand) expand.click();
          };
          doc.body.appendChild(btn);
          const sync = function () {
            const expand = doc.querySelector('[data-testid="stExpandSidebarButton"]');
            btn.style.display = expand ? "flex" : "none";
          };
          sync();
          new window.parent.MutationObserver(sync).observe(doc.body, {
            childList: true,
            subtree: true,
            attributes: true
          });
        })();
        </script>
        """,
        height=0,
    )


def header(kicker: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"<div class='cp-kicker'>{kicker}</div><p class='cp-title'>{title}</p>"
        f"<p class='cp-sub'>{subtitle}</p>",
        unsafe_allow_html=True,
    )


def style_fig(fig: go.Figure, title: str, yaxis_title: str | None = None, xaxis_title: str | None = None) -> go.Figure:
    fig.update_layout(**PLOTLY_LAYOUT, title=dict(text=title, font=dict(size=16)))
    if yaxis_title:
        fig.update_yaxes(title_text=yaxis_title)
    if xaxis_title:
        fig.update_xaxes(title_text=xaxis_title)
    return fig


def sidebar_filters() -> Filters:
    bounds = warehouse_bounds()
    min_d, max_d = bounds["min_date"], bounds["max_date"]
    default_start = max(min_d, max_d - timedelta(days=27))
    st.sidebar.markdown("**CITY PULSE**")
    st.sidebar.caption("NYC marketplace · City GM view")
    platform = st.sidebar.radio("Platform", ["Uber", "Lyft"], index=0)
    date_val = st.sidebar.date_input(
        "Date range",
        value=(default_start, max_d),
        min_value=min_d,
        max_value=max_d,
    )
    if isinstance(date_val, (list, tuple)) and len(date_val) == 2:
        start, end = date_val
    else:
        start, end = default_start, max_d
    boroughs = st.sidebar.multiselect("Borough", bounds["boroughs"], default=[])
    tod = st.sidebar.multiselect(
        "Time of day",
        ["overnight", "morning", "midday", "evening", "night"],
        default=[],
    )
    airport = st.sidebar.radio(
        "Pickup location",
        ["all", "street", "airport"],
        format_func=lambda x: {"all": "All pickups", "street": "Street only", "airport": "Airport only"}[x],
        index=0,
    )
    st.sidebar.caption(
        f"Warehouse {min_d} → {max_d}"
        + (f" · built {bounds['ran_at_utc']}" if bounds.get("ran_at_utc") is not None else "")
    )
    return Filters(
        start=start,
        end=end,
        platform=platform,
        boroughs=boroughs,
        time_of_day=tod,
        airport=airport,
    )


def fmt_num(n, digits=1) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    n = float(n)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.{digits}f}M"
    if n >= 10_000:
        return f"{sign}{n / 1_000:.0f}K"
    if n >= 100:
        return f"{sign}{n:,.0f}"
    return f"{sign}{n:,.{digits}f}"


def fmt_pct(x, digits=1) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    return f"{float(x) * 100:.{digits}f}%"


def fmt_money(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    return f"${float(x):,.2f}"


def delta_pct(current, prior) -> str | None:
    if current is None or prior in (None, 0) or pd.isna(current) or pd.isna(prior):
        return None
    return f"{(current - prior) / prior * 100:+.1f}%"


def load_geojson() -> dict | None:
    import json

    if not TAXI_ZONES_GEOJSON_PATH.exists():
        return None
    return json.loads(TAXI_ZONES_GEOJSON_PATH.read_text())
