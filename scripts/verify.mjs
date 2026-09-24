// UI checks for WowGear Classic (manual mode, lookup mode, slider, tiers, mobile).
//
// Usage:  cd scripts && npm i && node verify.mjs [base-url] [realm] [character]
// Needs the app running (default http://localhost:8000). The lookup check is
// skipped when no character is given.
import { chromium } from "playwright";
import { existsSync, mkdirSync } from "node:fs";

const BASE = process.argv[2] ?? "http://localhost:8000";
const REALM = process.argv[3];
const CHAR = process.argv[4];
const OUT = process.env.SHOTS ?? "shots";
if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });

const launch = existsSync("/opt/pw-browsers/chromium") ? { executablePath: "/opt/pw-browsers/chromium" } : {};
const browser = await chromium.launch(launch).catch(() => chromium.launch());
const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => { if (m.type() === "error" && !m.text().includes("zamimg") && !m.text().includes("ERR_CERT")) errors.push(`console: ${m.text()}`); });

const checks = [];
const chk = (name, ok, extra = "") => checks.push(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? ` (${extra})` : ""}`);

// ---- manual mode: Night Elf feral druid, level 24
await page.goto(`${BASE}/`);
await page.click("#tab-manual");
await page.selectOption("#m-race", "4");
await page.selectOption("#m-class", "11");
await page.selectOption("#m-spec", "feral_cat");
await page.fill("#m-level", "24");
await page.click("#panel-manual button[type=submit]");
await page.waitForSelector("#slot-list li", { timeout: 15000 });
chk("manual: gear list shows slots", (await page.locator("#slot-list li").count()) >= 14);
chk("manual: level output = 24", (await page.textContent("#level-out")) === "24");
chk("manual: todo list filled", (await page.locator("#todo-list > li").count()) >= 1);
await page.screenshot({ path: `${OUT}/manual-druid-24.png`, fullPage: true });

// tick the first item -> slot shows "You have it"
await page.locator("#slot-list li .own input").first().check();
chk("manual: tick marks item as owned", (await page.locator("#slot-list li.st-bis").count()) >= 1);

// slider to 60, tier buttons appear, tier 4 changes the list
await page.locator("#level-slider").fill("60");
chk("slider 60 shows tier row", await page.isVisible("#tier-row"));
const preRaid = await page.textContent("#slot-list");
await page.click('#tier-buttons button[data-tier="4"]');
const naxx = await page.textContent("#slot-list");
chk("tier 4 changes the list", preRaid !== naxx);
chk("URL keeps state", page.url().includes("class=11") && page.url().includes("tier=4"));
await page.screenshot({ path: `${OUT}/manual-druid-60-naxx.png`, fullPage: true });

// reload restores from URL
await page.reload();
await page.waitForSelector("#slot-list li", { timeout: 15000 });
chk("reload restores level 60", (await page.textContent("#level-out")) === "60");

// Tauren shaman enhancement at 30 (Horde-only class)
await page.goto(`${BASE}/?race=6&class=7&spec=enhancement&lvl=30&level=30`);
await page.waitForSelector("#slot-list li", { timeout: 15000 });
chk("shaman 30 loads from URL", (await page.textContent("#gear-sub")).includes("Enhancement Shaman"));
await page.screenshot({ path: `${OUT}/manual-shaman-30.png`, fullPage: true });

// ---- lookup mode
if (REALM && CHAR) {
  await page.goto(`${BASE}/`);
  await page.click("#tab-lookup");
  await page.selectOption("#region", REALM.split("/")[0]);
  await page.waitForFunction(() => !document.getElementById("realm-trigger").disabled, null, { timeout: 20000 });
  await page.click("#realm-trigger");
  await page.fill("#realm-search", REALM.split("/")[1]);
  await page.keyboard.press("Enter");
  await page.fill("#character", CHAR);
  await page.click("#lookup-btn");
  await page.waitForSelector("#char-bar .char-name", { timeout: 30000 });
  chk("lookup: character bar", (await page.textContent("#char-bar")).includes("Level"));
  chk("lookup: equipped items shown", (await page.locator(".equipped .item-link").count()) >= 10);
  await page.screenshot({ path: `${OUT}/lookup.png`, fullPage: true });
}

// ---- mobile layout: no horizontal scroll
await page.setViewportSize({ width: 390, height: 860 });
await page.goto(`${BASE}/?race=4&class=11&spec=feral_cat&lvl=24&level=24`);
await page.waitForSelector("#slot-list li", { timeout: 15000 });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
chk("mobile: no horizontal scroll", overflow <= 1, `overflow ${overflow}px`);
await page.screenshot({ path: `${OUT}/mobile.png`, fullPage: false });

chk("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
console.log(checks.join("\n"));
await browser.close();
process.exit(checks.some((c) => c.startsWith("FAIL")) ? 1 : 0);
