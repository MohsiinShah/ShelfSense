"""Demo store: four cameras, twelve shelf units, and a seeded 7-day history.

The seeded history is simulated and every row is tagged source="seed".
Rows produced by Gemini video analysis are tagged source="gemini".
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

STORE = {
    "id": "demo-mart-lhr",
    "name": "Demo Mart — Gulberg, Lahore",
    "city": "Lahore",
    "tz": "Asia/Karachi",
    "tz_offset_h": 5,
    "base_rate_pkr": 25000,
}

# Each camera covers three shelf zones. `zones` is what Gemini is told to watch.
CAMERAS = [
    {"id": "cam-01", "name": "Aisle 1 — Snacks & Beverages", "sample": "aisle-snacks.mp4",
     "zones": {
         "A1-L": "the shelving on the LEFT side of the frame",
         "A1-R": "the shelving on the RIGHT side of the frame",
         "A1-E": "the far end of the aisle / end-cap display in the background",
     }},
    {"id": "cam-02", "name": "Fresh Produce Hall", "sample": "produce-hall.mp4",
     "zones": {
         "P-FRONT": "the produce display tables in the FOREGROUND (bottom third of frame)",
         "P-MID": "the displays and walkway in the MIDDLE of the frame",
         "P-BACK": "the refrigerated shelving / signage at the BACK of the frame",
     }},
    {"id": "cam-03", "name": "Aisle 28 — Baby & Household", "sample": "aisle-household.mp4",
     "zones": {
         "A28-L": "the shelving on the LEFT side of the frame",
         "A28-R": "the shelving on the RIGHT side of the frame",
         "A28-E": "the open floor / promotional area at the far end",
     }},
    {"id": "cam-04", "name": "Aisle 6 — Bakery & Breakfast", "sample": "aisle-bakery.mp4",
     "zones": {
         "A6-L": "the shelving on the LEFT side of the frame",
         "A6-R": "the shelving / counter on the RIGHT side of the frame",
         "A6-E": "the far end of the aisle in the background",
     }},
]

# Floor-plan rectangles are in a 100 x 60 grid used by the dashboard heatmap.
UNITS = [
    {"id": "A1-L", "camera_id": "cam-01", "aisle": "1", "category": "Chips & snacks", "position": "eye_level", "rect": [6, 8, 6, 22]},
    {"id": "A1-R", "camera_id": "cam-01", "aisle": "1", "category": "Soft drinks", "position": "eye_level", "rect": [16, 8, 6, 22]},
    {"id": "A1-E", "camera_id": "cam-01", "aisle": "1", "category": "Promo end-cap", "position": "end_cap", "rect": [6, 2, 16, 5]},
    {"id": "P-FRONT", "camera_id": "cam-02", "aisle": "P", "category": "Seasonal fruit", "position": "table", "rect": [30, 40, 26, 12]},
    {"id": "P-MID", "camera_id": "cam-02", "aisle": "P", "category": "Vegetables", "position": "table", "rect": [30, 26, 26, 12]},
    {"id": "P-BACK", "camera_id": "cam-02", "aisle": "P", "category": "Dairy chiller", "position": "wall", "rect": [30, 14, 26, 10]},
    {"id": "A28-L", "camera_id": "cam-03", "aisle": "28", "category": "Nappies & wipes", "position": "eye_level", "rect": [64, 8, 6, 22]},
    {"id": "A28-R", "camera_id": "cam-03", "aisle": "28", "category": "Detergents", "position": "bottom", "rect": [74, 8, 6, 22]},
    {"id": "A28-E", "camera_id": "cam-03", "aisle": "28", "category": "Promo floor stack", "position": "end_cap", "rect": [64, 2, 16, 5]},
    {"id": "A6-L", "camera_id": "cam-04", "aisle": "6", "category": "Bread & buns", "position": "eye_level", "rect": [86, 8, 6, 22]},
    {"id": "A6-R", "camera_id": "cam-04", "aisle": "6", "category": "Cereals & spreads", "position": "top", "rect": [94, 8, 5, 22]},
    {"id": "A6-E", "camera_id": "cam-04", "aisle": "6", "category": "Tea & coffee end-cap", "position": "end_cap", "rect": [86, 2, 13, 5]},
]

# Simulation knobs per unit: (traffic multiplier, stop propensity, reach propensity, dwell s, age mix)
_PROFILE = {
    "A1-L": (1.30, 0.34, 0.22, 11, (0.18, 0.52, 0.22, 0.08)),
    "A1-R": (1.20, 0.28, 0.25, 8, (0.14, 0.50, 0.26, 0.10)),
    "A1-E": (1.55, 0.40, 0.18, 9, (0.12, 0.44, 0.30, 0.14)),
    "P-FRONT": (1.70, 0.46, 0.38, 19, (0.06, 0.28, 0.42, 0.24)),
    "P-MID": (1.35, 0.38, 0.33, 16, (0.05, 0.26, 0.43, 0.26)),
    "P-BACK": (0.95, 0.30, 0.29, 12, (0.07, 0.33, 0.40, 0.20)),
    "A28-L": (0.80, 0.42, 0.31, 21, (0.04, 0.58, 0.30, 0.08)),
    "A28-R": (0.70, 0.22, 0.15, 10, (0.02, 0.36, 0.44, 0.18)),
    "A28-E": (0.95, 0.27, 0.12, 7, (0.06, 0.40, 0.36, 0.18)),
    "A6-L": (1.10, 0.36, 0.30, 12, (0.08, 0.34, 0.38, 0.20)),
    "A6-R": (0.75, 0.25, 0.17, 14, (0.12, 0.38, 0.34, 0.16)),
    "A6-E": (1.00, 0.31, 0.21, 10, (0.03, 0.30, 0.40, 0.27)),
}

# Relative footfall by local hour (store open 09:00–23:00), evening peak.
_HOURLY = {9: 0.35, 10: 0.5, 11: 0.65, 12: 0.8, 13: 0.85, 14: 0.7, 15: 0.65, 16: 0.75,
           17: 0.95, 18: 1.15, 19: 1.35, 20: 1.4, 21: 1.2, 22: 0.8}


def seed_buckets(now: datetime | None = None, days: int = 7, rng_seed: int = 42) -> list[dict]:
    rng = random.Random(rng_seed)
    tz = timezone(timedelta(hours=STORE["tz_offset_h"]))
    now = (now or datetime.now(tz)).astimezone(tz).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)
    rows = []
    t = start
    while t < now:
        hour_w = _HOURLY.get(t.hour)
        if hour_w is not None:
            weekend = 1.35 if t.weekday() in (4, 5, 6) else 1.0  # Fri–Sun
            for unit_id, (mult, stop_p, reach_p, dwell, ages) in _PROFILE.items():
                # weekend evenings skew younger
                young_shift = 0.06 if (weekend > 1 and t.hour >= 18) else 0.0
                mix = [ages[0], ages[1] + young_shift, ages[2] - young_shift / 2, ages[3] - young_shift / 2]
                unique = max(0, int(rng.gauss(38 * mult * hour_w * weekend, 4)))
                visits = unique + int(unique * rng.uniform(0.05, 0.15))
                stops = int(visits * min(0.95, max(0.0, rng.gauss(stop_p, 0.04))))
                reach_visitors = int(unique * min(0.9, max(0.0, rng.gauss(reach_p, 0.04))))
                rows.append({
                    "unit_id": unit_id,
                    "bucket_start": t.astimezone(timezone.utc).isoformat(),
                    "visits": visits,
                    "unique_visitors": unique,
                    "stops": stops,
                    "reach_visitors": reach_visitors,
                    "reaches": int(reach_visitors * rng.uniform(1.1, 1.5)),
                    "dwell_p50": round(max(1.0, rng.gauss(dwell, 2)), 1),
                    **{band: round(unique * share, 2) for band, share in
                       zip(("age_lt18", "age_18_35", "age_35_55", "age_55p"), mix)},
                    "source": "seed",
                })
        t += timedelta(hours=1)
    return rows
