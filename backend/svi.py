"""Shelf Value Index engine — Technical Design §13.

Per unit u over a window W:
  F  unique visitors per covered hour (exposure)
  S  stops / visits (stop rate)
  R  reach visitors / unique visitors (reach rate)
  D  visit-weighted median dwell (seconds)
Each is robust min-max normalised within the store (P5..P95), then
  Base = 0.40 F + 0.25 S + 0.20 R + 0.15 D
  AudienceFit = clip(sum_b a_ub w_b / sum_b a_store,b w_b, 0.5, 1.5)
  SVI = min(100, round(100 * Base * AudienceFit))
  Price = base_rate * SVI / median(SVI)
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median

AGE_BANDS = ("age_lt18", "age_18_35", "age_35_55", "age_55p")
WEIGHTS = {"F": 0.40, "S": 0.25, "R": 0.20, "D": 0.15}
SVI_VERSION = "1.0-default-weights"
PRICE_FLOOR = 0.4

# Brand audience presets: weight per age band. "generic" disables AudienceFit.
AUDIENCES = {
    "generic": None,
    "18-35": {"age_lt18": 0.2, "age_18_35": 1.0, "age_35_55": 0.3, "age_55p": 0.1},
    "35-55": {"age_lt18": 0.1, "age_18_35": 0.3, "age_35_55": 1.0, "age_55p": 0.4},
    "families": {"age_lt18": 1.0, "age_18_35": 0.6, "age_35_55": 0.8, "age_55p": 0.2},
    "55+": {"age_lt18": 0.0, "age_18_35": 0.1, "age_35_55": 0.4, "age_55p": 1.0},
}


def _percentile(values: list[float], p: float) -> float:
    xs = sorted(values)
    if not xs:
        return 0.0
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def _robust_norm(values: dict[str, float]) -> dict[str, float]:
    vs = list(values.values())
    p5, p95 = _percentile(vs, 0.05), _percentile(vs, 0.95)
    span = p95 - p5
    if span <= 1e-9:
        return {k: 0.5 for k in values}
    return {k: min(1.0, max(0.0, (v - p5) / span)) for k, v in values.items()}


def unit_inputs(buckets: list[dict]) -> dict[str, dict]:
    """Aggregate raw bucket rows into F/S/R/D + age mix per unit."""
    acc: dict[str, dict] = defaultdict(lambda: {
        "hours": set(), "visits": 0, "unique": 0, "stops": 0, "reach_visitors": 0,
        "reaches": 0, "dwell_w": 0.0, "age": defaultdict(float), "sources": set(),
    })
    for b in buckets:
        a = acc[b["unit_id"]]
        a["hours"].add(b["bucket_start"])
        a["visits"] += b.get("visits", 0)
        a["unique"] += b.get("unique_visitors", 0)
        a["stops"] += b.get("stops", 0)
        a["reach_visitors"] += b.get("reach_visitors", 0)
        a["reaches"] += b.get("reaches", 0)
        a["dwell_w"] += b.get("dwell_p50", 0.0) * b.get("visits", 0)
        for band in AGE_BANDS:
            a["age"][band] += b.get(band, 0.0)
        a["sources"].add(b.get("source", "seed"))

    out = {}
    for unit_id, a in acc.items():
        hours = max(1, len(a["hours"]))
        age_total = sum(a["age"].values()) or 1.0
        out[unit_id] = {
            "F": a["unique"] / hours,
            "S": a["stops"] / a["visits"] if a["visits"] else 0.0,
            "R": a["reach_visitors"] / a["unique"] if a["unique"] else 0.0,
            "D": a["dwell_w"] / a["visits"] if a["visits"] else 0.0,
            "visits": a["visits"],
            "unique_visitors": a["unique"],
            "reaches": a["reaches"],
            "covered_hours": hours,
            "age_mix": {band: a["age"][band] / age_total for band in AGE_BANDS},
            "sources": sorted(a["sources"]),
        }
    return out


def score(buckets: list[dict], units: list[dict], base_rate: float,
          audience: str = "generic") -> list[dict]:
    """Return one row per unit with inputs, normalised inputs, SVI and price."""
    inputs = unit_inputs(buckets)
    if not inputs:
        return []
    norm = {m: _robust_norm({u: v[m] for u, v in inputs.items()}) for m in WEIGHTS}

    weights = AUDIENCES.get(audience)
    store_mix = {band: sum(v["age_mix"][band] for v in inputs.values()) / len(inputs)
                 for band in AGE_BANDS}
    store_on_target = sum(store_mix[b] * weights[b] for b in AGE_BANDS) if weights else 1.0

    unit_meta = {u["id"]: u for u in units}
    rows = []
    for unit_id, v in inputs.items():
        base = sum(WEIGHTS[m] * norm[m][unit_id] for m in WEIGHTS)
        fit = 1.0
        if weights and store_on_target > 0:
            on_target = sum(v["age_mix"][b] * weights[b] for b in AGE_BANDS)
            fit = min(1.5, max(0.5, on_target / store_on_target))
        rows.append({
            **unit_meta.get(unit_id, {"id": unit_id}),
            "inputs": {m: round(v[m], 3) for m in WEIGHTS},
            "normalised": {m: round(norm[m][unit_id], 3) for m in WEIGHTS},
            "base": round(base, 3),
            "audience_fit": round(fit, 2),
            "svi": min(100, round(100 * base * fit)),
            "visits": v["visits"],
            "unique_visitors": v["unique_visitors"],
            "reaches": v["reaches"],
            "age_mix": {b: round(x, 3) for b, x in v["age_mix"].items()},
            "covered_hours": v["covered_hours"],
            "confidence": "high" if v["covered_hours"] >= 72 else
                          "medium" if v["covered_hours"] >= 12 else "low",
            "sources": v["sources"],
        })

    med = median(r["svi"] for r in rows) or 1
    for r in rows:
        # Floor at 40% of the base rate: every slot still has a minimum rent.
        raw = max(PRICE_FLOOR * base_rate, base_rate * r["svi"] / med)
        r["price_pkr"] = int(round(raw / 500.0) * 500)
    rows.sort(key=lambda r: r["svi"], reverse=True)
    return rows


def hour_weekday_matrix(buckets: list[dict], tz_offset_h: int = 5) -> list[list[int]]:
    """7x24 grid of unique visitors (Mon=0), in store local time."""
    from datetime import datetime, timedelta, timezone

    grid = [[0] * 24 for _ in range(7)]
    tz = timezone(timedelta(hours=tz_offset_h))
    for b in buckets:
        t = datetime.fromisoformat(b["bucket_start"]).astimezone(tz)
        grid[t.weekday()][t.hour] += b.get("unique_visitors", 0)
    return grid
