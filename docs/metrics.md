# City Pulse metric dictionary

Owner: City Analytics (portfolio). Grain means the unique key of the table. Filters listed here are the ones applied **before** the metric is computed, not dashboard slicers.

All **rates** are recomputed from sums whenever the dashboard filters. Never average a take rate across zone-hours.

Source: NYC TLC High-Volume FHV trip records. Uber = `hvfhs_license_num = HV0003`. Lyft = `HV0005`.

---

## Completed trips

| | |
|---|---|
| **Grain** | Trip, then summed to city-day / zone-hour / borough-week |
| **Formula** | Count of trips that survive junk filters |
| **Filters** | Uber or Lyft; valid timestamps; pickup and dropoff zone in 1–263; miles in (0, 150]; trip time in (0, 5h]; passenger fare in (0, 1000]; driver pay ≥ 0; wait null or in [0, 2h] |
| **Owner** | City GM |
| **So what** | Volume. Down WoW is not automatically a demand story — wait and airport mix have to move with it. |

---

## Take rate

| | |
|---|---|
| **Grain** | city-day, zone-hour, borough-week |
| **Formula** | `(SUM(passenger_fare) − SUM(driver_pay)) / SUM(passenger_fare)` |
| **Filters** | Same as completed trips. Fare is TLC `base_passenger_fare` (before tips, tolls, taxes, airport fee). |
| **Owner** | Marketplace / pricing |
| **So what** | Contribution after driver pay. Can be negative on a slice when promotions push driver pay above base fare. A rising take rate with falling driver pay per hour is not a win. |

---

## Average wait (minutes)

| | |
|---|---|
| **Grain** | Same |
| **Formula** | `SUM(wait_seconds) / COUNT(wait_seconds) / 60` where wait = `pickup_datetime − request_datetime` |
| **Filters** | Null request timestamps are excluded from the wait average, not from trip counts. |
| **Owner** | Rider experience / ops |
| **So what** | Closest public proxy for ETAs. TLC does **not** publish quoted ETA, cancellations, or driver idle time. `on_scene_datetime` is wheelchair-accessible vehicles only and is not used. |

---

## Wait p50 / p90 (minutes)

| | |
|---|---|
| **Grain** | Computed on trips with `approx_quantile` (t-digest), stored on city-day and zone-hour. **Cannot be rolled up** by averaging p90s. Borough-week leaves p90 null. |
| **Formula** | `quantile_cont(wait_seconds, 0.5 / 0.9)` |
| **So what** | The tail is what riders remember. Use p90 on Quality; use the average on the WBR scorecard. |

---

## Average trip time (minutes) and miles

| | |
|---|---|
| **Grain** | Same |
| **Formula** | `SUM(trip_time_seconds) / trips / 60` and `SUM(trip_miles) / trips` |
| **So what** | Mix detectors. Airports and outer-borough long hauls inflate both. Volume up + trip time up at the same zone is congestion (or mix), not healthy density. |

---

## Airport share

| | |
|---|---|
| **Grain** | Same |
| **Formula** | Trips whose pickup **or** dropoff zone is EWR (1), JFK (132), or LGA (138), divided by completed trips |
| **Filters** | Airport **pickup** filter on the dashboard uses pickup zone only (`pu_is_airport`) so the map stays interpretable. |
| **So what** | Airport banks steal street coverage and stretch trip time. A 2pp WoW jump is a staffing problem, not a trivia fact. |

---

## Driver pay per hour (proxy)

| | |
|---|---|
| **Grain** | Same |
| **Formula** | `SUM(driver_pay) / (SUM(trip_time_seconds) / 3600)` |
| **Caveat** | **On-trip time only.** This is not earnings per online hour. Idle, en-route-to-pickup, and deadhead are invisible. Label it as a proxy in every chart. |
| **So what** | Directionally useful for “are trips getting worse to drive?” especially by borough. |

---

## Shared request / match rate

| | |
|---|---|
| **Formula** | Shared request: passenger opted into pool. Shared match: they actually shared the vehicle (`shared_*_flag = 'Y'`). |
| **So what** | Match rate is a product + density metric. Request without match is a failed promise. |

---

## Tip rate

| | |
|---|---|
| **Formula** | `SUM(tips) / SUM(passenger_fare)` |
| **So what** | Experience + mix. Airport and tourist corridors usually tip differently than local street. |

---

## Demand intensity / constrained zone-hours

| | |
|---|---|
| **Grain** | zone × hour × platform (across all dates in the warehouse) |
| **Formula** | `NTILE(10) OVER (PARTITION BY platform, pickup_hour ORDER BY trips)` stored as `demand_decile`. Decile 10 = constrained for that hour of day. |
| **So what** | Peak Manhattan at 7pm is supposed to be busy. A Boro Zone in decile 10 at 3am is a different story. Always read decile with hour. |

---

## Coverage gap (peak hours)

| | |
|---|---|
| **Grain** | Pickup zone, peak hours 07–09 and 17–19, current dashboard filters |
| **Formula** | Zones in the bottom quartile of peak-hour trips |
| **So what** | Thin coverage where the city is trying to move. Do not confuse this with low-demand overnight zones. |

---

## What this data cannot support

Do not invent these in interviews or on the dashboard:

- True ETAs or ETA error
- Rider cancellations or driver cancellations
- Online hours, utilization, or idle time
- Driver identity, tenure, or churn
- Rider identity, LTV, or promo code
- Surge multiplier as quoted in-app
- Requested-but-unfulfilled demand (we only see completed trips plus timestamps on those trips)

Wait is a **conditional** metric: it is only observed on trips that completed.
