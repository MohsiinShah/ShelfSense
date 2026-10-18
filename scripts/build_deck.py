"""Fill the AI Builder Cup submission template with ShelfSense content.

Usage: python3 scripts/build_deck.py <template.pptx> <out.pptx>
Adds shapes to the template's own slides (keeping its header, footer and title boxes),
removes the organiser's instruction slide, and embeds the architecture diagram and screenshots.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile
from html import escape
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE, OUT = sys.argv[1], sys.argv[2]
BENCH = json.load(open(ROOT / "docs/benchmark.json"))["summary"]

LINKS = {
    "repo": os.environ.get("REPO_URL", "https://github.com/MohsiinShah/ShelfSense"),
    "video": os.environ.get("VIDEO_URL", ""),
    "site": "https://shelfsense-demo.web.app",
}

# Palette: the template's near-black ink plus a ShelfSense teal accent.
INK, MUTED, LINE = "1F2937", "5B6474", "D9DEE4"
TEAL, TEAL_SOFT, CARD = "0F766E", "E6F4F1", "F5F7F9"
FONT, FONT_MED, FONT_SEMI = "Google Sans Flex", "Google Sans Flex Medium", "Google Sans Flex SemiBold"

EMU = 914400
def E(inches): return int(inches * EMU)

# Content area below the template header strip and title, above the footer line.
X0, X1 = 0.38, 9.62
Y0, Y1 = 1.30, 5.45

_id = [1000]
def nid():
    _id[0] += 1
    return _id[0]


def run(text, size=12, color=INK, font=FONT, bold=False, link=None):
    b = ' b="1"' if bold else ""
    h = f'<a:hlinkClick r:id="{link}"/>' if link else ""
    return (f'<a:r><a:rPr lang="en-GB" sz="{int(size * 100)}"{b} dirty="0"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill>'
            f'<a:latin typeface="{font}"/><a:ea typeface="{font}"/><a:cs typeface="{font}"/><a:sym typeface="{font}"/>{h}</a:rPr>'
            f'<a:t xml:space="preserve">{escape(text)}</a:t></a:r>')


def para(runs, align="l", bullet=False, space_after=4, line=None):
    if isinstance(runs, list):
        runs = "".join(runs)
    elif not runs.startswith("<a:r>"):
        runs = run(runs)
    bu = ('<a:buClr><a:srgbClr val="0F766E"/></a:buClr><a:buSzPct val="100000"/><a:buFont typeface="Arial"/><a:buChar char="•"/>'
          if bullet else "<a:buNone/>")
    ind = ' marL="171450" indent="-171450"' if bullet else ' marL="0" indent="0"'
    ln = f'<a:lnSpc><a:spcPct val="{line}"/></a:lnSpc>' if line else ""
    return f'<a:p><a:pPr{ind} algn="{align}">{ln}<a:spcBef><a:spcPts val="0"/></a:spcBef><a:spcAft><a:spcPts val="{int(space_after * 100)}"/></a:spcAft>{bu}</a:pPr>{runs}</a:p>'


def shape(x, y, w, h, paras="", fill=None, line=None, geom="rect", anchor="t", inset=0.08, name="Text", radius=None):
    fill_xml = f'<a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>' if fill else "<a:noFill/>"
    line_xml = f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else "<a:ln><a:noFill/></a:ln>"
    av = f'<a:gd name="adj" fmla="val {radius}"/>' if radius is not None else ""
    ins = E(inset)
    body = paras or para(run(""))
    i = nid()
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="{name} {i}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm><a:prstGeom prst="{geom}"><a:avLst>{av}</a:avLst></a:prstGeom>{fill_xml}{line_xml}</p:spPr>'
            f'<p:txBody><a:bodyPr wrap="square" lIns="{ins}" tIns="{ins}" rIns="{ins}" bIns="{ins}" anchor="{anchor}"><a:normAutofit/></a:bodyPr><a:lstStyle/>{body}</p:txBody></p:sp>')


def arrow(x, y, w, h, color=TEAL):
    i = nid()
    return (f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Arrow {i}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm><a:prstGeom prst="rightArrow"><a:avLst/></a:prstGeom>'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>')


def picture(rid, x, y, w, h, name="Picture", border=True):
    i = nid()
    ln = f'<a:ln w="9525"><a:solidFill><a:srgbClr val="{LINE}"/></a:solidFill></a:ln>' if border else "<a:ln><a:noFill/></a:ln>"
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{i}" name="{name} {i}" descr="{escape(name)}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{E(x)}" y="{E(y)}"/><a:ext cx="{E(w)}" cy="{E(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom>{ln}</p:spPr></p:pic>')


def card(x, y, w, h, title, lines, title_size=12, body_size=10.5, fill=CARD, kicker=None):
    ps = []
    if kicker:
        ps.append(para(run(kicker, 8.5, TEAL, FONT_SEMI), space_after=2))
    ps.append(para(run(title, title_size, INK, FONT_SEMI), space_after=4))
    for ln in lines:
        ps.append(para(run(ln, body_size, MUTED), space_after=3))
    return shape(x, y, w, h, "".join(ps), fill=fill, geom="roundRect", radius=6000, inset=0.12, name="Card")


def stat(x, y, w, value, label, value_size=26, note=None):
    ps = para(run(value, value_size, TEAL, FONT_SEMI), space_after=0) + para(run(label, 10, INK, FONT_MED), space_after=1)
    if note:
        ps += para(run(note, 8.5, MUTED), space_after=0)
    return shape(x, y, w, 1.05, ps, name="Stat", inset=0.02)


# ---------------------------------------------------------------- package helpers
work = Path(tempfile.mkdtemp(prefix="deck-"))
with zipfile.ZipFile(TEMPLATE) as z:
    z.extractall(work)
P = work / "ppt"


def slide_path(n): return P / "slides" / f"slide{n}.xml"


def add_rel(n, rtype, target, external=False):
    rels = P / "slides" / "_rels" / f"slide{n}.xml.rels"
    x = rels.read_text()
    ids = [int(m) for m in re.findall(r'Id="rId(\d+)"', x)]
    rid = f"rId{max(ids) + 1}"
    mode = ' TargetMode="External"' if external else ""
    x = x.replace("</Relationships>", f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/{rtype}" Target="{escape(target)}"{mode}/></Relationships>')
    rels.write_text(x)
    return rid


_media = [0]
def add_image(n, src, max_w=1800, crop_top=0.0, ratio=None):
    im = Image.open(src).convert("RGB")
    if crop_top:
        im = im.crop((0, int(im.height * crop_top), im.width, im.height))
    if ratio:  # keep the top of the screen at this width:height
        im = im.crop((0, 0, im.width, min(im.height, int(im.width / ratio))))
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    _media[0] += 1
    name = f"shelfsense{_media[0]}.png"
    im.save(P / "media" / name, optimize=True)
    return add_rel(n, "image", f"../media/{name}"), im.width / im.height


def append(n, xml):
    p = slide_path(n)
    x = p.read_text()
    p.write_text(x.replace("</p:spTree>", xml + "</p:spTree>", 1))


def remove_shape(n, shape_name):
    p = slide_path(n)
    x = p.read_text()
    x2 = re.sub(r'<p:sp>(?:(?!</p:sp>).)*?name="' + re.escape(shape_name) + r'".*?</p:sp>', "", x, count=1, flags=re.S)
    assert x2 != x, f"shape {shape_name} not found on slide {n}"
    p.write_text(x2)


def set_text(n, old, new):
    p = slide_path(n)
    x = p.read_text()
    assert f"<a:t>{old}</a:t>" in x, (n, old)
    p.write_text(x.replace(f"<a:t>{old}</a:t>", f"<a:t>{escape(new)}</a:t>", 1))


def fit(img_ratio, x, y, w, h):
    """Largest box with img_ratio inside (x, y, w, h), centred."""
    if w / h > img_ratio:
        nw = h * img_ratio
        return x + (w - nw) / 2, y, nw, h
    nh = w / img_ratio
    return x, y + (h - nh) / 2, w, nh


# ---------------------------------------------------------------- slide 1: team details
set_text(1, "Problem Statement: ", "Problem Statement: Shelf space is priced by position, not by how many shoppers actually see it.")

# ---------------------------------------------------------------- slide 3: brief about the idea
append(3, shape(X0, 1.30, 5.55, 3.9, "".join([
    para(run("ShelfSense", 22, INK, FONT_SEMI), space_after=2),
    para(run("AI that turns a store's existing CCTV into a price tag for every shelf.", 13, TEAL, FONT_MED), space_after=10),
    para(run("Brands pay retailers for end-caps, eye-level slots and promotional bays, but that space is priced by position and negotiation. "
             "A shelf passed by 2,000 shoppers a day can cost the same as one passed by 200.", 11, MUTED), space_after=8, line=110000),
    para(run("ShelfSense sends store camera clips to Gemini, which measures for every shelf zone who walks past, who stops, who reaches for a product, "
             "how long they stay and their approximate age band. Those counts become a Shelf Value Index (0–100) and a suggested monthly rent. "
             "An AI assistant answers questions like “Which shelf reaches the most 18–35 shoppers on weekend evenings?”", 11, MUTED), space_after=8, line=110000),
    para([run("Live today: ", 11, INK, FONT_SEMI), run(LINKS["site"], 11, TEAL, FONT_MED)], space_after=0),
]), name="Idea"))
sx = 6.25
append(3, shape(sx, 1.30, 3.37, 3.9, "", fill=TEAL_SOFT, geom="roundRect", radius=5000, name="Panel"))
append(3, stat(sx + 0.25, 1.45, 3.0, f"{BENCH['video_wall_median_s']:.1f} s", "to analyse a store clip with Gemini", note="median of 12 live runs"))
append(3, stat(sx + 0.25, 2.65, 3.0, "4 → 12", "cameras → priced shelf zones", note="in the live demo store"))
append(3, stat(sx + 0.25, 3.85, 3.0, "0", "faces or identities stored", note="only anonymous counts reach Firestore"))

# ---------------------------------------------------------------- slide 4: opportunities
remove_shape(4, "Google Shape;79;p16")
append(4, shape(0.265, 0.66, 8.9, 0.5, para(run("Opportunities", 16, INK, FONT_MED)), name="Title", inset=0.1))
cw, gap = 2.93, 0.24
cards = [
    ("HOW IS IT DIFFERENT?", "Prices the shelf, not the store",
     ["Footfall counters (ShopperTrak, RetailNext) count the store entrance.",
      "Shelf recognition (Trax) checks stock and planograms.",
      "ShelfSense measures who sees each shelf and outputs a price."]),
    ("HOW DOES IT SOLVE IT?", "Attention becomes a number",
     ["Gemini turns camera footage into per-zone visitors, stops, reaches, dwell and age mix.",
      "The SVI blends them; rent = base rate × SVI ÷ store median.",
      "Brands get proof of what a placement delivered."]),
    ("USP", "Existing cameras, privacy-first",
     ["No new hardware for the prototype: any store clip works.",
      "Audience-aware pricing: the same shelf is worth more to the brand whose shoppers walk past it.",
      "Only anonymous counts are kept; video is deleted after analysis."]),
]
for i, (k, t, ls) in enumerate(cards):
    append(4, card(X0 + i * (cw + gap), 1.35, cw, 2.55, t, ls, kicker=k, body_size=11))
append(4, shape(X0, 4.08, X1 - X0, 0.85, "".join([
    para([run("Market  ", 11, TEAL, FONT_SEMI), run("Modern retail chains in Pakistan (hypermarkets, supermarkets, pharmacies) and the FMCG brands that rent their shelves.", 10.5, INK)], space_after=3),
    para([run("Model  ", 11, TEAL, FONT_SEMI), run("Retailers pay a per-store subscription to price their space; brands pay for reach and audience reports on their placements.", 10.5, INK)], space_after=0),
]), fill=TEAL_SOFT, geom="roundRect", radius=8000, inset=0.14, anchor="ctr", name="Market"))

# ---------------------------------------------------------------- slide 5: features
feats = [
    ("Video → shelf metrics", "Gemini 3 Flash watches a clip and returns visitors, stops, reaches, dwell, age bands and a timestamped event log per zone."),
    ("Shelf Value Index", "0.40 footfall + 0.25 stop rate + 0.20 reach + 0.15 dwell, robust-normalised within the store."),
    ("Suggested rent", "Base rate × SVI ÷ store median SVI, with a 40% floor. Sortable ranking with CSV export."),
    ("Brand audience view", "AudienceFit re-weights every shelf by how well its shoppers match a brand's target age group."),
    ("Ask ShelfSense", "Plain-language questions answered by Gemini from Firestore data only, citing shelf ids."),
    ("Floor heatmap & insights", "Shelves coloured by any metric, hour × weekday heatmaps, and a weekly summary written by Gemini."),
]
cw, ch = 2.93, 1.72
for i, (t, d) in enumerate(feats):
    r, c = divmod(i, 3)
    append(5, card(X0 + c * (cw + 0.24), 1.35 + r * (ch + 0.2), cw, ch, t, [d], kicker=f"0{i + 1}", body_size=11))

# ---------------------------------------------------------------- slide 6: process flow + use cases
steps = [("1  Capture", "Store camera clip, or upload"), ("2  Cloud Run", "API stores clip, builds zone prompt"),
         ("3  Gemini", "Counts per zone, JSON schema"), ("4  Firestore", "Hourly buckets: seed + live"),
         ("5  Score", "SVI, audience fit, rent"), ("6  Act", "Dashboard, chat, CSV")]
sw, sg = 1.31, 0.25
for i, (t, d) in enumerate(steps):
    x = X0 + i * (sw + sg)
    append(6, shape(x, 1.35, sw, 1.0, para(run(t, 11, "FFFFFF", FONT_SEMI), space_after=2) + para(run(d, 9, "E6F4F1"), space_after=0),
                    fill=TEAL, geom="roundRect", radius=10000, inset=0.09, name="Step"))
    if i < len(steps) - 1:
        append(6, arrow(x + sw + 0.04, 1.77, sg - 0.08, 0.16))
append(6, shape(X0, 2.55, 6, 0.35, para(run("Use cases", 12, INK, FONT_SEMI)), name="Label", inset=0.02))
uses = [("Retailer", ["Price end-caps and bays from evidence", "Staff the floor for real peaks", "Re-plan layout from the heatmap"]),
        ("FMCG brand", ["Choose shelves that reach its audience", "Verify reach and attention after launch", "Compare placements across stores"]),
        ("Store manager", ["Ask questions in plain language", "Weekly summary with one action", "Spot under-priced shelves"])]
for i, (t, ls) in enumerate(uses):
    append(6, card(X0 + i * (2.93 + 0.24), 2.95, 2.93, 1.7, t, ["• " + l for l in ls], body_size=11))

# ---------------------------------------------------------------- slide 7: wireframes (real screens)
rid_a, ra = add_image(7, ROOT / "docs/screenshots/2-floor.png")
rid_b, rb = add_image(7, ROOT / "docs/screenshots/3-pricing.png")
w = (X1 - X0 - 0.3) / 2
for j, (rid, r, cap) in enumerate([(rid_a, ra, "Floor heatmap + shelf detail: how each SVI is built"), (rid_b, rb, "Shelf pricing in a brand's view (ages 18–35)")]):
    x = X0 + j * (w + 0.3)
    bx, by, bw, bh = fit(r, x, 1.3, w, 3.0)
    append(7, picture(rid, bx, by, bw, bh, cap))
    append(7, shape(x, 4.38, w, 0.5, para(run(cap, 10, MUTED), align="ctr"), name="Caption", inset=0.02))

# ---------------------------------------------------------------- slide 8: architecture
rid, r = add_image(8, ROOT / "docs/architecture.png", max_w=2400, crop_top=0.17)
bx, by, bw, bh = fit(r, X0, 1.22, X1 - X0, 3.75)
append(8, picture(rid, bx, by, bw, bh, "ShelfSense architecture diagram", border=False))

# ---------------------------------------------------------------- slide 9: technologies
tech = [("Gemini 3 Flash · Vertex AI", "Video understanding with structured JSON output; grounded Q&A; weekly summary"),
        ("Cloud Run", "FastAPI service in a container, autoscaling, dedicated service account"),
        ("Firestore", "System of record: units, cameras, hourly buckets, analyses, questions"),
        ("Firebase Hosting", "Dashboard + /api/** rewrite to Cloud Run on one origin"),
        ("Cloud Storage", "Video bucket; uploads deleted after analysis + 1-day lifecycle"),
        ("Cloud Build · Artifact Registry", "Source-to-container builds for every deploy"),
        ("Python · FastAPI · Pydantic", "API, SVI engine, Gemini response schema"),
        ("JavaScript · Plotly", "Dashboard charts, floor plan SVG, chat UI")]
cw, ch = 2.22, 1.62
for i, (t, d) in enumerate(tech):
    r_, c = divmod(i, 4)
    fill = TEAL_SOFT if i < 4 else CARD
    append(9, card(X0 + c * (cw + 0.12), 1.35 + r_ * (ch + 0.18), cw, ch, t, [d], title_size=11, body_size=9.5, fill=fill))
append(9, shape(X0, 4.95, 9, 0.3, para(run("Shaded: the four required technologies. Demo video narration uses Cloud Text-to-Speech.", 8.5, MUTED)), name="Note", inset=0.02))

# ---------------------------------------------------------------- slide 10: cost
per_clip = BENCH["video_in_tok_median"] / 1e6 * 0.50 + BENCH["video_out_tok_median"] / 1e6 * 3.00
rows = [("Item", "Prototype (today)", "Pilot store (estimate)"),
        ("Gemini video analysis", f"≈ US${per_clip:.4f} per 15 s clip", "Edge detection; Gemini for audits + Q&A"),
        ("Cloud Run API", "≈ US$10 / month (1 warm instance)", "≈ US$10–20 / month shared"),
        ("Firestore + Hosting + Storage", "Within free tier", "< US$5 / store / month"),
        ("Edge device", "Not needed (clips)", "≈ US$250 one-time (Jetson Orin Nano class)"),
        ("Cameras", "Existing", "Existing IP cameras")]
tw = [2.45, 3.3, 3.49]
y = 1.35
for ri, row in enumerate(rows):
    x = X0
    for ci, cell in enumerate(row):
        head = ri == 0
        append(10, shape(x, y, tw[ci] - 0.04, 0.5, para(run(cell, 10.5 if not head else 10, "FFFFFF" if head else (INK if ci == 0 else MUTED), FONT_SEMI if head or ci == 0 else FONT), space_after=0),
                         fill=TEAL if head else (CARD if ri % 2 else None), anchor="ctr", inset=0.1, name="Cell"))
        x += tw[ci]
    y += 0.54
append(10, shape(X0, y + 0.08, 9.2, 0.7, para(run(f"Per-clip cost uses measured median tokens ({int(BENCH['video_in_tok_median']):,} in / {int(BENCH['video_out_tok_median'])} out) at Gemini 3 Flash list price (US$0.50 / US$3.00 per million). "
                                                  "Other figures are estimates to be confirmed in a pilot. Because raw video never leaves the store in production, cloud cost stays small and flat per store.", 9, MUTED), line=110000),
                 name="Note", inset=0.02))

# ---------------------------------------------------------------- slide 11: snapshots
shots = [("4-live.png", "Live analysis: Gemini counts per zone with a clickable event log"), ("1-overview.png", "Overview: KPIs, Gemini weekly summary, footfall by hour"),
         ("5-ask.png", "Ask ShelfSense: grounded answers citing shelves"), ("3-pricing.png", "Pricing table with audience fit")]
w, h = (X1 - X0 - 0.25) / 2, 1.62
for i, (f, cap) in enumerate(shots):
    r_, c = divmod(i, 2)
    rid, ratio = add_image(11, ROOT / "docs/screenshots" / f, max_w=1600, ratio=2.3)
    x, y = X0 + c * (w + 0.25), 1.25 + r_ * (h + 0.38)
    bx, by, bw, bh = fit(ratio, x, y, w, h)
    append(11, picture(rid, bx, by, bw, bh, cap))
    append(11, shape(x, y + h + 0.01, w, 0.3, para(run(cap, 9, MUTED), align="ctr", space_after=0), name="Caption", inset=0.01))

# ---------------------------------------------------------------- slide 12: performance
stats = [(f"{BENCH['video_wall_median_s']:.1f} s", "Gemini video analysis", f"median, end to end · worst {BENCH['video_wall_max_s']:.1f} s"),
         (f"{BENCH['ask_wall_median_s']:.1f} s", "Ask ShelfSense answer", f"5 questions · worst {BENCH['ask_wall_max_s']:.1f} s"),
         (f"{BENCH['store_median_ms'] / 1000:.2f} s", "Dashboard API", "median /store response, 10 calls"),
         ("12 / 12", "Schema-valid results", "every video run parsed into the JSON schema")]
for i, (v, l, n) in enumerate(stats):
    append(12, shape(X0 + i * 2.34, 1.3, 2.2, 1.25, para(run(v, 24, TEAL, FONT_SEMI), space_after=0) + para(run(l, 10.5, INK, FONT_MED), space_after=1) + para(run(n, 8.5, MUTED), space_after=0),
                     fill=TEAL_SOFT, geom="roundRect", radius=8000, inset=0.12, name="Stat"))
pb = BENCH["people_by_cam"]
append(12, shape(X0, 2.75, 4.5, 2.2, "".join([
    para(run("Consistency across repeated runs", 12, INK, FONT_SEMI), space_after=4),
    para(run(f"Same clip, 3 runs each. Total people counted: produce hall {pb['cam-02']}, aisle 28 {pb['cam-03']}, aisle 6 {pb['cam-04']}, aisle 1 {pb['cam-01']}.", 10, MUTED), bullet=True, space_after=3),
    para(run("Per-zone counts vary most in the busiest zone (produce hall middle: 8–12 visitors).", 10, MUTED), bullet=True, space_after=3),
    para(run(f"≈ {int(BENCH['video_in_tok_median']):,} input / {int(BENCH['video_out_tok_median'])} output tokens per 15 s clip.", 10, MUTED), bullet=True, space_after=0),
]), name="Consistency", inset=0.05))
append(12, shape(5.1, 2.75, 4.5, 2.2, "".join([
    para(run("Method and limits", 12, INK, FONT_SEMI), space_after=4),
    para(run("Measured on the live deployment (Firebase Hosting → Cloud Run → Vertex AI), 18 Oct 2026, scripts/benchmark.py in the repo.", 10, MUTED), bullet=True, space_after=3),
    para(run("Count accuracy is not yet scored against hand labels. Next: the MERL Shopping dataset's labelled reach events, then a store pilot.", 10, MUTED), bullet=True, space_after=3),
    para(run("Model: gemini-3-flash-preview, low thinking, medium media resolution.", 10, MUTED), bullet=True, space_after=0),
]), name="Method", inset=0.05))

# ---------------------------------------------------------------- slide 13: future development
phases = [("PILOT · MONTHS 1–3", "One chain, 3–5 stores", ["In-store edge box: detection + tracking on device, only counts leave", "Calibrate SVI weights against POS data", "Face blurring at the first step"]),
          ("PRODUCT · MONTHS 4–9", "Multi-store platform", ["Firebase Auth with retailer / brand tenants", "Brand portal and automated reach reports", "Store-manager mobile app"]),
          ("SCALE · MONTHS 10–18", "Marketplace", ["More chains, cross-chain brand benchmarks", "Book shelf space at the suggested price", "Export to similar emerging markets"])]
for i, (k, t, ls) in enumerate(phases):
    append(13, card(X0 + i * (2.93 + 0.24), 1.35, 2.93, 2.45, t, ["• " + l for l in ls], kicker=k, body_size=11))
append(13, shape(X0, 3.98, 9.2, 0.6, para(run("Privacy roadmap: no face images or embeddings, no tracking across days or stores, signage in store, and a DPIA before the pilot. "
                                               "We design to GDPR-style principles while Pakistan's data-protection bill is still a draft.", 9.5, MUTED), line=110000), name="Note", inset=0.02))

# ---------------------------------------------------------------- slide 14: links
remove_shape(14, "Google Shape;159;p26")
append(14, shape(0.265, 0.66, 8.9, 0.5, para(run("Provide links to your:", 16, INK, FONT_MED)), name="Title", inset=0.1))
items = [("GitHub Public Repository", LINKS["repo"]), ("Demo Video Link (3 Minutes)", LINKS["video"] or "[add link after upload]"), ("Final Product Link", LINKS["site"])]
for i, (label, url) in enumerate(items):
    y = 1.45 + i * 1.08
    rid = add_rel(14, "hyperlink", url, external=True) if url.startswith("http") else None
    append(14, shape(X0, y, 9.24, 0.88, para(run(label, 11, MUTED, FONT_MED), space_after=2) + para(run(url, 15, TEAL, FONT_SEMI, link=rid), space_after=0),
                     fill=CARD, geom="roundRect", radius=10000, inset=0.16, anchor="ctr", name="Link"))

# ---------------------------------------------------------------- slide 15: brief description (required by the submission rules)
append(15, shape(0.265, 0.66, 8.9, 0.5, para(run("Brief description: how ShelfSense uses Firebase, Firestore, Cloud Run and Gemini", 16, INK, FONT_MED)), name="Title", inset=0.1))
use = [("Gemini", "Gemini 3 Flash on Vertex AI watches each store clip and returns per-zone visitors, stops, reaches, dwell, age bands and events as schema-checked JSON. It also answers questions grounded on store data and writes the weekly summary."),
       ("Cloud Run", "Our FastAPI service runs on Cloud Run: it accepts clips, calls Gemini, writes results, computes the Shelf Value Index and prices, and serves the dashboard's API."),
       ("Firestore", "Firestore holds the store model (units, cameras), hourly attention buckets from simulated history and live Gemini runs, every analysis and question. Security rules deny direct client access."),
       ("Firebase", "Firebase Hosting serves the dashboard at shelfsense-demo.web.app and rewrites /api/** to Cloud Run, so the whole product runs on one origin.")]
for i, (t, d) in enumerate(use):
    r_, c = divmod(i, 2)
    append(15, card(X0 + c * (4.5 + 0.24), 1.35 + r_ * (1.75 + 0.18), 4.5, 1.75, t, [d], title_size=13, body_size=11, fill=TEAL_SOFT if i % 3 == 0 else CARD))

# ---------------------------------------------------------------- remove the organiser's instruction slide (slide 2)
pres = (P / "presentation.xml").read_text()
rels = (P / "_rels" / "presentation.xml.rels").read_text()
rid2 = re.search(r'Id="(rId\d+)"[^>]*Target="slides/slide2.xml"', rels) or re.search(r'Target="slides/slide2.xml"[^>]*Id="(rId\d+)"', rels)
pres = re.sub(r'<p:sldId [^>]*r:id="' + rid2.group(1) + r'"/>', "", pres)
r14 = re.search(r'Id="(rId\d+)"[^>]*Target="slides/slide14.xml"', rels).group(1)
r15 = re.search(r'Id="(rId\d+)"[^>]*Target="slides/slide15.xml"', rels).group(1)
s14 = re.search(r'<p:sldId [^>]*r:id="' + r14 + r'"/>', pres).group(0)
s15 = re.search(r'<p:sldId [^>]*r:id="' + r15 + r'"/>', pres).group(0)
pres = pres.replace(s14, "@@14@@").replace(s15, s14).replace("@@14@@", s15)
(P / "presentation.xml").write_text(pres)

# Drop the now-orphaned slide parts, then zip with [Content_Types].xml first.
import subprocess
subprocess.run([sys.executable, os.environ["PPTX_SKILL"] + "/scripts/clean.py", str(work)], check=True)
out = Path(OUT).resolve()
if out.exists():
    out.unlink()
files = sorted(f for f in work.rglob("*") if f.is_file())
files.sort(key=lambda f: f.name != "[Content_Types].xml")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(f, f.relative_to(work).as_posix())
print("wrote", out)
