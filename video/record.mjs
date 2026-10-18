// Records the ShelfSense demo walkthrough against the live site, paced to the narration.
// Usage: node record.mjs <video-dir>   (run with playwright resolvable)
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const DIR = path.resolve(process.argv[2]);
const SITE = "https://shelfsense-demo.web.app/";
const W = 1600, H = 900, GAP = 0.6;
const segs = Object.fromEntries(JSON.parse(fs.readFileSync(path.join(DIR, "narration.json"))).map((s) => [s.id, s]));

const browser = await browser_();
async function browser_() { return chromium.launch({ channel: "chrome" }); }
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: path.join(DIR, "raw"), size: { width: W, height: H } },
});
const T0 = Date.now();
// Visible cursor, since headless recordings do not draw one.
await ctx.addInitScript(() => {
  window.addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    c.style.cssText = "position:fixed;z-index:99999;width:22px;height:22px;border-radius:50%;background:rgba(15,118,110,.35);border:2px solid #0f766e;pointer-events:none;transform:translate(-50%,-50%);left:-40px;top:-40px;transition:width .1s,height .1s";
    document.body.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.left = e.clientX + "px"; c.style.top = e.clientY + "px"; });
    addEventListener("mousedown", () => { c.style.width = c.style.height = "14px"; });
    addEventListener("mouseup", () => { c.style.width = c.style.height = "22px"; });
  });
});
const p = await ctx.newPage();
const log = [];
const sleep = (ms) => p.waitForTimeout(ms);
const now = () => (Date.now() - T0) / 1000;

async function moveTo(sel, opts = {}) {
  const el = typeof sel === "string" ? p.locator(sel).first() : sel;
  await el.scrollIntoViewIfNeeded();
  const b = await el.boundingBox();
  await p.mouse.move(b.x + b.width / 2 + (opts.dx || 0), b.y + b.height / 2 + (opts.dy || 0), { steps: 25 });
  return el;
}
async function click(sel, opts) { await moveTo(sel, opts); await sleep(250); await p.mouse.down(); await sleep(80); await p.mouse.up(); }
async function scrollTo(y) { await p.evaluate((y) => window.scrollTo({ top: y, behavior: "smooth" }), y); }

// Run one narrated segment: start audio at the current time, run actions, hold until audio ends.
async function seg(id, actions = async () => {}) {
  const start = now();
  log.push({ id, start: +start.toFixed(2) });
  await actions();
  const remaining = segs[id].dur + GAP - (now() - start);
  if (remaining > 0) await sleep(remaining * 1000);
}

// Title
await p.goto("file://" + path.join(DIR, "title.html"));
await sleep(1500);
await seg("s00_title");

// Overview, with data warm.
await p.goto(SITE);
await p.waitForSelector("#summary li", { timeout: 60000 });
await sleep(800);
await seg("s01_problem", async () => {
  await sleep(4000); await moveTo(".kpi:nth-child(1)"); await sleep(5000); await moveTo("#topChart", { dy: -60 });
});
await seg("s02_overview", async () => {
  await moveTo(".kpi:nth-child(2)"); await sleep(2500); await moveTo(".kpi:nth-child(3)"); await sleep(3000);
  await moveTo("#summary li:nth-child(1)"); await sleep(2500); await moveTo("#summary li:nth-child(2)"); await sleep(2500);
  await moveTo("#summary li:nth-child(3)"); await sleep(2500);
  await scrollTo(600); await sleep(1500); await moveTo("#storeHeat", { dx: 380, dy: 40 });
});

// Live analysis
await scrollTo(0);
await seg("s03_live", async () => {
  await click('[data-tab="live"]'); await sleep(1500);
  await click('.cam[data-cam="cam-02"]'); await sleep(4000);
  await moveTo("#runSample"); await sleep(2500);
  await click("#runSample");
});
await p.waitForSelector("#analysis .zones", { timeout: 90000 });
await seg("s04_results", async () => {
  await moveTo("#analysis .zone:nth-child(1)"); await sleep(3000);
  await moveTo("#analysis .zone:nth-child(2)"); await sleep(2500);
  await moveTo("#analysis .zone:nth-child(3)"); await sleep(2500);
  await click("#analysis .events button:nth-child(4)"); await sleep(3500);
  await click("#analysis .events button:nth-child(2)"); await sleep(2500);
  await moveTo("#analysis .meta");
});

// Floor map + SVI
await scrollTo(0);
await seg("s05_floor", async () => {
  await click('[data-tab="floor"]'); await sleep(2500);
  await moveTo('#floor .unit[data-unit="P-FRONT"]'); await sleep(2000);
  await click('#floor .unit[data-unit="A1-E"]'); await sleep(3000);
  await moveTo("#unitDetail table tr:nth-child(2)"); await sleep(1800);
  await moveTo("#unitDetail table tr:nth-child(3)"); await sleep(1500);
  await moveTo("#unitDetail table tr:nth-child(4)"); await sleep(1500);
  await moveTo("#unitDetail table tr:nth-child(5)"); await sleep(1500);
  await moveTo("#unitHeat", { dx: 100 });
});

// Pricing + audience
await scrollTo(0);
await seg("s06_pricing", async () => {
  await click('[data-tab="pricing"]'); await sleep(2000);
  await moveTo("#rank tbody tr:nth-child(1) td:nth-child(10)"); await sleep(5500);
  await moveTo("#audience"); await sleep(800);
  await p.selectOption("#audience", "18-35"); await sleep(2500);
  await moveTo('#rank tr[data-unit="A28-L"] td:nth-child(9)'); await sleep(3000);
  await moveTo('#rank tr[data-unit="A28-L"] td:nth-child(4)');
});

// Ask
await p.selectOption("#audience", "generic");
await seg("s07_ask", async () => {
  await click('[data-tab="ask"]'); await sleep(1200);
  await click("#q");
  await p.keyboard.type("Where should a new energy drink brand rent space, and what would it cost?", { delay: 35 });
  await sleep(300);
  await click("#askForm button");
});
await p.waitForFunction(() => !document.querySelector(".msg.typing"), null, { timeout: 60000 });
await seg("s08_answer", async () => {
  await moveTo(".msg.bot .cite"); await sleep(4000); await moveTo(".msg.bot", { dx: 200 });
});

// Architecture
await p.goto("file://" + path.join(DIR, "..", "docs", "architecture.html"));
await sleep(600);
await seg("s09_arch");

// Close
await p.goto("file://" + path.join(DIR, "title.html"));
await p.evaluate(() => { document.getElementById("tag").textContent = "Price shelf space by attention, not guesswork."; });
await sleep(400);
await seg("s10_close");
await sleep(1200);

const videoPath = await p.video().path();
await ctx.close(); await browser.close();
fs.writeFileSync(path.join(DIR, "timeline.json"), JSON.stringify({ video: videoPath, end: now(), segments: log }, null, 1));
console.log(JSON.stringify({ video: videoPath, end: now().toFixed(1), segments: log.length }));
