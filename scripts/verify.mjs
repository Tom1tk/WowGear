// UI verification for WowGearBis: paperdoll geometry (retail in-game layout),
// portrait fill ratio, skeleton loading state, top loading bar.
//
// Usage:  cd scripts && npm i && node verify.mjs [base-url]
// Requires the app running locally (default http://localhost:8000).
import { chromium } from "playwright";

const BASE = process.argv[2] ?? "http://localhost:8000";
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => {
  if (m.type() === "error") errors.push(`console: ${m.text()}`);
});

const checks = [];
const chk = (name, ok, extra = "") =>
  checks.push(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? ` (${extra})` : ""}`);

// Delay the analyze request so skeleton/loading-bar states are observable.
await page.route("**/api/analyze", async (route) => {
  await new Promise((r) => setTimeout(r, 4000));
  await route.continue();
});

await page.goto(BASE);
await page.waitForSelector('#realm option[value="draenor"]', { state: "attached", timeout: 30000 });
chk("realm dropdown populated", await page.locator("#realm option").count() > 50);

// realm choice persists via localStorage across reloads
await page.selectOption("#realm", "silvermoon");
await page.reload();
await page.waitForSelector('#realm option[value="silvermoon"]', { state: "attached", timeout: 30000 });
chk("stored realm restored after reload",
  await page.evaluate(() => document.getElementById("realm").value) === "silvermoon");
await page.selectOption("#realm", "draenor");
await page.fill("#character", "Greyball");
await page.click("#analyze-btn");

// --- while the request is in flight ---
await page.waitForSelector("#skeletons:not([hidden])", { timeout: 10000 });
chk("skeletons visible during fetch", true);
chk("skeleton display:grid while loading",
  await page.evaluate(() => getComputedStyle(document.getElementById("skeletons")).display) === "grid");
chk("real layout hidden during fetch",
  await page.evaluate(() => getComputedStyle(document.getElementById("results-layout")).display === "none"));
chk("top bar active during fetch",
  await page.evaluate(() => document.getElementById("top-bar").classList.contains("active")));
chk("top bar width advanced",
  (await page.evaluate(() => getComputedStyle(document.getElementById("top-bar")).width)) !== "0px");

await page.waitForSelector("#results:not([hidden]) #character-card h2", { timeout: 120000 });
await page.waitForLoadState("networkidle");

// --- after load ---
chk("skeletons gone after fetch (display:none)",
  await page.evaluate(() => getComputedStyle(document.getElementById("skeletons")).display === "none"));
chk("real layout visible after fetch",
  await page.evaluate(() => getComputedStyle(document.getElementById("results-layout")).display === "grid"));
chk("top bar inactive after fetch",
  await page.evaluate(() => !document.getElementById("top-bar").classList.contains("active")));

const box = async (sel) => page.locator(sel).boundingBox();
const eq = async (slot) => box(`.pd-col [data-slot="${slot}"]`);

const portrait = await box(".pd-portrait img");
const head = await eq("head");
const wrist = await eq("wrist");
const hands = await eq("hands");
const trinket2 = await eq("trinket_2");
const mainHand = await eq("main_hand");
const offHand = await eq("off_hand");

chk("weapons below portrait", mainHand.y > portrait.y + portrait.height);
chk("head top-left of portrait", head.x < portrait.x);
chk("hands top-right of portrait", hands.x > portrait.x + portrait.width);
chk("right column: hands above trinket_2", hands.y < trinket2.y);
chk("weapons on same row", Math.abs(mainHand.y - offHand.y) < 4);
chk("weapons centered under portrait",
  Math.abs((mainHand.x + offHand.x + offHand.width) / 2 - (portrait.x + portrait.width / 2)) < 90);

const leftSlots = ["head", "neck", "shoulders", "back", "chest", "wrist"];
const rightSlots = ["hands", "waist", "legs", "feet", "ring_1", "ring_2", "trinket_1", "trinket_2"];
const ordered = async (slots) => {
  const boxes = {};
  for (const s of slots) boxes[s] = await eq(s);
  return slots.every((s, i) => i === 0 || boxes[slots[i]].y > boxes[slots[i - 1]].y);
};
chk("left column top→bottom order", await ordered(leftSlots));
chk("right column top→bottom order", await ordered(rightSlots));

// --- portrait fit (Blizzard main-raw is a 4:3 canvas with the character
// centered in ~33-67% x, 17-81% y; object-fit cover must fill the frame) ---
const fit = await page.evaluate(() => {
  const img = document.querySelector(".pd-portrait img");
  const r = img.getBoundingClientRect();
  const scale = Math.max(r.width / img.naturalWidth, r.height / img.naturalHeight);
  const drawnW = img.naturalWidth * scale;
  const drawnH = img.naturalHeight * scale;
  // Character footprint inside the canvas (from Blizzard's render bbox).
  const charW = drawnW * 0.34;
  const charH = drawnH * 0.64;
  return {
    frameW: r.width, frameH: r.height,
    drawnW, drawnH,
    charW, charH,
    fillsFrame: drawnW >= r.width - 1 && drawnH >= r.height - 1,
    charCoversFrame: charH >= r.height * 0.5 && charW >= r.width * 0.4,
    nat: [img.naturalWidth, img.naturalHeight],
  };
});
chk("portrait fills frame (cover)", fit.fillsFrame,
  `drawn ${Math.round(fit.drawnW)}x${Math.round(fit.drawnH)} in ${Math.round(fit.frameW)}x${Math.round(fit.frameH)}`);
chk("character occupies most of frame", fit.charCoversFrame,
  `char ≈${Math.round(fit.charW)}x${Math.round(fit.charH)}`);

// --- no JS errors, sane table ---
chk("no JS console errors", errors.length === 0);
chk("comparison table has 16 rows",
  (await page.locator("#comparison-table tbody tr").count()) === 16);

console.log(checks.join("\n"));
await page.screenshot({ path: "/tmp/wowgear_verify.png", fullPage: true });
console.log("\nScreenshot: /tmp/wowgear_verify.png");
await browser.close();
process.exit(checks.some((c) => c.startsWith("FAIL")) ? 1 : 0);
