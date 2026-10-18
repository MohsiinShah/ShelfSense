"""Benchmark the live deployment: Gemini video analysis, grounded Q&A, and dashboard API latency."""
import json, statistics as st, sys, time, urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://shelfsense-demo.web.app/api"
RUNS = 3

def call(method, path, data=None, headers=None):
    t = time.perf_counter()
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers or {})
    body = json.load(urllib.request.urlopen(req, timeout=180))
    return body, time.perf_counter() - t

def form(fields):
    b = "----shelfsense"
    parts = "".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in fields.items())
    return (parts + f"--{b}--\r\n").encode(), {"Content-Type": f"multipart/form-data; boundary={b}"}

out = {"video": {}, "ask": [], "store": []}
for cam in ["cam-01", "cam-02", "cam-03", "cam-04"]:
    rows = []
    for _ in range(RUNS):
        data, h = form({"camera_id": cam})
        r, wall = call("POST", "/analyze", data, h)
        rows.append({"wall_s": round(wall, 2), "model_s": r["meta"]["latency_s"], "in_tok": r["meta"]["input_tokens"],
                     "out_tok": r["meta"]["output_tokens"], "people": r["analysis"]["people_total"],
                     "zone_visitors": [z["unique_visitors"] for z in r["analysis"]["zones"]],
                     "events": len(r["analysis"]["events"]), "quality": r["analysis"]["data_quality"][:60]})
    out["video"][cam] = rows
    print(cam, rows, flush=True)

QS = ["Which shelf reaches the most 18-35 shoppers on weekend evenings?",
      "Which shelves are under-priced for the attention they get?",
      "When should I staff the produce hall?",
      "What is the suggested rent for A28-L and why?",
      "Compare the end-caps in aisles 1, 6 and 28."]
for q in QS:
    r, wall = call("POST", "/ask", json.dumps({"question": q}).encode(), {"Content-Type": "application/json"})
    out["ask"].append({"q": q, "wall_s": round(wall, 2), "model_s": r["meta"]["latency_s"]})
for _ in range(10):
    _, wall = call("GET", "/store?audience=18-35")
    out["store"].append(round(wall, 3))

walls = [r["wall_s"] for rows in out["video"].values() for r in rows]
out["summary"] = {
    "video_runs": len(walls), "video_wall_median_s": st.median(walls), "video_wall_max_s": max(walls),
    "video_in_tok_median": st.median(r["in_tok"] for rows in out["video"].values() for r in rows),
    "video_out_tok_median": st.median(r["out_tok"] for rows in out["video"].values() for r in rows),
    "ask_wall_median_s": st.median(a["wall_s"] for a in out["ask"]), "ask_wall_max_s": max(a["wall_s"] for a in out["ask"]),
    "store_median_ms": round(st.median(out["store"]) * 1000), "store_max_ms": round(max(out["store"]) * 1000),
    "people_by_cam": {c: [r["people"] for r in rows] for c, rows in out["video"].items()},
}
json.dump(out, open("docs/benchmark.json", "w"), indent=1)
print(json.dumps(out["summary"], indent=1))
