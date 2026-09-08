from __future__ import annotations

import streamlit as st

from lib import ROOT, header, page_setup

page_setup("KPI dictionary")
header(
    "Metric dictionary",
    "Definitions a City GM can argue with",
    "Grain, formula, filters, and what this dataset cannot support. Same text as docs/metrics.md.",
)

md = (ROOT / "docs" / "metrics.md").read_text()
st.markdown(md)
