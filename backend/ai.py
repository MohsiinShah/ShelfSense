"""Gemini on Vertex AI: shelf-zone video analysis, grounded Q&A, weekly summary."""
from __future__ import annotations

import json
import os
import time

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
_client: genai.Client | None = None


def client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "global"),
        )
    return _client


class AgeBands(BaseModel):
    age_lt18: int = Field(description="people who appear under 18")
    age_18_35: int
    age_35_55: int
    age_55p: int


class ZoneResult(BaseModel):
    zone_id: str
    unique_visitors: int = Field(description="distinct people who passed through or in front of this zone")
    visits: int = Field(description="passes in front of the zone; one person can pass more than once")
    stops: int = Field(description="passes where the person paused >= 2 s with body or head oriented to the shelf")
    reach_visitors: int = Field(description="distinct people who reached toward, touched or picked up a product here")
    reaches: int = Field(description="total hand-to-shelf interactions")
    dwell_p50_s: float = Field(description="median seconds a visitor spent in the zone")
    age_bands: AgeBands
    notes: str = Field(description="one short sentence on what happened at this zone")


class Event(BaseModel):
    t_s: float = Field(description="timestamp in seconds from clip start")
    zone_id: str
    kind: str = Field(description="one of: pass, stop, reach, pickup, putback")
    description: str


class VideoAnalysis(BaseModel):
    scene: str = Field(description="one-sentence description of the camera view")
    people_total: int
    zones: list[ZoneResult]
    events: list[Event]
    data_quality: str = Field(description="good / fair / poor, with the reason (occlusion, blur, camera motion, angle)")


def _video_prompt(camera: dict) -> str:
    zones = "\n".join(f"- {zid}: {desc}" for zid, desc in camera["zones"].items())
    return f"""You are the vision engine of ShelfSense, a retail analytics system that measures
how much shopper attention each shelf zone receives from a store camera.

Camera: {camera['name']}
Shelf zones to measure (use exactly these zone ids):
{zones}

Watch the whole clip and, for every zone, count:
- unique_visitors: distinct people who passed through or in front of the zone
- visits: passes in front of the zone (a person can pass more than once)
- stops: passes where the person paused for 2 seconds or more facing the shelf
- reach_visitors / reaches: people reaching toward, touching or picking up products, and the total count of such interactions
- dwell_p50_s: median seconds a visitor spent in the zone
- age_bands: approximate age band of each unique visitor from overall appearance only

List up to 25 notable events with timestamps (pass, stop, reach, pickup, putback).

Privacy rules: never identify, name or describe a specific person's face or identity.
Only produce anonymous aggregate counts. Count only what you can see; if a zone is
not visible, return zeros and say so in notes. If the camera moves, still give your
best count and mention it in data_quality."""


def analyze_video(gcs_uri: str, camera: dict) -> tuple[dict, dict]:
    """Return (analysis, meta). meta carries model, latency and token usage."""
    t0 = time.perf_counter()
    resp = client().models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_uri(file_uri=gcs_uri, mime_type="video/mp4"),
            _video_prompt(camera),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=VideoAnalysis,
            temperature=0.1,
            media_resolution=types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
        ),
    )
    latency = time.perf_counter() - t0
    analysis = VideoAnalysis.model_validate_json(resp.text).model_dump()
    # Keep only the zones this camera owns.
    analysis["zones"] = [z for z in analysis["zones"] if z["zone_id"] in camera["zones"]]
    usage = resp.usage_metadata
    meta = {
        "model": MODEL,
        "latency_s": round(latency, 2),
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
    }
    return analysis, meta


ASK_SYSTEM = """You are "Ask ShelfSense", an analyst assistant for a retailer and the brands
that rent its shelf space. Answer ONLY from the JSON data provided. Be concise (max ~120 words),
lead with the direct answer, cite shelf unit ids in square brackets like [A1-E], and quote the
numbers you used. SVI is the Shelf Value Index (0-100); price_pkr is the suggested monthly rent.
If the data cannot answer the question, say what is missing. Never invent numbers.
Rows with source "seed" are simulated history; rows with source "gemini" come from live video analysis."""


def ask(question: str, context: dict, history: list[dict] | None = None) -> tuple[str, dict]:
    t0 = time.perf_counter()
    contents = []
    for turn in (history or [])[-6:]:
        contents.append(types.Content(role=turn["role"], parts=[types.Part.from_text(text=turn["text"])]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(
        text=f"DATA:\n{json.dumps(context, separators=(',', ':'))}\n\nQUESTION: {question}")]))
    resp = client().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(system_instruction=ASK_SYSTEM, temperature=0.2),
    )
    return resp.text.strip(), {"model": MODEL, "latency_s": round(time.perf_counter() - t0, 2)}


def weekly_summary(context: dict) -> str:
    resp = client().models.generate_content(
        model=MODEL,
        contents=[f"DATA:\n{json.dumps(context, separators=(',', ':'))}\n\n"
                  "Write this week's store summary for the retail manager: exactly 4 short bullet "
                  "points (markdown '- '), covering the most valuable shelf, the most under-priced "
                  "opportunity, the peak traffic window, and one concrete layout or pricing action. "
                  "Cite unit ids in [brackets] and use the numbers."],
        config=types.GenerateContentConfig(system_instruction=ASK_SYSTEM, temperature=0.3),
    )
    return resp.text.strip()
