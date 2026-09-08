"""Threshold-based Weekly Business Review insights. No LLM — rules a GM can audit."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pandas as pd

from src.config import load_config
from src.transform import connect


@dataclass
class Insight:
    title: str
    body: str
    severity: str
    score: float
    action: str


@dataclass
class WbrPacket:
    current_week: pd.Timestamp
    prior_week: pd.Timestamp
    current: dict
    prior: dict
    wow: dict
    insights: list[Insight] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


def _complete_week_starts(city_day: pd.DataFrame) -> list[pd.Timestamp]:
    max_date = pd.to_datetime(city_day["pickup_date"]).max()
    starts = sorted(pd.to_datetime(city_day["week_start"]).unique())
    complete = [w for w in starts if (w + timedelta(days=6)) <= max_date]
    return complete


def _rollup(df: pd.DataFrame) -> dict:
    trips = df["trips"].sum()
    fare = df["passenger_fare_sum"].sum()
    pay = df["driver_pay_sum"].sum()
    wait_trips = df["wait_trips"].sum()
    time_sum = df["trip_time_seconds_sum"].sum()
    return {
        "trips": float(trips),
        "take_rate": float((fare - pay) / fare) if fare else None,
        "avg_wait_minutes": float(df["wait_seconds_sum"].sum() / wait_trips / 60) if wait_trips else None,
        "avg_trip_minutes": float(time_sum / trips / 60) if trips else None,
        "avg_trip_miles": float(df["miles_sum"].sum() / trips) if trips else None,
        "airport_share": float(df["airport_trips"].sum() / trips) if trips else None,
        "driver_pay_per_hour": float(pay / (time_sum / 3600)) if time_sum else None,
        "shared_match_rate": float(df["shared_match_trips"].sum() / trips) if trips else None,
        "tip_rate": float(df["tips_sum"].sum() / fare) if fare else None,
        "wait_p90_minutes": float(df["wait_p90_seconds"].median() / 60) if "wait_p90_seconds" in df else None,
    }


def _wow(current: dict, prior: dict, key: str) -> float | None:
    a, b = current.get(key), prior.get(key)
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b


def _wow_pp(current: dict, prior: dict, key: str) -> float | None:
    a, b = current.get(key), prior.get(key)
    if a is None or b is None:
        return None
    return a - b


def generate_wbr(platform: str = "Uber") -> WbrPacket:
    cfg = load_config()["insights"]
    con = connect(read_only=True)
    try:
        city = con.execute(
            f"""
            SELECT * FROM mart.city_day
            WHERE platform = ?
            """,
            [platform],
        ).fetchdf()
        borough = con.execute(
            "SELECT * FROM mart.borough_week WHERE platform = ?",
            [platform],
        ).fetchdf()
        zones = con.execute(
            """
            SELECT
                week_start,
                pu_location_id,
                ANY_VALUE(zone_name) AS zone_name,
                ANY_VALUE(borough) AS borough,
                SUM(trips) AS trips,
                SUM(trip_time_seconds_sum) AS trip_time_seconds_sum,
                SUM(wait_seconds_sum) AS wait_seconds_sum,
                SUM(wait_trips) AS wait_trips
            FROM mart.zone_hour
            WHERE platform = ?
            GROUP BY week_start, pu_location_id
            """,
            [platform],
        ).fetchdf()
    finally:
        con.close()

    if city.empty:
        raise RuntimeError("mart.city_day is empty. Run the pipeline first.")

    weeks = _complete_week_starts(city)
    if len(weeks) < 2:
        raise RuntimeError("Need at least two complete weeks for a WBR.")
    current_week, prior_week = weeks[-1], weeks[-2]
    city["week_start"] = pd.to_datetime(city["week_start"])
    borough["week_start"] = pd.to_datetime(borough["week_start"])
    zones["week_start"] = pd.to_datetime(zones["week_start"])

    cur_df = city[city["week_start"] == current_week]
    prev_df = city[city["week_start"] == prior_week]
    current = _rollup(cur_df)
    prior = _rollup(prev_df)
    wow = {
        "trips": _wow(current, prior, "trips"),
        "take_rate": _wow_pp(current, prior, "take_rate"),
        "avg_wait_minutes": _wow(current, prior, "avg_wait_minutes"),
        "avg_trip_minutes": _wow(current, prior, "avg_trip_minutes"),
        "airport_share": _wow_pp(current, prior, "airport_share"),
        "driver_pay_per_hour": _wow(current, prior, "driver_pay_per_hour"),
        "shared_match_rate": _wow_pp(current, prior, "shared_match_rate"),
        "avg_trip_miles": _wow(current, prior, "avg_trip_miles"),
        "tip_rate": _wow_pp(current, prior, "tip_rate"),
    }

    insights: list[Insight] = []

    take_bps = (wow["take_rate"] or 0) * 10000
    if take_bps <= -cfg["take_rate_drop_bps"]:
        insights.append(
            Insight(
                title="Take rate compressed",
                body=(
                    f"Take rate fell {abs(take_bps):.0f} bps week over week "
                    f"to {current['take_rate'] * 100:.1f}%. Contribution is thinner after driver pay."
                ),
                severity="high",
                score=abs(take_bps),
                action="Pull fare mix by airport vs street and check whether promotions or longer trips are eating contribution.",
            )
        )
    elif take_bps >= cfg["take_rate_drop_bps"]:
        insights.append(
            Insight(
                title="Take rate expanded",
                body=(
                    f"Take rate rose {take_bps:.0f} bps to {current['take_rate'] * 100:.1f}%. "
                    f"Watch driver pay-per-hour so supply does not walk."
                ),
                severity="medium",
                score=take_bps * 0.6,
                action="Confirm driver pay per hour is still competitive in outer boroughs before celebrating the take-rate lift.",
            )
        )

    airport_pp = (wow["airport_share"] or 0) * 100
    if airport_pp >= cfg["airport_share_jump_pp"]:
        insights.append(
            Insight(
                title="Airport mix spiked",
                body=(
                    f"Airport-touching trips rose {airport_pp:.1f} pp to "
                    f"{current['airport_share'] * 100:.1f}% of volume. Airports inflate time and miles "
                    f"and can starve street coverage."
                ),
                severity="high",
                score=airport_pp * 20,
                action="Check JFK/LGA wait times and pre-position supply on the next peak inbound bank.",
            )
        )

    if wow["avg_wait_minutes"] is not None and wow["avg_wait_minutes"] * 100 >= cfg["wait_up_pct"]:
        insights.append(
            Insight(
                title="Pickup wait deteriorated",
                body=(
                    f"Average request-to-pickup wait rose {wow['avg_wait_minutes'] * 100:.1f}% "
                    f"to {current['avg_wait_minutes']:.1f} min. Riders feel this before they feel take rate."
                ),
                severity="high",
                score=abs(wow["avg_wait_minutes"]) * 400,
                action="Target incentives at the borough-hours where wait p90 moved the most, not a citywide bonus.",
            )
        )

    if (
        wow["driver_pay_per_hour"] is not None
        and wow["driver_pay_per_hour"] * 100 <= -cfg["pay_per_hour_drop_pct"]
    ):
        b = borough.copy()
        b["pay_per_hour"] = b["driver_pay_sum"] / (b["trip_time_seconds_sum"] / 3600)
        cur_b = b[b["week_start"] == current_week][["borough", "pay_per_hour", "trips"]]
        prev_b = b[b["week_start"] == prior_week][["borough", "pay_per_hour"]].rename(
            columns={"pay_per_hour": "pay_prior"}
        )
        merged = cur_b.merge(prev_b, on="borough")
        merged["drop"] = (merged["pay_per_hour"] - merged["pay_prior"]) / merged["pay_prior"]
        worst = merged.sort_values("drop").head(1)
        worst_name = worst.iloc[0]["borough"] if not worst.empty else "a borough"
        insights.append(
            Insight(
                title="Driver pay per hour slipped",
                body=(
                    f"On-trip driver pay per hour (proxy — not true online hours) fell "
                    f"{abs(wow['driver_pay_per_hour']) * 100:.1f}% to "
                    f"${current['driver_pay_per_hour']:.2f}. Weakest borough: {worst_name}."
                ),
                severity="medium",
                score=abs(wow["driver_pay_per_hour"]) * 300,
                action=f"Review {worst_name} utilization and quest design; this proxy falls when trips get slower or fares get thinner.",
            )
        )

    z = zones.copy()
    z["avg_min"] = z["trip_time_seconds_sum"] / z["trips"] / 60
    cur_z = z[z["week_start"] == current_week]
    prev_z = z[z["week_start"] == prior_week][["pu_location_id", "trips", "avg_min"]].rename(
        columns={"trips": "trips_prior", "avg_min": "min_prior"}
    )
    zm = cur_z.merge(prev_z, on="pu_location_id")
    zm = zm[zm["trips"] >= cfg["min_zone_trips_for_congestion"]]
    zm["trips_wow"] = (zm["trips"] - zm["trips_prior"]) / zm["trips_prior"]
    zm["time_wow"] = (zm["avg_min"] - zm["min_prior"]) / zm["min_prior"]
    congested = zm[
        (zm["trips_wow"] >= cfg["volume_up_pct"] / 100)
        & (zm["time_wow"] >= cfg["trip_time_up_pct"] / 100)
    ].sort_values("trips", ascending=False)
    if not congested.empty:
        top = congested.head(3)
        names = ", ".join(f"{r.zone_name}" for r in top.itertuples())
        insights.append(
            Insight(
                title="Volume up, trips slower",
                body=(
                    f"{len(congested)} zones grew trips >{cfg['volume_up_pct']:.0f}% with trip time also up "
                    f">{cfg['trip_time_up_pct']:.0f}%. Loudest: {names}. That is congestion or mix shift, not healthy growth."
                ),
                severity="high",
                score=float(len(congested) * 15 + top.iloc[0]["trips_wow"] * 100),
                action="Do not add untargeted trip bonuses there — they will sit in traffic. Push supply to adjacent zones or airport recovery instead.",
            )
        )

    if wow["trips"] is not None and wow["trips"] <= -0.05:
        insights.append(
            Insight(
                title="Completed trips down",
                body=(
                    f"Completed trips fell {abs(wow['trips']) * 100:.1f}% WoW "
                    f"({current['trips']:,.0f} vs {prior['trips']:,.0f})."
                ),
                severity="medium",
                score=abs(wow["trips"]) * 200,
                action="Separate demand (requests we cannot see) from completion: check wait and airport share before calling it a demand story.",
            )
        )

    if not insights:
        insights.append(
            Insight(
                title="Marketplace stable week",
                body=(
                    f"No threshold breaches vs the prior complete week. Take rate "
                    f"{current['take_rate'] * 100:.1f}%, wait {current['avg_wait_minutes']:.1f} min, "
                    f"airport share {current['airport_share'] * 100:.1f}%."
                ),
                severity="low",
                score=1,
                action="Use the quiet week to clear the thin-coverage zone-hours on the supply page.",
            )
        )

    insights = sorted(insights, key=lambda i: i.score, reverse=True)[:3]
    actions: list[str] = []
    for ins in insights:
        if ins.action and ins.action not in actions:
            actions.append(ins.action)
        if len(actions) == 2:
            break

    return WbrPacket(
        current_week=current_week,
        prior_week=prior_week,
        current=current,
        prior=prior,
        wow=wow,
        insights=insights,
        actions=actions,
    )
