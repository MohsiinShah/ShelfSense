"""ShelfSense API — FastAPI on Cloud Run, Firestore for data, Gemini for vision and Q&A."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore, storage
from pydantic import BaseModel

import ai
import svi
from store_config import CAMERAS, STORE, UNITS, seed_buckets

PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
BUCKET = os.environ.get("VIDEO_BUCKET", f"{PROJECT}-videos")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
MAX_UPLOAD_MB = 30

app = FastAPI(title="ShelfSense API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db = firestore.Client(project=PROJECT)
gcs = storage.Client(project=PROJECT)
store_ref = db.collection("stores").document(STORE["id"])
CAMERA_BY_ID = {c["id"]: c for c in CAMERAS}
UNIT_BY_ID = {u["id"]: u for u in UNITS}

_cache: dict = {"buckets": None, "at": 0.0}
CACHE_TTL_S = 120


# ---------- data access ----------

def seed(force: bool = False) -> int:
    snap = store_ref.get()
    if snap.exists and not force:
        return 0
    if force:
        for coll in ("buckets", "analyses", "questions", "meta"):
            for doc in store_ref.collection(coll).list_documents(page_size=500):
                doc.delete()
    store_ref.set({**STORE, "seeded_at": datetime.now(timezone.utc).isoformat()})
    for u in UNITS:
        store_ref.collection("units").document(u["id"]).set(u)
    for c in CAMERAS:
        store_ref.collection("cameras").document(c["id"]).set(c)
    rows = seed_buckets()
    batch, n = db.batch(), 0
    for r in rows:
        doc_id = f"{r['unit_id']}_{r['bucket_start'][:13]}"
        batch.set(store_ref.collection("buckets").document(doc_id), r)
        n += 1
        if n % 450 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    _cache["buckets"] = None
    return n


def load_buckets() -> list[dict]:
    if _cache["buckets"] is not None and time.time() - _cache["at"] < CACHE_TTL_S:
        return _cache["buckets"]
    rows = []
    for d in store_ref.collection("buckets").stream():
        r = d.to_dict()
        if "dwell_w" in r:  # live rows keep a visit-weighted dwell sum
            r["dwell_p50"] = r["dwell_w"] / r["visits"] if r.get("visits") else 0.0
        rows.append(r)
    _cache.update(buckets=rows, at=time.time())
    return rows


def weekend_evening_18_35(buckets: list[dict]) -> dict[str, int]:
    tz = timezone(timedelta(hours=STORE["tz_offset_h"]))
    out: dict[str, float] = {}
    for b in buckets:
        t = datetime.fromisoformat(b["bucket_start"]).astimezone(tz)
        if t.weekday() in (4, 5, 6) and t.hour >= 18:
            out[b["unit_id"]] = out.get(b["unit_id"], 0) + b.get("age_18_35", 0)
    return {k: int(v) for k, v in out.items()}


def peak_windows(buckets: list[dict], unit_id: str | None = None, top: int = 3) -> list[dict]:
    rows = [b for b in buckets if unit_id is None or b["unit_id"] == unit_id]
    grid = svi.hour_weekday_matrix(rows, STORE["tz_offset_h"])
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    cells = sorted(((grid[d][h], d, h) for d in range(7) for h in range(24)), reverse=True)[:top]
    return [{"day": days[d], "hour": f"{h:02d}:00", "unique_visitors": v} for v, d, h in cells]


def ai_context(buckets: list[dict]) -> dict:
    generic = svi.score(buckets, UNITS, STORE["base_rate_pkr"])
    by_aud = {a: {r["id"]: r["svi"] for r in svi.score(buckets, UNITS, STORE["base_rate_pkr"], a)}
              for a in svi.AUDIENCES if a != "generic"}
    we = weekend_evening_18_35(buckets)
    units = [{
        "id": r["id"], "aisle": r["aisle"], "category": r["category"], "position": r["position"],
        "svi": r["svi"], "price_pkr": r["price_pkr"],
        "footfall_per_hour": r["inputs"]["F"], "stop_rate": r["inputs"]["S"],
        "reach_rate": r["inputs"]["R"], "median_dwell_s": r["inputs"]["D"],
        "unique_visitors_7d": r["unique_visitors"], "age_mix": r["age_mix"],
        "svi_by_audience": {a: by_aud[a][r["id"]] for a in by_aud},
        "weekend_evening_18_35_visitors": we.get(r["id"], 0),
        "peaks": peak_windows(buckets, r["id"], 2),
        "sources": r["sources"],
    } for r in generic]
    recent = [d.to_dict() for d in store_ref.collection("analyses")
              .order_by("created_at", direction=firestore.Query.DESCENDING).limit(5).stream()]
    return {
        "store": {k: STORE[k] for k in ("name", "city", "base_rate_pkr")},
        "svi_formula": "Base=0.40F+0.25S+0.20R+0.15D (robust min-max), SVI=100*Base*AudienceFit, price=base_rate*SVI/median",
        "store_peaks": peak_windows(buckets),
        "units": units,
        "recent_live_analyses": [{
            "camera": a["camera_id"], "when": a["created_at"], "people": a["analysis"]["people_total"],
            "zones": [{k: z[k] for k in ("zone_id", "unique_visitors", "stops", "reaches", "notes")}
                      for z in a["analysis"]["zones"]],
        } for a in recent],
    }


# ---------- endpoints ----------

@app.on_event("startup")
def _startup() -> None:
    try:
        seed()
    except Exception as e:  # never block startup on seeding
        print("seed skipped:", e)


@app.get("/api/health")
def health():
    return {"ok": True, "model": ai.MODEL, "project": PROJECT}


@app.get("/api/store")
def get_store(audience: str = "generic"):
    if audience not in svi.AUDIENCES:
        raise HTTPException(400, f"audience must be one of {list(svi.AUDIENCES)}")
    buckets = load_buckets()
    rows = svi.score(buckets, UNITS, STORE["base_rate_pkr"], audience)
    total_unique = sum(r["unique_visitors"] for r in rows)
    visits = sum(b.get("visits", 0) for b in buckets)
    reach_v = sum(b.get("reach_visitors", 0) for b in buckets)
    dwell = sum(b.get("dwell_p50", 0) * b.get("visits", 0) for b in buckets)
    live = sum(1 for b in buckets if b.get("source") == "gemini")
    summary = store_ref.collection("meta").document("summary").get()
    return {
        "store": STORE,
        "cameras": [{k: c[k] for k in ("id", "name", "sample", "zones")} for c in CAMERAS],
        "audience": audience,
        "audiences": list(svi.AUDIENCES),
        "svi_version": svi.SVI_VERSION,
        "kpis": {
            "unit_visitors": total_unique,
            "avg_dwell_s": round(dwell / visits, 1) if visits else 0,
            "reach_rate": round(reach_v / total_unique, 3) if total_unique else 0,
            "top_unit": rows[0]["id"] if rows else None,
            "peak": peak_windows(buckets, top=1)[0] if buckets else None,
        },
        "provenance": {"seed_rows": len(buckets) - live, "live_rows": live},
        "units": rows,
        "heatmap": svi.hour_weekday_matrix(buckets, STORE["tz_offset_h"]),
        "summary": summary.to_dict() if summary.exists else None,
    }


@app.get("/api/units/{unit_id}")
def get_unit(unit_id: str, audience: str = "generic"):
    if unit_id not in UNIT_BY_ID:
        raise HTTPException(404, "unknown unit")
    buckets = load_buckets()
    rows = svi.score(buckets, UNITS, STORE["base_rate_pkr"], audience)
    row = next(r for r in rows if r["id"] == unit_id)
    mine = [b for b in buckets if b["unit_id"] == unit_id]
    tz = timezone(timedelta(hours=STORE["tz_offset_h"]))
    daily: dict[str, int] = {}
    for b in mine:
        day = datetime.fromisoformat(b["bucket_start"]).astimezone(tz).strftime("%Y-%m-%d")
        daily[day] = daily.get(day, 0) + b.get("unique_visitors", 0)
    aisle_rows = [r for r in rows if r["aisle"] == row["aisle"]]
    return {
        "unit": row,
        "heatmap": svi.hour_weekday_matrix(mine, STORE["tz_offset_h"]),
        "daily": [{"day": d, "unique_visitors": v} for d, v in sorted(daily.items())],
        "aisle_avg_svi": round(sum(r["svi"] for r in aisle_rows) / len(aisle_rows), 1),
        "peaks": peak_windows(buckets, unit_id),
    }


@app.post("/api/analyze")
async def analyze(camera_id: str = Form(...), video: UploadFile | None = File(None)):
    camera = CAMERA_BY_ID.get(camera_id)
    if not camera:
        raise HTTPException(400, "unknown camera_id")
    bucket = gcs.bucket(BUCKET)
    if video is not None and video.filename:
        data = await video.read()
        if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"video must be under {MAX_UPLOAD_MB} MB")
        blob_name = f"uploads/{uuid.uuid4().hex}.mp4"  # bucket lifecycle deletes after 1 day
        bucket.blob(blob_name).upload_from_string(data, content_type=video.content_type or "video/mp4")
        source = "upload"
    else:
        blob_name = f"samples/{camera['sample']}"
        source = "sample"
    uri = f"gs://{BUCKET}/{blob_name}"

    try:
        analysis, meta = ai.analyze_video(uri, camera)
    except Exception as e:
        raise HTTPException(502, f"Gemini analysis failed: {e}") from e

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    batch = db.batch()
    for z in analysis["zones"]:
        doc = store_ref.collection("buckets").document(f"{z['zone_id']}_{now.isoformat()[:13]}_live")
        batch.set(doc, {
            "unit_id": z["zone_id"], "bucket_start": now.isoformat(), "source": "gemini",
            "visits": firestore.Increment(z["visits"]),
            "unique_visitors": firestore.Increment(z["unique_visitors"]),
            "stops": firestore.Increment(z["stops"]),
            "reach_visitors": firestore.Increment(z["reach_visitors"]),
            "reaches": firestore.Increment(z["reaches"]),
            "dwell_w": firestore.Increment(z["dwell_p50_s"] * z["visits"]),
            **{band: firestore.Increment(n) for band, n in z["age_bands"].items()},
        }, merge=True)
    record = {
        "camera_id": camera_id, "source": source, "video": blob_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "analysis": analysis, "meta": meta,
    }
    ref = store_ref.collection("analyses").document()
    batch.set(ref, record)
    batch.commit()
    _cache["buckets"] = None
    if source == "upload":
        try:
            bucket.blob(blob_name).delete()  # privacy: raw video is not retained
            record["video"] = "deleted after analysis"
        except Exception:
            pass
    return {"id": ref.id, **record}


@app.get("/api/analyses")
def list_analyses(limit: int = 20):
    docs = store_ref.collection("analyses").order_by(
        "created_at", direction=firestore.Query.DESCENDING).limit(min(limit, 50)).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


class AskBody(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/ask")
def ask(body: AskBody):
    q = body.question.strip()[:500]
    if not q:
        raise HTTPException(400, "empty question")
    ctx = ai_context(load_buckets())
    try:
        answer, meta = ai.ask(q, ctx, body.history)
    except Exception as e:
        raise HTTPException(502, f"Gemini failed: {e}") from e
    store_ref.collection("questions").add({
        "question": q, "answer": answer, "meta": meta,
        "created_at": datetime.now(timezone.utc).isoformat()})
    return {"answer": answer, "meta": meta}


@app.post("/api/summary")
def refresh_summary():
    ctx = ai_context(load_buckets())
    text = ai.weekly_summary(ctx)
    doc = {"text": text, "model": ai.MODEL, "created_at": datetime.now(timezone.utc).isoformat()}
    store_ref.collection("meta").document("summary").set(doc)
    return doc


@app.post("/api/admin/seed")
def admin_seed(x_admin_token: str = Header("")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(403, "forbidden")
    return {"rows": seed(force=True)}
