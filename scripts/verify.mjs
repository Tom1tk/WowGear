// UI checks for WowGear Forever (manual mode, name+surname lookup, slider, tiers,
// Uncertain badges, mobile).
//
// Usage:  cd scripts && npm i && node verify.mjs [base-url] [region/name/surname]
// Needs the app running (default http://localhost:8000). The lookup check runs
// against the real API only when a character is given; a stubbed /api/character
// (invented character) and mocked "uncertain" gear data are always checked.
import { chromium } from "playwright";
import { existsSync, mkdirSync } from "node:fs";

const BASE = process.argv[2] ?? "http://localhost:8000";
const CHAR = process.argv[3]; // e.g. eu/Name/Surname
const OUT = process.env.SHOTS ?? "shots";
if (!existsSync(OUT)) mkdirSync(OUT, { recursive: true });

const pwExe = process.env.PW_CHROMIUM ?? "/opt/pw-browsers/chromium";
const launch = existsSync(pwExe) ? { executablePath: pwExe } : {};
const browser = await chromium.launch(launch).catch(() => chromium.launch());
const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
// Ignored: CDN/cert noise, Wowhead "entity not found" (stale ids in old-shape data), and the stubbed 404 lookup below.
page.on("console", (m) => { if (m.type() === "error" && !/zamimg|ERR_CERT|Wowhead tooltip|status of 404/.test(m.text())) errors.push(`console: ${m.text()}`); });
page.on("response", (r) => { if (r.status() === 404 && !r.url().includes("/api/character")) console.log(`note: 404 ${r.url()}`); });

const checks = [];
const chk = (name, ok, extra = "") => checks.push(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? ` (${extra})` : ""}`);

// ---- manual mode: Night Elf feral druid, level 24
await page.goto(`${BASE}/`);
await page.click("#tab-manual");
const raceOpts = await page.locator("#m-race option").allTextContents();
chk("manual: races listed from meta", raceOpts.length >= 8, raceOpts.join(", "));
await page.selectOption("#m-race", { label: raceOpts.find((r) => r.startsWith("Night Elf")) });
await page.selectOption("#m-class", "11");
await page.selectOption("#m-spec", "feral_cat");
await page.fill("#m-level", "24");
await page.click("#panel-manual button[type=submit]");
await page.waitForSelector("#slot-list li", { timeout: 15000 });
chk("manual: gear list shows slots", (await page.locator("#slot-list li").count()) >= 14);
chk("manual: level output = 24", (await page.textContent("#level-out")) === "24");
chk("manual: todo list filled", (await page.locator("#todo-list > li").count()) >= 1);
chk("manual: item links go to wowhead forever", ((await page.getAttribute("#slot-list .item-link", "href")) ?? "").includes("/forever/item="));
chk("manual: warcraftdb link", (await page.locator('#slot-list a.ext[href*="forever.warcraftdb.com/data/item/"]').count()) >= 1);
await page.screenshot({ path: `${OUT}/manual-druid-24.png`, fullPage: true });

// Skyborne (only once the data has it): class list comes from the race
const sky = raceOpts.find((r) => r.startsWith("Skyborne"));
if (sky) {
  await page.selectOption("#m-race", { label: sky });
  chk("manual: skyborne class list not empty", (await page.locator("#m-class option").count()) >= 1);
  await page.selectOption("#m-race", { label: raceOpts.find((r) => r.startsWith("Night Elf")) });
}

// tick the first item -> slot shows "You have it"
await page.locator("#slot-list li .own input").first().check();
chk("manual: tick marks item as owned", (await page.locator("#slot-list li.st-bis").count()) >= 1);

// slider to 60, tier buttons come from meta.tiers
await page.locator("#level-slider").fill("60");
chk("slider 60 shows tier row", await page.isVisible("#tier-row"));
const tierBtns = await page.locator("#tier-buttons button").count();
const metaTiers = Object.keys((await (await page.request.get(`${BASE}/static/data/meta.json`)).json()).tiers).filter((t) => t !== "0").length;
chk("tier buttons = Pre-raid + meta.tiers", tierBtns === metaTiers + 1, `${tierBtns} buttons, ${metaTiers} meta tiers`);
const preRaid = await page.textContent("#slot-list");
await page.click('#tier-buttons button[data-tier="1"]');
chk("tier 1 changes the list", preRaid !== (await page.textContent("#slot-list")));
chk("URL keeps state", page.url().includes("class=11") && page.url().includes("tier=1"));
await page.screenshot({ path: `${OUT}/manual-druid-60-tier1.png`, fullPage: true });

// reload restores from URL
await page.reload();
await page.waitForSelector("#slot-list li", { timeout: 15000 });
chk("reload restores level 60", (await page.textContent("#level-out")) === "60");

// Tauren shaman enhancement at 30 (Horde-only class)
await page.goto(`${BASE}/?race=6&class=7&spec=enhancement&lvl=30&level=30`);
await page.waitForSelector("#slot-list li", { timeout: 15000 });
chk("shaman 30 loads from URL", (await page.textContent("#gear-sub")).includes("Enhancement Shaman"));

// ---- lookup mode, stubbed API (invented character)
const stub = (character) => ({
  character: { name: "Testa", surname: "Examplar", region: "eu", ruleset: "Normal", level: 24, class_id: 11, class_name: "Druid", race_id: 4, race: "Night Elf", faction: "A", avatar_url: null, guild: null },
  equipped: {}, spec: "feral_cat", spec_reason: "stub", ...character,
});
let lastUrl = "";
await page.route("**/api/character*", (route) => {
  lastUrl = route.request().url();
  const u = new URL(lastUrl);
  if (u.searchParams.get("name") === "Missing") return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Character not found. Forever characters show up from level 10, after logging out." }) });
  return route.fulfill({ contentType: "application/json", body: JSON.stringify(stub()) });
});
await page.goto(`${BASE}/`);
await page.click("#tab-lookup");
chk("lookup: no realm field", (await page.locator("#realm-trigger, #realm").count()) === 0);
await page.fill("#character", "Bad1");
await page.fill("#surname", "Examplar");
await page.click("#lookup-btn");
chk("lookup: digits rejected before sending", (await page.textContent("#status")).includes("letters only") && lastUrl === "");
await page.fill("#character", "Missing");
await page.click("#lookup-btn");
await page.waitForFunction(() => document.getElementById("status").textContent.includes("level 10"));
chk("lookup: 404 shows server message", true);
await page.fill("#character", "Testa");
await page.selectOption("#region", "eu");
await page.click("#lookup-btn");
await page.waitForSelector("#char-bar .char-name", { timeout: 15000 });
const bar = await page.textContent("#char-bar");
chk("lookup: name surname shown", bar.includes("Testa Examplar"));
chk("lookup: ruleset and region shown", bar.includes("Normal · EU"), bar.replace(/\s+/g, " ").slice(0, 120));
chk("lookup: request has name+surname+region", lastUrl.includes("name=Testa") && lastUrl.includes("surname=Examplar") && lastUrl.includes("region=eu"));
chk("lookup: URL shareable", page.url().includes("surname=Examplar") && page.url().includes("region=eu"));
await page.screenshot({ path: `${OUT}/lookup-stub.png`, fullPage: true });
await page.goto(page.url());
await page.waitForSelector("#char-bar .char-name", { timeout: 15000 });
chk("lookup: reload from URL params", (await page.textContent("#char-bar")).includes("Testa Examplar"));
await page.unroute("**/api/character*");

// ---- real lookup (optional)
if (CHAR) {
  const [region, name, surname] = CHAR.split("/");
  await page.goto(`${BASE}/`);
  await page.click("#tab-lookup");
  await page.selectOption("#region", region);
  await page.fill("#character", name);
  await page.fill("#surname", surname);
  await page.click("#lookup-btn");
  await page.waitForSelector("#char-bar .char-name", { timeout: 30000 });
  chk("lookup: character bar", (await page.textContent("#char-bar")).includes("Level"));
  await page.screenshot({ path: `${OUT}/lookup.png`, fullPage: true });
}

// ---- Uncertain UI with mocked gear data (patched in the browser only)
const ctx2 = await browser.newContext({ viewport: { width: 1360, height: 1000 } });
const page2 = await ctx2.newPage();
page2.on("pageerror", (e) => errors.push(`pageerror2: ${e.message}`));
await page2.route("**/data/gear/*.json", async (route) => {
  const resp = await route.fetch();
  const g = await resp.json();
  const ids = Object.keys(g.items);
  ids.forEach((id, i) => {
    const it = g.items[id];
    if (i % 3 === 0) { it.uncertain = ["Stats differ: source A +12 Strength, source B +10 Strength"]; it.checks = { stats: "conflict" }; }
    else if (i % 3 === 1) it.checks = { name: "single", stats: "single" };
    if (i % 5 === 0 && it.sources?.[0]) it.sources[0].conflict = true;
  });
  await route.fulfill({ response: resp, json: g });
});
await page2.goto(`${BASE}/?race=4&class=11&spec=feral_cat&lvl=24&level=24`);
await page2.waitForSelector("#slot-list li", { timeout: 15000 });
const nUnc = await page2.locator("#slot-list .badge-unc").count();
chk("uncertain: badges shown", nUnc >= 3, `${nUnc}`);
chk("uncertain: '1 source' note shown", (await page2.locator("#slot-list .one-src").count()) >= 1);
chk("uncertain: legend visible", await page2.isVisible("#legend"));
const first = page2.locator("#slot-list .pick .badge-unc").first();
chk("uncertain: reasons hidden until opened", !(await page2.locator("#slot-list .pick .unc-body").first().isVisible()));
await first.focus();
await page2.keyboard.press("Enter");
chk("uncertain: keyboard opens reasons", await page2.locator("#slot-list .pick .unc-body").first().isVisible());
chk("uncertain: reason text", (await page2.locator("#slot-list .pick .unc-body").first().textContent()).includes("Stats differ"));
chk("uncertain: report link carries reasons", decodeURIComponent(await page2.getAttribute("#report-link", "href")).includes("Stats differ"));
await page2.screenshot({ path: `${OUT}/uncertain-desktop.png`, fullPage: true });
await page2.setViewportSize({ width: 375, height: 860 });
await page2.waitForTimeout(200);
chk("uncertain mobile 375: no horizontal scroll", (await page2.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1);
await page2.locator("#slot-list .pick .badge-unc").nth(1).tap().catch(() => page2.locator("#slot-list .pick .badge-unc").nth(1).click());
await page2.screenshot({ path: `${OUT}/uncertain-375.png`, fullPage: true });
await ctx2.close();

// ---- mobile layout: no horizontal scroll
await page.setViewportSize({ width: 375, height: 860 });
await page.goto(`${BASE}/?race=4&class=11&spec=feral_cat&lvl=24&level=24`);
await page.waitForSelector("#slot-list li", { timeout: 15000 });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
chk("mobile: no horizontal scroll", overflow <= 1, `overflow ${overflow}px`);
await page.screenshot({ path: `${OUT}/mobile.png`, fullPage: false });

chk("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
console.log(checks.join("\n"));
await browser.close();
process.exit(checks.some((c) => c.startsWith("FAIL")) ? 1 : 0);
