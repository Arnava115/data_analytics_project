# City Pulse

NYC marketplace command center for a City GM. Built as a Data Analyst portfolio product: metric dictionary, SQL marts, a Weekly Business Review with actions, and drilldowns — not a chart gallery.

**Question:** Where is Uber’s NYC marketplace healthy this week, and what should ops do?

**Data:** [NYC TLC High-Volume FHV trip records](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page) — Uber (`HV0003`) and Lyft (`HV0005`) as a competitor overlay. Latest two published months.

## What a City GM sees

1. **WBR (home)** — north-star KPIs, WoW on the last complete week, three written insights, two recommended actions.
2. **Supply vs demand** — zone map, borough × hour heatmap, thin-coverage zones in peak hours.
3. **Marketplace economics** — take rate, fare vs driver pay, pay-per-hour proxy, Uber vs Lyft.
4. **Quality** — request-to-pickup wait, trip time, miles, shared match, zone outliers.
5. **KPI dictionary** — grain, formula, filters, and what TLC cannot support.

Rates are always recomputed from sums. The dashboard is not allowed to average take rates.

## Run

```bash
make setup    # python3.11 venv + deps
make run      # download TLC → DuckDB marts → SQL tests
make app      # Streamlit at http://localhost:8501
```

First `make run` downloads two months **one at a time**, aggregates into DuckDB, then deletes the parquet (`keep_raw: false` in `config.yaml`) so a laptop disk can hold the warehouse. Re-runs download again. Warehouse: `data/warehouse/city_pulse.duckdb`.

```bash
make ingest       # download only
make transform    # rebuild marts from cached parquet
make test         # dbt-style SQL tests (fail on any row)
```

## Deploy (Streamlit Community Cloud)

Vercel cannot host this app. Streamlit Community Cloud can. Use **GitHub Desktop** to publish, then Cloud to run it.

**GitHub Desktop**
1. File → Add Local Repository → this folder (`data_analytics_project`).
2. Make sure these are **included** in the commit (not ignored): `data/warehouse/city_pulse.duckdb` (~90 MB), `data/reference/taxi_zone_lookup.csv`, `data/reference/taxi_zones.geojson`.
3. Commit on `main`, then **Publish repository**. Leave it **public** so Streamlit Cloud can clone it.

**Streamlit Cloud**
1. Open [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
2. Create app:
   - Repository: the one you just published
   - Branch: `main`
   - Main file path: `app/Home.py`
   - Python version: **3.11**
3. Deploy. First boot takes several minutes. URL: `https://<app-name>.streamlit.app`.

## Method

```
TLC parquet  →  junk filters  →  stg.trips (ephemeral)
                                  ├─ mart.zone_hour   (atomic slice grain)
                                  ├─ mart.city_day
                                  └─ mart.borough_week
KPI views recompute take rate, wait, airport share, pay/hour from sums.
Insights are threshold rules on complete ISO weeks — not an LLM.
```

Junk rules live in `config.yaml` and `sql/staging/01_stg_trips.sql`: invalid zones, zero miles/time, extreme fare/wait, inverted timestamps.

## Findings

Warehouse window: **1 Apr 2026 – 31 May 2026** (Uber + Lyft). 43.1M in-scope trips; **5.8% junk** dropped (invalid zones, zero miles/time, extreme fare/wait). Uber completed **29.0M** trips.

Citywide Uber (two-month window):

- Take rate **23.0%**
- Request-to-pickup wait **5.3 min** average
- On-trip driver pay **$62.65 / hour** (proxy — not online hours)
- Airport-touching mix **8.0%**
- Shared match **1.6%**

**WBR week of 25 May vs 18 May (Uber, complete ISO weeks):**

1. **Take rate compressed 163 bps to 23.2%.** Contribution after driver pay thinned. First action: split fare mix airport vs street and check whether promotions or longer trips are eating the fare.
2. **Trips −3.3% WoW** (3.10M vs prior week) with wait **+4.4% to 5.7 min**. Not a threshold breach on wait, but the direction is worse experience on a slightly smaller pie.
3. **Pelham Bay Park** is the only zone that grew trips >10% with trip time also up >10%. Treat that as congestion/mix, not a place for untargeted trip bonuses.

Lyft is on the competitor overlay for take rate and pay-per-hour; north-star KPIs above are Uber.

A fresh `make run` pulls the **latest two published** TLC months (not necessarily Apr–May).

## Interview lines this repo is meant to support

- I defined take rate and demand intensity at zone-hour grain and showed ops where coverage was thinning at peak.
- I used real Uber NYC trips, documented data limitations (no ETAs, no idle time, wait is conditional on completion), and still produced actions a City GM could take.
- The dashboard is a product: WBR narrative, drilldown, and a metric dictionary.

## Layout

```
config.yaml          thresholds and airport zone IDs
sql/staging/         dim.zones, junk profile, stg.trips
sql/marts/           city-day, zone-hour, borough-week
sql/tests/           empty/grain/bounds checks — must return zero rows
src/pipeline.py      one-command ETL
src/insights.py      WBR rules
src/metrics.py       rollup SQL fragment (single definition of rates)
app/Home.py          Streamlit product
docs/metrics.md      dictionary
```
