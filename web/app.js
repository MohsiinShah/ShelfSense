"use strict";

const API = "/api";
const state = { store: null, audience: "generic", camera: null, selectedUnit: null, sort: { key: "svi", dir: -1 }, chat: [] };
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const POS = { eye_level: "Eye level", end_cap: "End-cap", bottom: "Bottom shelf", top: "Top shelf", table: "Display table", wall: "Wall chiller" };
const AGE = { age_lt18: "<18", age_18_35: "18–35", age_35_55: "35–55", age_55p: "55+" };
const METRIC = { svi: "SVI", F: "Footfall / hr", S: "Stop rate", R: "Reach rate", D: "Median dwell (s)" };
// 24px stroke icons (Lucide-style paths).
const ICONS = {
  people: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
  hand: '<path d="M18 11V6a2 2 0 0 0-4 0v5M14 10V4a2 2 0 0 0-4 0v6M10 10.5V6a2 2 0 0 0-4 0v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>',
  star: '<path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>',
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
  camera: '<path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/>',
};
const icon = (name) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name]}</svg>`;
const fmt = new Intl.NumberFormat("en-PK");
const pkr = (n) => "PKR " + fmt.format(n);
const pct = (x) => (x * 100).toFixed(0) + "%";

async function api(path, opts = {}) {
  const r = await fetch(API + path, opts);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Minimal, safe markdown: escape first, then bullets, bold and [UNIT] citations.
function md(text) {
  const units = new Set((state.store?.units || []).map((u) => u.id));
  let h = esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // Link every known shelf id, bracketed or not.
    .replace(/\[?\b([A-Z][A-Z0-9]*-[A-Z]+)\b\]?/g, (m, id) => units.has(id) ? `<span class="cite" data-unit="${id}">${id}</span>` : m);
  // Group consecutive bullet lines into lists; everything else is a paragraph.
  let out = "", list = null;
  for (const line of h.split("\n")) {
    const m = line.match(/^\s*(?:([-*•])|\d+[.)])\s+(.*)$/);
    const kind = m ? (m[1] ? "ul" : "ol") : null;
    if (list && kind !== list) { out += `</${list}>`; list = null; }
    if (kind) { if (!list) { out += `<${kind}>`; list = kind; } out += `<li>${m[2]}</li>`; continue; }
    if (line.trim()) out += `<p>${line}</p>`;
  }
  return out + (list ? `</${list}>` : "");
}

// Sequential colour ramp (colour-blind safe, teal family) for SVI and metrics.
const RAMP = ["#e6f4f1", "#b8e3da", "#7fcbbd", "#45ad9d", "#1f8a7c", "#0f6b61", "#0a4f48"];
function rampColor(t) {
  t = Math.max(0, Math.min(1, t));
  return RAMP[Math.round(t * (RAMP.length - 1))];
}
const isDark = () => matchMedia("(prefers-color-scheme: dark)").matches;
function plotLayout(extra = {}) {
  const ink = isDark() ? "#93a1b2" : "#5b6474";
  return {
    margin: { l: 44, r: 12, t: 8, b: 36 }, paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: "Inter, system-ui, sans-serif", size: 12, color: ink },
    xaxis: { gridcolor: isDark() ? "#233040" : "#eef1f4", zeroline: false },
    yaxis: { gridcolor: isDark() ? "#233040" : "#eef1f4", zeroline: false },
    ...extra,
  };
}
const plotCfg = { displayModeBar: false, responsive: true };

// ---------- load ----------
async function loadStore() {
  const s = await api(`/store?audience=${encodeURIComponent(state.audience)}`);
  state.store = s;
  // Generic ranking is the baseline the brand views are compared against.
  if (state.audience === "generic") state.base = s.units;
  else if (!state.base) state.base = (await api("/store?audience=generic")).units;
  $("#storeName").textContent = `${s.store.name} · base rate ${pkr(s.store.base_rate_pkr)}/month`;
  renderKpis(); renderSummary(); renderTop(); renderPricing(); renderFloor();
  if (state.selectedUnit) showUnit(state.selectedUnit);
  if (!state.camera) renderCams();
  $("#provenance").textContent = `Data: ${fmt.format(s.provenance.seed_rows)} simulated hourly rows (7-day demo history) + ${fmt.format(s.provenance.live_rows)} live rows from Gemini video analysis · ${s.svi_version}`;
  if (!s.summary) refreshSummary(true);
}

function renderKpis() {
  const k = state.store.kpis;
  const top = state.store.units[0];
  const tiles = [
    ["people", "Shelf visitors (7 d)", fmt.format(k.unit_visitors), "unique passes across 12 shelf zones"],
    ["clock", "Avg dwell", k.avg_dwell_s + " s", "visit-weighted median"],
    ["hand", "Reach rate", pct(k.reach_rate), "visitors who touched a product"],
    ["star", "Top shelf", k.top_unit, `${top.category} · SVI ${top.svi}`],
    ["calendar", "Peak window", k.peak ? `${k.peak.day} ${k.peak.hour}` : "—", "busiest hour of the week"],
  ];
  $("#kpis").innerHTML = tiles.map(([i, l, v, s]) => `<div class="kpi"><div class="label">${icon(i)}${l}</div><div class="value">${esc(v)}</div><div class="sub">${esc(s)}</div></div>`).join("");
}

function renderSummary() {
  const s = state.store.summary;
  if (!s) return;
  $("#summary").classList.remove("muted", "loading");
  $("#summary").innerHTML = md(s.text);
  $("#summaryMeta").textContent = `Generated by ${s.model} · ${new Date(s.created_at).toLocaleString()}`;
}

async function refreshSummary(auto = false) {
  const btn = $("#refreshSummary");
  btn.disabled = true;
  $("#summary").classList.add("loading");
  $("#summary").innerHTML = '<span class="spinner"></span>Gemini is reading this week’s shelf data…';
  try {
    state.store.summary = await api("/summary", { method: "POST" });
    renderSummary();
  } catch (e) {
    $("#summary").textContent = (auto ? "" : "Could not generate summary: ") + e.message;
  } finally { btn.disabled = false; }
}

function renderTop() {
  const rows = state.store.units.slice(0, 8).reverse();
  Plotly.react("topChart", [{
    type: "bar", orientation: "h", x: rows.map((r) => r.svi), y: rows.map((r) => `${r.id} · ${r.category}`),
    marker: { color: rows.map((r) => rampColor(r.svi / 100)) },
    text: rows.map((r) => `${r.svi}  ·  ${pkr(r.price_pkr)}`), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{y}<br>SVI %{x}<extra></extra>",
  }], plotLayout({ margin: { l: 170, r: 110, t: 4, b: 28 }, xaxis: { range: [0, 100], showgrid: false } }), plotCfg);

  drawStoreHeat();
}

function drawStoreHeat() {
  const sum = state.store.heatmap;
  const hours = [...Array(24).keys()].slice(9, 23);
  Plotly.react("storeHeat", [{
    type: "heatmap", z: sum.map((r) => r.slice(9, 23)), x: hours.map((h) => `${h}:00`), y: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    colorscale: RAMP.map((c, i) => [i / (RAMP.length - 1), c]), hovertemplate: "%{y} %{x}<br>%{z} shelf visitors<extra></extra>", showscale: false,
  }], plotLayout({ margin: { l: 40, r: 8, t: 4, b: 30 }, yaxis: { autorange: "reversed" } }), plotCfg);
}

// ---------- floor ----------
function metricValue(u, m) { return m === "svi" ? u.svi : u.inputs[m]; }

function renderFloor() {
  const m = $("#floorMetric").value;
  const units = state.store.units;
  const vals = units.map((u) => metricValue(u, m));
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const norm = (v) => (hi - lo ? (v - lo) / (hi - lo) : 0.5);
  const svg = $("#floor");
  // Store shell: walls, aisle labels, checkout and entrance, then shelves, then cameras on top.
  let out = `<rect class="shell" x="0.6" y="0.6" width="98.8" height="58.8" rx="2"/>`;
  out += `<path class="door" d="M4 59.4 H22"/><text class="zone-label" x="13" y="57.4" text-anchor="middle">ENTRANCE</text>`;
  out += `<text class="zone-label" x="43" y="12.2" text-anchor="middle">FRESH PRODUCE HALL</text>`;
  for (const [x, label] of [[14, "AISLE 1"], [72, "AISLE 28"], [92.5, "AISLE 6"]]) out += `<text class="zone-label" x="${x}" y="33.6" text-anchor="middle">${label}</text>`;
  for (const x of [64, 76, 88]) out += `<rect class="till" x="${x}" y="50" width="9" height="3.2" rx="0.6"/>`;
  out += `<text class="zone-label" x="81" y="56.6" text-anchor="middle">CHECKOUT</text>`;
  for (const u of units) {
    const [x, y, w, h] = u.rect;
    const t = norm(metricValue(u, m));
    const fill = rampColor(t);
    const ink = t > 0.55 ? "#ffffff" : "#0f172a";
    const v = m === "svi" ? u.svi : m === "S" || m === "R" ? pct(u.inputs[m]) : u.inputs[m].toFixed(m === "D" ? 1 : 0);
    const vertical = h > w * 1.5;
    const tx = x + w / 2, ty = y + h / 2;
    out += `<g><rect class="unit${state.selectedUnit === u.id ? " sel" : ""}" data-unit="${u.id}" x="${x}" y="${y}" width="${w}" height="${h}" rx="1" fill="${fill}"><title>${esc(u.id)} · ${esc(u.category)} · ${METRIC[m]} ${v}</title></rect>`;
    out += vertical
      ? `<text x="${tx}" y="${ty}" fill="${ink}" text-anchor="middle" transform="rotate(-90 ${tx} ${ty})">${esc(u.id)} · ${v}</text></g>`
      : `<text x="${tx}" y="${ty + 0.7}" fill="${ink}" text-anchor="middle">${esc(u.id)} · ${v}</text></g>`;
  }
  // Camera positions and the area each one watches (field-of-view wedge).
  const CAM_POS = { "cam-01": [14, 39, 8, 20, 31], "cam-02": [43, 56.5, 33, 53, 46], "cam-03": [72, 39, 66, 78, 31], "cam-04": [92.5, 39, 87, 98, 31] };
  for (const c of state.store.cameras) {
    const p = CAM_POS[c.id];
    if (!p) continue;
    const [cx, cy, l, r, top] = p;
    out += `<g class="cam-pin" data-cam="${c.id}"><title>${esc(c.id)} · ${esc(c.name)} (open live feed)</title>`
      + `<path class="fov" d="M${cx} ${cy} L${l} ${top} L${r} ${top} Z"/>`
      + `<circle cx="${cx}" cy="${cy}" r="1.7"/>`
      // Label on the left when the pin is near the right wall.
      + (cx > 85 ? `<text x="${cx - 2.4}" y="${cy + 0.7}" text-anchor="end">${esc(c.id)}</text></g>` : `<text x="${cx + 2.4}" y="${cy + 0.7}">${esc(c.id)}</text></g>`);
  }
  svg.innerHTML = out;
  $("#floorLegend").innerHTML = `<span>${METRIC[m]} low</span><span class="ramp" style="background:linear-gradient(90deg,${RAMP.join(",")})"></span><span>high</span>`;
}

async function showUnit(id) {
  state.selectedUnit = id;
  $$("#floor .unit").forEach((r) => r.classList.toggle("sel", r.dataset.unit === id));
  const el = $("#unitDetail");
  el.innerHTML = `<h2>${esc(id)}</h2><p class="muted"><span class="spinner"></span>Loading…</p>`;
  const d = await api(`/units/${id}?audience=${encodeURIComponent(state.audience)}`);
  const u = d.unit;
  const fitCls = u.audience_fit > 1.02 ? "fit-up" : u.audience_fit < 0.98 ? "fit-down" : "";
  el.innerHTML = `
    <div class="card-head"><h2>${esc(u.id)} · ${esc(u.category)}</h2><span class="tag">${POS[u.position] || u.position} · Aisle ${esc(u.aisle)}</span></div>
    <div class="kpis" style="grid-template-columns:repeat(3,1fr);margin-bottom:10px">
      <div class="kpi"><div class="label">SVI</div><div class="value">${u.svi}</div><div class="sub">aisle avg ${d.aisle_avg_svi}</div></div>
      <div class="kpi"><div class="label">Suggested rent</div><div class="value" style="font-size:19px">${pkr(u.price_pkr)}</div><div class="sub">per month</div></div>
      <div class="kpi"><div class="label">Audience fit</div><div class="value ${fitCls}">${u.audience_fit}×</div><div class="sub">${esc($("#audience").selectedOptions[0].text)}</div></div>
    </div>
    <table><tr><th>Input</th><th class="num">Raw</th><th class="num">Normalised</th><th class="num">Weight</th></tr>
      <tr><td>Footfall / hr</td><td class="num">${u.inputs.F.toFixed(1)}</td><td class="num">${u.normalised.F}</td><td class="num">0.40</td></tr>
      <tr><td>Stop rate</td><td class="num">${pct(u.inputs.S)}</td><td class="num">${u.normalised.S}</td><td class="num">0.25</td></tr>
      <tr><td>Reach rate</td><td class="num">${pct(u.inputs.R)}</td><td class="num">${u.normalised.R}</td><td class="num">0.20</td></tr>
      <tr><td>Median dwell</td><td class="num">${u.inputs.D.toFixed(1)} s</td><td class="num">${u.normalised.D}</td><td class="num">0.15</td></tr>
    </table>
    <h2 style="margin-top:14px">Hour × weekday</h2><div id="unitHeat" class="chart" style="height:220px"></div>
    <h2>Audience mix</h2><div id="unitAge" class="chart" style="height:90px"></div>
    <p class="fine">Peaks: ${d.peaks.map((p) => `${p.day} ${p.hour} (${p.unique_visitors})`).join(" · ")} · confidence ${u.confidence} · ${u.covered_hours} covered hours · sources: ${u.sources.join(", ")}</p>`;
  const hours = [...Array(24).keys()].slice(9, 23);
  Plotly.react("unitHeat", [{
    type: "heatmap", z: d.heatmap.map((r) => r.slice(9, 23)), x: hours.map((h) => `${h}:00`), y: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    colorscale: RAMP.map((c, i) => [i / (RAMP.length - 1), c]), showscale: false, hovertemplate: "%{y} %{x}<br>%{z} visitors<extra></extra>",
  }], plotLayout({ margin: { l: 36, r: 6, t: 4, b: 28 }, yaxis: { autorange: "reversed" } }), plotCfg);
  const ages = Object.keys(AGE);
  Plotly.react("unitAge", ages.map((a, i) => ({
    type: "bar", orientation: "h", name: AGE[a], x: [u.age_mix[a]], y: [""], marker: { color: RAMP[[1, 3, 5, 6][i]] },
    text: [`${AGE[a]} ${pct(u.age_mix[a])}`], textposition: "inside", insidetextanchor: "middle", hovertemplate: `${AGE[a]}: %{x:.0%}<extra></extra>`,
  })), plotLayout({ barmode: "stack", showlegend: false, margin: { l: 4, r: 4, t: 4, b: 4 }, xaxis: { visible: false, range: [0, 1] }, yaxis: { visible: false } }), plotCfg);
}

// ---------- pricing ----------
function renderPricing() {
  const rows = [...state.store.units];
  const { key, dir } = state.sort;
  const val = (r) => ({ svi: r.svi, price: r.price_pkr, F: r.inputs.F, S: r.inputs.S, R: r.inputs.R, D: r.inputs.D, fit: r.audience_fit, id: r.id }[key]);
  rows.sort((a, b) => (val(a) > val(b) ? 1 : -1) * dir);
  const aud = $("#audience").selectedOptions[0].text;
  $("#pricingNote").textContent = state.audience === "generic"
    ? "Generic view: every shopper counts the same. Pick a brand audience above to re-weight by who actually passes each shelf."
    : `Brand view for “${aud}”: SVI is multiplied by AudienceFit (on-target share vs store average, clipped 0.5–1.5×). ▲▼ show each shelf's move against the generic ranking; small figures under the rent show the change.`;
  const rank = Object.fromEntries(state.store.units.map((u, i) => [u.id, i + 1]));
  const base = Object.fromEntries((state.base || []).map((u, i) => [u.id, { rank: i + 1, price: u.price_pkr }]));
  const brand = state.audience !== "generic";
  const move = (id) => {
    if (!brand || !base[id]) return "";
    const d = base[id].rank - rank[id];
    return d > 0 ? `<span class="mv up" title="up ${d} vs generic">▲${d}</span>` : d < 0 ? `<span class="mv down" title="down ${-d} vs generic">▼${-d}</span>` : `<span class="mv">–</span>`;
  };
  const dprice = (r) => {
    if (!brand || !base[r.id]) return "";
    const d = r.price_pkr - base[r.id].price;
    return d ? `<div class="dp ${d > 0 ? "up" : "down"}">${d > 0 ? "+" : "−"}${fmt.format(Math.abs(d))}</div>` : "";
  };
  const head = [[null, "#", 1], ["id", "Shelf"], [null, "Category"], [null, "Position"], ["svi", "SVI", 1], ["F", "Footfall/hr", 1], ["S", "Stop", 1], ["R", "Reach", 1], ["D", "Dwell", 1], ["fit", "Fit", 1], ["price", "Rent / month", 1], [null, "Data"]];
  $("#rank").innerHTML = "<thead><tr>" + head.map(([k, l, n]) => `<th class="${n ? "num" : ""}" ${k ? `data-sort="${k}"` : ""}>${l}${key === k ? (dir < 0 ? " ↓" : " ↑") : ""}</th>`).join("") + "</tr></thead><tbody>" +
    rows.map((r) => `<tr data-unit="${r.id}">
      <td class="num rk">${rank[r.id]}${move(r.id)}</td><td><strong>${esc(r.id)}</strong></td><td>${esc(r.category)}</td><td>${POS[r.position] || r.position}</td>
      <td class="num"><span class="bar" style="width:${Math.max(2, r.svi * 0.6)}px;background:${rampColor(r.svi / 100)}"></span>${r.svi}</td>
      <td class="num">${r.inputs.F.toFixed(1)}</td><td class="num">${pct(r.inputs.S)}</td><td class="num">${pct(r.inputs.R)}</td><td class="num">${r.inputs.D.toFixed(1)} s</td>
      <td class="num ${r.audience_fit > 1.02 ? "fit-up" : r.audience_fit < 0.98 ? "fit-down" : ""}">${r.audience_fit}×</td>
      <td class="num"><strong>${pkr(r.price_pkr)}</strong>${dprice(r)}</td>
      <td>${r.sources.map((s) => `<span class="tag ${s === "gemini" ? "live" : ""}">${s === "gemini" ? "live" : "sim"}</span>`).join(" ")}</td></tr>`).join("") + "</tbody>";
}

function exportCsv() {
  const cols = ["id", "category", "position", "aisle", "svi", "price_pkr", "audience_fit", "F", "S", "R", "D", "unique_visitors", "confidence"];
  const lines = [cols.join(",")].concat(state.store.units.map((r) =>
    cols.map((c) => (["F", "S", "R", "D"].includes(c) ? r.inputs[c] : r[c])).map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  a.download = `shelfsense-pricing-${state.audience}.csv`;
  a.click();
}

// ---------- live analysis ----------
function renderCams() {
  const cams = state.store.cameras;
  $("#cams").innerHTML = cams.map((c) => `<button class="cam" data-cam="${c.id}"><img src="clips/${c.sample.replace(".mp4", ".jpg")}" alt="" loading="lazy"><div>${esc(c.id)} · ${esc(c.name)}</div></button>`).join("");
  selectCam(cams[0].id);
}

function selectCam(id) {
  state.camera = state.store.cameras.find((c) => c.id === id);
  $$(".cam").forEach((b) => b.classList.toggle("active", b.dataset.cam === id));
  $("#camTitle").textContent = `${state.camera.id} · ${state.camera.name}`;
  const p = $("#player");
  p.src = `clips/${state.camera.sample}`;
  p.play().catch(() => {});
  drawZones(null);
}

// Where each zone sits in the frame, as % of the picture: [left, top, width, height].
// Zone ids end in -L / -R / -E (aisle cameras) or -FRONT / -MID / -BACK (hall camera).
const ZONE_BOX = { L: [1, 10, 33, 86], R: [66, 10, 33, 86], E: [36, 16, 28, 38], FRONT: [1, 66, 98, 32], MID: [1, 37, 98, 28], BACK: [1, 8, 98, 28] };

function drawZones(results) {
  const ov = $("#zoneOv");
  const byId = Object.fromEntries((results || []).map((z) => [z.zone_id, z]));
  ov.innerHTML = Object.keys(state.camera.zones).map((id) => {
    const b = ZONE_BOX[id.split("-").pop()];
    if (!b) return "";
    const z = byId[id];
    const stats = z ? `<b>${z.unique_visitors}</b> visitors · <b>${z.reaches}</b> reaches` : "";
    return `<div class="zbox${z ? " has" : ""}" data-zone="${id}" style="left:${b[0]}%;top:${b[1]}%;width:${b[2]}%;height:${b[3]}%">
      <span class="zlabel">${esc(id)}${stats ? `<small>${stats}</small>` : ""}</span></div>`;
  }).join("");
  ov.hidden = !$("#showZones").checked;
  positionZones();
}

// Fit the overlay to the visible picture (the video is letterboxed with object-fit: contain).
function positionZones() {
  const v = $("#player"), ov = $("#zoneOv");
  if (!v.videoWidth) return;
  const W = v.clientWidth, H = v.clientHeight, r = v.videoWidth / v.videoHeight;
  const w = Math.min(W, H * r), h = w / r;
  Object.assign(ov.style, { left: `${(W - w) / 2}px`, top: `${(H - h) / 2}px`, width: `${w}px`, height: `${h}px` });
}

function flashZone(id) {
  const el = $(`#zoneOv [data-zone="${id}"]`);
  if (!el) return;
  el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
}

function setStatus(text, cls = "") {
  const s = $("#camStatus");
  s.textContent = text; s.className = "pill " + cls;
}

async function runAnalysis(file) {
  const fd = new FormData();
  fd.append("camera_id", state.camera.id);
  if (file) {
    if (file.size > 30 * 1024 * 1024) { alert("Please use a clip under 30 MB."); return; }
    fd.append("video", file);
    $("#player").src = URL.createObjectURL(file);
  }
  const btn = $("#runSample");
  btn.disabled = true;
  const t0 = performance.now();
  setStatus("Gemini is watching…", "busy");
  const timer = setInterval(() => setStatus(`Gemini is watching… ${((performance.now() - t0) / 1000).toFixed(0)} s`, "busy"), 500);
  $("#analysis").innerHTML = `<h2>Gemini analysis</h2>
    <ol class="steps" id="steps">
      <li class="active"><span></span>Sending ${file ? "your clip" : "the clip"} to the API on Cloud Run</li>
      <li><span></span>Gemini 3 Flash is watching and counting shoppers per shelf zone</li>
      <li><span></span>Saving anonymous counts to Firestore</li>
    </ol>
    <p class="fine">Typically 4–8 seconds.</p>`;
  const steps = $$("#steps li");
  const stepTo = (n) => steps.forEach((li, i) => { li.className = i < n ? "done" : i === n ? "active" : ""; });
  setTimeout(() => stepTo(1), 700);
  try {
    const r = await api("/analyze", { method: "POST", body: fd });
    stepTo(2);
    await new Promise((ok) => setTimeout(ok, 350));
    renderAnalysis(r);
    setStatus(`done in ${((performance.now() - t0) / 1000).toFixed(1)} s`);
    loadHistory();
    loadStore();
  } catch (e) {
    setStatus("error", "err");
    $("#analysis").innerHTML = `<h2>Gemini analysis</h2><p>Analysis failed: ${esc(e.message)}</p>`;
  } finally { clearInterval(timer); btn.disabled = false; }
}

function renderAnalysis(r) {
  const a = r.analysis, m = r.meta;
  if (r.camera_id === state.camera.id) drawZones(a.zones);
  $("#analysis").innerHTML = `
    <div class="card-head"><h2>Gemini analysis · ${esc(r.camera_id)}</h2><span class="tag live">written to Firestore</span></div>
    <p class="small">${esc(a.scene)} <strong>${a.people_total}</strong> people in view.</p>
    <div class="zones">${a.zones.map((z) => `
      <div class="zone"><h3>${esc(z.zone_id)}</h3>
        <dl><dt>Visitors</dt><dd>${z.unique_visitors}</dd><dt>Stops</dt><dd>${z.stops}</dd><dt>Reaches</dt><dd>${z.reaches}</dd>
        <dt>Dwell p50</dt><dd>${z.dwell_p50_s}s</dd><dt>18–35</dt><dd>${z.age_bands.age_18_35}</dd></dl>
        <p>${esc(z.notes)}</p></div>`).join("")}</div>
    <h2>Event log <span class="fine">click to jump</span></h2>
    <div class="events">${a.events.map((e) => `<button data-t="${e.t_s}" data-zone="${esc(e.zone_id)}"><span class="t">${e.t_s.toFixed(1)}s</span><span><strong>${esc(e.zone_id)}</strong> · ${esc(e.kind)} — ${esc(e.description)}</span></button>`).join("") || '<p class="muted">No events.</p>'}</div>
    <div class="meta"><span class="tag">${esc(m.model)}</span><span class="tag">${m.latency_s}s model latency</span>
      ${m.input_tokens ? `<span class="tag">${fmt.format(m.input_tokens)} in / ${fmt.format(m.output_tokens)} out tokens</span>` : ""}
      <span class="tag">quality: ${esc(a.data_quality)}</span></div>`;
}

async function loadHistory() {
  try {
    const rows = await api("/analyses?limit=8");
    $("#history").classList.remove("muted");
    $("#history").innerHTML = rows.length ? rows.map((r) => `<div class="row"><span class="tag">${new Date(r.created_at).toLocaleString()}</span><strong>${esc(r.camera_id)}</strong>
      <span>${r.analysis.people_total} people · ${r.analysis.zones.map((z) => `${esc(z.zone_id)}: ${z.unique_visitors} visitors / ${z.reaches} reaches`).join(" · ")}</span>
      <span class="fine" style="margin:0">${esc(r.meta.model)} · ${r.meta.latency_s}s · ${esc(r.source)}</span></div>`).join("") : "No analyses yet — run one above.";
    $$("#history .row").forEach((el, i) => el.addEventListener("click", () => { if (rows[i].camera_id !== state.camera.id) selectCam(rows[i].camera_id); renderAnalysis(rows[i]); }));
  } catch (e) { $("#history").textContent = e.message; }
}

// ---------- ask ----------
const SUGGESTED = [
  "Which shelf reaches the most 18–35 shoppers on weekend evenings?",
  "Which shelves are under-priced for the attention they get?",
  "When should I staff the produce hall?",
  "Where should a new energy drink brand rent space, and what would it cost?",
];

function addMsg(role, html, meta = "") {
  $("#chatEmpty")?.remove();
  const el = document.createElement("div");
  el.className = "msg " + (role === "user" ? "user" : "bot");
  el.innerHTML = html + (meta ? `<div class="fine">${esc(meta)}</div>` : "");
  $("#log").appendChild(el);
  $("#log").scrollTop = $("#log").scrollHeight;
  return el;
}

async function ask(q) {
  q = q.trim();
  if (!q) return;
  $("#q").value = "";
  addMsg("user", esc(q));
  const pending = addMsg("bot", '<span class="spinner"></span>Thinking with Gemini…');
  pending.classList.add("typing");
  try {
    const r = await api("/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q, history: state.chat }) });
    pending.classList.remove("typing");
    pending.innerHTML = md(r.answer) + `<div class="fine">${esc(r.meta.model)} · ${r.meta.latency_s}s · grounded on Firestore shelf data</div>`;
    state.chat.push({ role: "user", text: q }, { role: "model", text: r.answer });
  } catch (e) {
    pending.textContent = "Sorry, that failed: " + e.message;
  }
}

// ---------- wiring ----------
function wire() {
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => {
    $$(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    $$(".tab").forEach((t) => t.classList.toggle("active", t.id === "tab-" + b.dataset.tab));
    history.replaceState(null, "", "#" + b.dataset.tab);
    window.dispatchEvent(new Event("resize"));
  }));
  $("#audience").addEventListener("change", (e) => { state.audience = e.target.value; loadStore(); });
  $("#floorMetric").addEventListener("change", renderFloor);
  $("#floor").addEventListener("click", (e) => {
    const pin = e.target.closest(".cam-pin");
    if (pin) { $('[data-tab="live"]').click(); selectCam(pin.dataset.cam); return; }
    const id = e.target.dataset?.unit; if (id) showUnit(id);
  });
  $("#showZones").addEventListener("change", (e) => { $("#zoneOv").hidden = !e.target.checked; });
  $("#player").addEventListener("loadedmetadata", positionZones);
  window.addEventListener("resize", positionZones);
  $("#rank").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-sort]");
    if (th) {
      const k = th.dataset.sort;
      state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : -1 };
      renderPricing();
      return;
    }
    const tr = e.target.closest("tr[data-unit]");
    if (tr) { $('[data-tab="floor"]').click(); showUnit(tr.dataset.unit); }
  });
  document.body.addEventListener("click", (e) => {
    const c = e.target.closest(".cite");
    if (c) { $('[data-tab="floor"]').click(); showUnit(c.dataset.unit); }
  });
  $("#refreshSummary").addEventListener("click", () => refreshSummary());
  $("#csv").addEventListener("click", exportCsv);
  $("#cams").addEventListener("click", (e) => { const b = e.target.closest(".cam"); if (b) selectCam(b.dataset.cam); });
  $("#runSample").addEventListener("click", () => runAnalysis(null));
  $("#upload").addEventListener("change", (e) => { if (e.target.files[0]) runAnalysis(e.target.files[0]); e.target.value = ""; });
  $("#analysis").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-t]");
    if (b) { const p = $("#player"); p.currentTime = +b.dataset.t; p.play().catch(() => {}); flashZone(b.dataset.zone); }
  });
  $("#suggest").innerHTML = SUGGESTED.map((s) => `<button class="ghost">${esc(s)}</button>`).join("");
  $("#suggest").addEventListener("click", (e) => { if (e.target.tagName === "BUTTON") ask(e.target.textContent); });
  $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); ask($("#q").value); });
  const hash = location.hash.slice(1);
  if (hash) $(`[data-tab="${hash}"]`)?.click();
}

async function loadHealth() {
  try {
    const h = await api("/health");
    const el = $("#live");
    el.querySelector("span").textContent = "Live · " + h.model.replace(/^gemini-/, "Gemini ").replace(/-preview$/, "").replace(/-/g, " ").replace(/\bflash\b/, "Flash");
    el.title = `API on Cloud Run is up · model ${h.model}`;
    el.hidden = false;
  } catch {}
}

window.addEventListener("DOMContentLoaded", async () => {
  wire();
  loadHealth();
  try {
    await loadStore();
    loadHistory();
  } catch (e) {
    $("#storeName").textContent = "Could not reach the ShelfSense API: " + e.message;
  }
});
