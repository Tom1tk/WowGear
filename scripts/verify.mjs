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
await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
chk("manual: gear list shows slots", (await page.locator("#rows > li").count()) >= 14);
chk("manual: level output = 24", (await page.textContent("#level-out")) === "24");
chk("manual: todo list filled", (await page.locator("#todo-list .group").count()) >= 1);
chk("manual: item links go to wowhead forever", ((await page.getAttribute("#rows .item-link", "href")) ?? "").includes("/forever/item="));
chk("manual: warcraftdb link", (await page.locator('#rows a.ext[href*="forever.warcraftdb.com/data/item/"]').count()) >= 1);
await page.screenshot({ path: `${OUT}/manual-druid-24.png`, fullPage: true });

// Skyborne (only once the data has it): class list comes from the race
const sky = raceOpts.find((r) => r.startsWith("Skyborne"));
if (sky) {
  await page.selectOption("#m-race", { label: sky });
  chk("manual: skyborne class list not empty", (await page.locator("#m-class option").count()) >= 1);
  await page.selectOption("#m-race", { label: raceOpts.find((r) => r.startsWith("Night Elf")) });
}

// tick the first item -> slot shows "You have it"
await page.locator("#rows .own-box").first().check();
chk("manual: tick marks item as owned", (await page.locator('#rows .delta .none:text("Have it")').count()) >= 1);

// slider to 60, tier buttons come from meta.tiers
await page.click("#lvl-btn");
await page.locator("#level-slider").fill("60");
chk("slider 60 shows tier row", await page.isVisible("#tier-row"));
const tierBtns = await page.locator("#tier-buttons button").count();
const metaTiers = Object.keys((await (await page.request.get(`${BASE}/static/data/meta.json`)).json()).tiers).filter((t) => t !== "0").length;
chk("tier buttons = Pre-raid + meta.tiers", tierBtns === metaTiers + 1, `${tierBtns} buttons, ${metaTiers} meta tiers`);
await page.click('#tier-buttons button[data-tier="1"]');
chk("tier 1 shows its note", (await page.textContent("body")).includes("Raids open")); // tier 1 has no loot until raids are datamined
chk("URL keeps state", page.url().includes("class=11") && page.url().includes("tier=1"));
await page.screenshot({ path: `${OUT}/manual-druid-60-tier1.png`, fullPage: true });

// reload restores from URL
await page.reload();
await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
chk("reload restores level 60", (await page.textContent("#level-out")) === "60");

// Tauren shaman enhancement at 30 (Horde-only class)
await page.goto(`${BASE}/?race=6&class=7&spec=enhancement&lvl=30&level=30`);
await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
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
chk("lookup: ruleset and region shown", bar.includes("Normal") && bar.includes("EU"), bar.replace(/\s+/g, " ").slice(0, 120));
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
await page2.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
await page2.waitForLoadState("load"); // styles (and the fonts request) must be in before visibility checks
const nUnc = await page2.locator("#rows .row-main .badge-unc").count();
chk("uncertain: badges shown", nUnc >= 3, `${nUnc}`);
chk("uncertain: '1 source' note shown", (await page2.locator("#rows .one-src").count()) >= 1);
chk("uncertain: legend visible", await page2.isVisible("#legend"));
const uncRow = page2.locator("#rows > li", { has: page2.locator(".badge-unc") }).first();
chk("uncertain: reasons hidden until opened", !(await uncRow.locator(".reasons").isVisible()));
await uncRow.locator(".chev-btn").focus();
await page2.keyboard.press("Enter");
chk("uncertain: keyboard opens reasons", await uncRow.locator(".reasons").isVisible());
chk("uncertain: reason text", (await uncRow.locator(".reasons").textContent()).trim().length > 10);
chk("uncertain: report link carries reasons", decodeURIComponent(await page2.getAttribute("#report-link", "href")).includes("Stats differ"));
await page2.screenshot({ path: `${OUT}/uncertain-desktop.png`, fullPage: true });
await page2.setViewportSize({ width: 375, height: 860 });
await page2.waitForTimeout(200);
chk("uncertain mobile 375: no horizontal scroll", (await page2.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1);
await page2.locator("#rows .row-main .badge-unc").nth(1).click();
await page2.screenshot({ path: `${OUT}/uncertain-375.png`, fullPage: true });
await ctx2.close();

// ---- P1 percent gain, P5 item lookup, P8 weapon type (stubbed character wearing an invented hat)
const GEAR_URL = `${BASE}/static/data/gear/druid.feral_cat.A.json`;
const gear = await (await page.request.get(GEAR_URL)).json();
const headBest = gear.slots.head.filter((p) => p.level <= 24 && !p.tier).at(-1).items[0];
await page.setViewportSize({ width: 1360, height: 1000 });
await page.route("**/api/character*", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({
  character: { name: "Testa", surname: "Examplar", region: "eu", ruleset: "Normal", level: 24, class_id: 11, class_name: "Druid", race_id: 4, race: "Night Elf", faction: "A", guild: null },
  equipped: { head: { item_id: 999001, name: "Invented Hat", quality: "RARE", score: Math.round(headBest[1] / 2 * 10) / 10 } }, spec: "feral_cat", spec_reason: "stub" }) }));
await page.route("**/api/score", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify({ scores: { 999001: Math.round(headBest[1] / 2 * 10) / 10 } }) }));
await page.goto(`${BASE}/?region=eu&name=Testa&surname=Examplar&spec=feral_cat&level=24`);
await page.waitForSelector("#rows > li .gain", { timeout: 15000 });
const gains = await page.locator("#rows .gain").allTextContents();
chk("P1: gains are percents or 'new'", gains.length > 0 && gains.every((g) => /^(\+\d+(\.\d)?%|new)$/.test(g)), gains.slice(0, 4).join(" "));
const headRow = page.locator("#rows > li", { has: page.locator('.slot:text-is("Head")') });
chk("P1: worn item at half the score = +100%", (await headRow.locator(".gain").textContent()) === "+100%");
chk("P1: empty slot says new", (await page.locator("#rows .gain", { hasText: "new" }).count()) >= 1);
await page.selectOption("#sort", "gain");
chk("P1: biggest-upgrade sort puts 'new' first", (await page.locator("#rows .gain").first().textContent()) === "new");
chk("P1: todo shows percents and an upgrade count", /^\d+ upgrades?$/.test((await page.locator("#todo-list .g-gain").first().textContent()).trim()) && /%|new/.test(await page.locator("#todo-list .g-d").first().textContent()));
await page.unroute("**/api/character*");
await page.unroute("**/api/score");

await page.goto(`${BASE}/?race=4&class=11&spec=feral_cat&lvl=29&level=29`);
await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
// P8
const wopts = await page.locator("#weapon-select option").allTextContents();
chk("P8: weapon select lists types", wopts[0] === "Best (any)" && wopts.length >= 3, wopts.join(", "));
const wval = await page.locator("#weapon-select option").nth(1).getAttribute("value");
await page.selectOption("#weapon-select", wval);
const wsubs = await page.evaluate(async ([url, wval]) => {
  const g = await (await fetch(url)).json();
  return [...document.querySelectorAll("#rows > li:not([hidden]) .item-link")].map((a) => g.items[a.href.split("item=")[1]]).filter((it) => it.class === 2).map((it) => String(it.subclass) === wval);
}, [GEAR_URL, wval]);
chk("P8: weapon rows only show that type", wsubs.length >= 1 && wsubs.every(Boolean), `${wsubs.length} weapon rows`);
chk("P8: URL keeps weapon", page.url().includes(`weapon=${wval}`));
await page.goto(`${BASE}/?race=4&class=11&spec=feral_cat&lvl=29&level=29`);
await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
chk("P8: localStorage restores weapon", (await page.inputValue("#weapon-select")) === wval);
await page.selectOption("#weapon-select", "");
chk("P8: Best (any) clears the URL param", !page.url().includes("weapon="));
// P5
await page.fill("#lk-in", "zzzzqq");
chk("P5: no match says not in lists", (await page.textContent("#lk-list")).includes("Not in this spec's lists"));
const pick = Object.values(gear.items).find((it) => it.name && it.name.length > 6).name;
await page.fill("#lk-in", pick.slice(0, 5).toLowerCase());
chk("P5: type-ahead lists matches", (await page.locator("#lk-list li[role=option]").count()) >= 1);
await page.keyboard.press("ArrowDown");
await page.keyboard.press("Enter");
chk("P5: Enter selects, list closes", await page.locator("#lk-list").isHidden());
const lk = await page.textContent("#lk-out");
chk("P5: result shows score, ranges, source", /score \d/.test(lk) && /(Best|Top 3|On the list)/.test(lk) && lk.includes("Where to get it"), lk.slice(0, 160));
chk("P5: result has wowhead link", (await page.locator('#lk-out a[href*="/forever/item="]').count()) === 1);
await page.keyboard.press("Escape");
chk("P5: Escape clears", (await page.inputValue("#lk-in")) === "" && (await page.textContent("#lk-out")).trim() === "");

// ---- new data fields, hand-edited copy via route interception (frontend/data untouched)
const ctx3 = await browser.newContext({ viewport: { width: 1360, height: 1000 } });
const page3 = await ctx3.newPage();
page3.on("pageerror", (e) => errors.push(`pageerror3: ${e.message}`));
page3.on("console", (m) => { if (m.type() === "error" && !/zamimg|ERR_CERT|Wowhead tooltip/.test(m.text())) errors.push(`console3: ${m.text()}`); });
await page3.route("**/data/gear/*.json", async (route) => {
  const resp = await route.fetch();
  const g = await resp.json();
  for (const p of g.slots.head) if (p.items[1]) p.items[1] = [p.items[1][0], p.items[1][1], Math.round((p.items[0][1] + 100) * 10) / 10];
  const topId = String(g.slots.head.filter((p) => p.level <= 24 && !p.tier).at(-1).items[0][0]);
  const it = g.items[topId];
  it.unscored = ["Use: Fiery Strike"];
  it.random_enchant = { suffix: "of the Bear", note: "Random enchant: best roll shown (of the Bear)" };
  it.set = { name: "Invented Set", pieces: 5, bonuses: [{ count: 2, text: "+10 Agility", scored: true }, { count: 4, text: "Rage on crit", scored: false }] };
  Object.assign(it.sources[0], { chain: { pos: 2, len: 5, first_id: 1, first_name: "An Invented Start", first_level: 12 }, reagents: [["Heavy Leather", 4, 1], ["Rune Thread", 2, 2]], zone: "Testzone" });
  await route.fulfill({ response: resp, json: g });
});
await page3.goto(`${BASE}/?race=4&class=11&spec=feral_cat&lvl=24&level=24`);
await page3.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
const row3 = page3.locator("#rows > li").first();
chk("fields: * after score with title", (await row3.locator(".score").first().textContent()).endsWith("*") && (await row3.locator(".score").first().getAttribute("title")).includes("Fiery Strike"));
await row3.locator(".chev-btn").click();
const det = await row3.locator(".detail").textContent();
chk("fields: expanded row lists unscored, enchant note, set, chain, reagents, zone",
  ["Fiery Strike", "best roll shown", "Invented Set", "Rage on crit", "Quest 2 of 5 — starts with An Invented Start (level 12)", "Needs 4× Heavy Leather, 2× Rune Thread", "Testzone"].every((t) => det.includes(t)), det.slice(0, 200));
const rawName = await row3.locator(".item-link").first().getAttribute("href");
await page3.click("#set-btn");
await page3.selectOption("#score-pick", "set");
const row3b = page3.locator("#rows > li").first();
chk("fields: set toggle re-ranks (other head item wins)", (await row3b.locator(".item-link").first().getAttribute("href")) !== rawName);
chk("fields: set toggle shows score_set", /^\d{3}/.test(await row3b.locator(".score").first().textContent()));
await page3.reload();
await page3.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
chk("fields: set mode persists", (await page3.inputValue("#score-pick")) === "set" || (await page3.locator("#score-pick").evaluate((e) => e.value)) === "set");
await ctx3.close();

// ---- gear planner: add from Best gear, pick by search, route lists the stops
await page.goto(`${BASE}/?race=6&class=11&spec=feral_cat&lvl=30&level=30`);
await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
await page.evaluate(() => Object.keys(localStorage).filter((k) => k.startsWith("wowgear:plan:")).forEach((k) => localStorage.removeItem(k)));
await page.click("#rows > li .row-main >> nth=0");
await page.click("#rows > li.open .detail > .plan-add");
await page.click("#v-plan");
chk("planner: Best gear rows hidden", !(await page.isVisible("#rows")) && await page.isVisible("#plan-rows"));
chk("planner: Add to plan fills the slot", (await page.locator(".plan-row .plan-want a").count()) === 1);
await page.locator(".plan-in").nth(1).click();
await page.keyboard.press("Enter");
chk("planner: search picks an item", (await page.locator(".plan-row .plan-want a").count()) === 2);
chk("planner: route has steps", (await page.locator("#itin .step").count()) >= 1 && !(await page.isVisible("#todo-panel")));
await page.click("#v-best");
chk("planner: back to Best gear", await page.isVisible("#rows") && !(await page.isVisible("#itin-panel")));

// ---- screenshots and the fold rule
const SHOTS_SIZES = [[1920, 1080], [1440, 900], [390, 844]];
for (const [w, h] of SHOTS_SIZES) {
  await page.setViewportSize({ width: w, height: h });
  await page.goto(`${BASE}/?race=6&class=11&spec=feral_cat&lvl=29&level=29`);
  await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
  await page.fill("#lk-in", "a");
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/p2-${w}x${h}.png` });
  if (w === 1920) {
    await page.fill("#lk-in", ""); await page.keyboard.press("Escape");
    const fold = await page.evaluate(() => ({ row: document.querySelectorAll("#rows > li")[7].getBoundingClientRect().bottom, grp: document.querySelector("#todo-list .group").getBoundingClientRect().bottom, h: innerHeight }));
    chk("fold 1920x1080: first 8 rows and first todo group visible", fold.row <= fold.h && fold.grp <= fold.h, JSON.stringify(fold));
  }
}

// ---- mobile layout: no horizontal scroll
await page.setViewportSize({ width: 375, height: 860 });
await page.goto(`${BASE}/?race=4&class=11&spec=feral_cat&lvl=24&level=24`);
await page.waitForSelector('#results[data-state="ready"] #rows > li', { timeout: 15000 });
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
chk("mobile: no horizontal scroll", overflow <= 1, `overflow ${overflow}px`);
await page.screenshot({ path: `${OUT}/mobile.png`, fullPage: false });

chk("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
console.log(checks.join("\n"));
await browser.close();
process.exit(checks.some((c) => c.startsWith("FAIL")) ? 1 : 0);
