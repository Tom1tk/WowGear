import { describeSource as describeIn, catsOf, CATS, EFFORT, locText, pinCommand, mapImage } from "./sources.js";
import { setupLookup } from "./lookup.js";

const $ = (id) => document.getElementById(id);
const DATA = "/static/data";
const REPORT_URL = "https://github.com/Tom1tk/WowGear/issues/new";
const QUALITY = { 1: "common", 2: "uncommon", 3: "rare", 4: "epic", 5: "legendary" };
const QUALITY_BY_TYPE = { POOR: 0, COMMON: 1, UNCOMMON: 2, RARE: 3, EPIC: 4, LEGENDARY: 5 };
const SLOT_LABEL = {
  head: "Head", neck: "Neck", shoulders: "Shoulders", back: "Back", chest: "Chest",
  wrist: "Wrist", hands: "Hands", waist: "Waist", legs: "Legs", feet: "Feet",
  ring: "Ring", trinket: "Trinket", main_hand: "Main hand", off_hand: "Off hand",
  two_hand: "Two-hand", ranged: "Ranged", relic: "Relic",
};
const GROUP = { two_hand: "weapons", main_hand: "weapons", off_hand: "weapons", ranged: "weapons", relic: "weapons", neck: "jewellery", ring: "jewellery", trinket: "jewellery" }; // rest: armour
const grpOf = (slot) => GROUP[slot] || "armour";
const BAR_CAP = 50; // gain bars cap at +50% so one outlier does not flatten the rest
const UP = 0.05;    // smaller gains (percent) round to 0.0% and count as no upgrade
// Item subclass (item class 2 = weapon) -> name for the weapon-type select.
const WEAPON_TYPES = { 0: "Axe (1H)", 1: "Axe (2H)", 2: "Bow", 3: "Gun", 4: "Mace (1H)", 5: "Mace (2H)", 6: "Polearm", 7: "Sword (1H)", 8: "Sword (2H)", 10: "Staff", 13: "Fist weapon", 15: "Dagger", 16: "Thrown", 18: "Crossbow", 19: "Wand" };
const fmtGain = (g) => (g === Infinity ? "new" : g >= 10 ? `+${Math.round(g)}%` : `+${g.toFixed(1)}%`);
const ARMOR_ORDER = ["head", "neck", "shoulders", "back", "chest", "wrist", "hands", "waist", "legs", "feet"];
const WOWHEAD = "https://www.wowhead.com/forever/item=";
const ICON_CHEV = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="m3.5 6 4.5 4.5L12.5 6" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const WARCRAFTDB = "https://forever.warcraftdb.com/data/item/";
const ICON_WARN = '<svg class="ico" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.5 15 14H1L8 1.5Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 6v3.5M8 11.6v.1" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';

const state = {
  meta: null,
  mode: "lookup",        // lookup | manual
  char: null,            // looked-up character (lookup mode)
  manual: null,          // {raceId, classId, spec, level}
  spec: null,
  level: 20,
  tier: 0,
  gear: null,
  gearKey: "",
  scores: {},            // equipped item id -> score (lookup mode)
  wtype: "",             // weapon-type filter: item subclass as string, "" = best of any type
  scoreSet: false,       // score with set bonuses and effects (score_set) instead of raw stats
};
const gearCache = new Map();

// ---------------------------------------------------------------- storage
function store(key, value) {
  try { localStorage.setItem(`wowgear:${key}`, JSON.stringify(value)); } catch { /* best effort */ }
}
function recall(key, fallback = null) {
  try {
    const raw = localStorage.getItem(`wowgear:${key}`);
    return raw ? JSON.parse(raw) : fallback;
  } catch { return fallback; }
}

// ---------------------------------------------------------------- scene

// Background art: WoW Forever launch press kit (bg/kit/). The race still sets the colour theme.
const SCENES = {
  "barrow-deeps": "Barrow Deeps", "campfire": "Campfire", "dalaran": "Dalaran", "drowned-city": "The Drowned City",
  "hyjal": "Mount Hyjal", "hyjal-summit": "Hyjal Summit", "mulgore": "Mulgore", "new-water": "Open sea",
  "riverglades": "Riverglades", "shendralas": "Shen'dralas", "skywatch": "Skywatch", "zephras": "Zephras Isle",
  "key-alliance": "Alliance key art", "key-horde": "Horde key art",
};
const ROTATE_MS = 90_000;
let sceneRace = null;
let rotateTimer = 0;

function raceSlug(raceId) {
  const r = state.meta?.races[String(raceId)];
  if (!r) return null;
  const slug = (r.slug || r.name.toLowerCase()).replace(/[\s_]+/g, "-");
  return slug.endsWith("skyborne") ? "skyborne" : slug; // both Skyborne races share one theme
}
function sceneImage() {
  const pick = recall("bg", "faction");
  if (pick === "rotate") {
    const keys = Object.keys(SCENES);
    return keys[Math.floor(Date.now() / ROTATE_MS) % keys.length];
  }
  if (SCENES[pick]) return pick;
  const faction = state.meta?.races[String(sceneRace)]?.faction;
  return faction === "A" ? "key-alliance" : "key-horde";
}
function showImage(key) {
  const [a, b] = [$("scene-a"), $("scene-b")];
  const url = `/static/bg/kit/${key}.jpg`;
  if ([a, b].some((l) => l.classList.contains("on") && l.dataset.key === key)) return;
  const img = new Image();
  img.onload = () => {
    if (img.dataset.stale) return;
    const [shown, hidden] = a.classList.contains("on") ? [a, b] : [b, a];
    hidden.style.backgroundImage = `url('${url}')`;
    hidden.dataset.key = key;
    hidden.classList.add("on");
    shown.classList.remove("on");
  };
  showImage.pending?.setAttribute("data-stale", "1");
  showImage.pending = img;
  img.src = url;
}
function refreshScene() {
  clearInterval(rotateTimer);
  showImage(sceneImage());
  if (recall("bg", "faction") === "rotate") rotateTimer = setInterval(() => showImage(sceneImage()), ROTATE_MS);
}
// Cross-fade the background and switch the race colour theme.
function setScene(raceId) {
  sceneRace = raceId;
  const key = raceSlug(raceId);
  if (key) document.documentElement.dataset.race = key;
  else delete document.documentElement.dataset.race;
  refreshScene();
}
function initSettings() {
  const bg = $("bg-pick");
  bg.append(el("option", { value: "faction" }, "My faction's key art"), el("option", { value: "rotate" }, "Rotate through all"));
  for (const [k, name] of Object.entries(SCENES)) bg.append(el("option", { value: k }, name));
  bg.value = recall("bg", "faction");
  bg.onchange = () => { store("bg", bg.value); refreshScene(); };
  const theme = $("theme-pick");
  theme.value = recall("theme", "dark");
  document.documentElement.dataset.theme = theme.value;
  theme.onchange = () => { store("theme", theme.value); document.documentElement.dataset.theme = theme.value; };
  const sm = $("score-pick");
  state.scoreSet = recall("scoremode", "raw") === "set";
  sm.value = state.scoreSet ? "set" : "raw";
  sm.onchange = () => { state.scoreSet = sm.value === "set"; store("scoremode", sm.value); render(); };
  const pin = $("pin-pick");
  pin.value = recall("pin", "tomtom");
  pin.onchange = () => store("pin", pin.value);
  refreshScene();
}

// Map-pin button for a source with a known spot: hover shows where, click copies a chat command for the game.
function pinBtn(src) {
  const l = src?.loc ?? state.meta.instances[src?.instance]?.entrance; // dungeon sources: pin the entrance
  if (!l) return null;
  const img = mapImage(l.zone);
  const b = el("button", { type: "button", class: "pin", title: img ? null : `${locText(l)}. Click to copy a map-pin command, then paste it into game chat.` }, `📍 ${locText(l)}`);
  b.addEventListener("click", async (e) => {
    e.stopPropagation();
    const cmd = pinCommand(l, recall("pin", "tomtom"));
    try { await navigator.clipboard.writeText(cmd); b.dataset.done = "Copied: paste in game chat"; }
    catch { window.prompt("Copy this, then paste it into game chat:", cmd); }
    setTimeout(() => delete b.dataset.done, 2500);
  });
  if (img) {
    b.addEventListener("mouseenter", () => showMap(b, img, l));
    b.addEventListener("focus", () => showMap(b, img, l));
    b.addEventListener("mouseleave", hideMap);
    b.addEventListener("blur", hideMap);
  }
  return b;
}

// Hover map: the zone's map with a dot on the spot, like Wowhead's vendor/quest maps.
let mapPop;
function showMap(anchor, img, l) {
  mapPop ??= document.body.appendChild(el("div", { class: "map-pop", role: "tooltip" }));
  mapPop.replaceChildren(
    el("div", { class: "map-box" }, el("img", { src: img, alt: `${l.zone} map` }), el("span", { class: "map-dot", style: `left:${l.x}%;top:${l.y}%` })),
    el("div", { class: "map-cap" }, `${locText(l)}. Click the pin to copy a map-pin command.`));
  const r = anchor.getBoundingClientRect(), w = Math.min(420, innerWidth - 16), h = w * 2 / 3 + 30;
  const left = Math.max(8, Math.min(r.left, innerWidth - w - 8));
  const top = r.bottom + 6 + h < innerHeight ? r.bottom + 6 : Math.max(8, r.top - 6 - h);
  Object.assign(mapPop.style, { width: `${w}px`, left: `${left}px`, top: `${top}px`, display: "block" });
}
function hideMap() { if (mapPop) mapPop.style.display = "none"; }

// ---------------------------------------------------------------- helpers
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function showStatus(message, isError = false) {
  const s = $("status");
  s.textContent = message;
  s.classList.toggle("error", isError);
  s.hidden = false;
}
function hideStatus() { $("status").hidden = true; }

function itemLink(id, info) {
  const q = QUALITY[info?.quality] || "common";
  return el("a", {
    class: `item-link q-${q}`, href: `${WOWHEAD}${id}`, "data-wowhead": `item=${id}&domain=forever`,
    target: "_blank", rel: "noopener", "data-wh-icon-size": "small",
  }, info?.name || `Item ${id}`);
}

function refreshTooltips() {
  try { window.$WowheadPower?.refreshLinks(); } catch { /* tooltips are optional */ }
}

function sourceReasons(src) {
  const inst = src.instance && state.meta.instances[src.instance];
  return [
    ...(src.conflict ? ["Our databases disagree about this source (for example the drop chance, or which monster or quest it comes from)."] : []),
    ...(inst?.uncertain || []).map((r) => `${inst.name}: ${r}`),
  ];
}

function currentClass() {
  const cid = state.mode === "lookup" ? state.char?.character.class_id : state.manual?.classId;
  return cid ? { id: String(cid), ...state.meta.classes[String(cid)] } : null;
}
function currentFaction() {
  if (state.mode === "lookup") return state.char?.character.faction || "A";
  return state.meta.races[String(state.manual.raceId)].faction;
}
function characterLevel() {
  return state.mode === "lookup" ? state.char.character.level : state.manual.level;
}

// ---------------------------------------------------------------- gear data
async function loadGear() {
  const cls = currentClass();
  const key = `${cls.slug}.${state.spec}.${currentFaction()}`;
  if (state.gearKey === key && state.gear) return state.gear;
  if (!gearCache.has(key)) {
    const resp = await fetch(`${DATA}/gear/${key}.json`);
    if (!resp.ok) throw new Error("No gear list for this class and spec.");
    gearCache.set(key, await resp.json());
  }
  state.gear = gearCache.get(key);
  state.gearKey = key;
  return state.gear;
}

const pointKey = (p) => (p.tier > 0 ? 60 + p.tier : p.level);

// Breakpoints of a slot with the weapon-type filter and score mode applied (cached per gear/filter/mode).
// Items are [id, score, score_set?]; the score here is the one in use. Limit: only items on the pipeline's top lists can appear.
let pointsCache = { key: "", slots: {} };
const wtypeOk = (id) => { const it = state.gear.items[id]; return !state.wtype || it.class !== 2 || String(it.subclass) === state.wtype; };
function slotPoints(slot) {
  const key = `${state.gearKey}|${state.wtype}|${state.scoreSet}`;
  if (pointsCache.key !== key) pointsCache = { key, slots: {} };
  return (pointsCache.slots[slot] ??= (state.gear.slots[slot] || []).map((p) => {
    const items = p.items.filter(([id]) => wtypeOk(id)).map(([id, sc, set]) => [id, state.scoreSet ? set ?? sc : sc]);
    return { ...p, items: state.scoreSet ? items.sort((a, b) => b[1] - a[1]) : items };
  }).filter((p) => p.items.length));
}

function pointAt(slot, level = state.level, tier = state.tier) {
  const points = slotPoints(slot);
  const target = level >= 60 && tier > 0 ? 60 + tier : Math.min(level, 60);
  let found = null;
  for (const p of points) if (pointKey(p) <= target) found = p;
  return found;
}

// First later level where this slot (2nd ring/trinket: index 1) gets a pick: shown on an empty row.
function nextFill(slot, index) {
  const target = state.level >= 60 && state.tier > 0 ? 60 + state.tier : state.level;
  for (const p of slotPoints(slot)) {
    const ok = p.items.filter(([id]) => itemOk(id));
    if (pointKey(p) > target && ok[index]) return { p, id: ok[index][0] };
  }
  return null;
}

function firstSeen(slot, iid) {
  for (const p of slotPoints(slot)) {
    if (p.items.some(([id]) => id === iid)) return p;
  }
  return null;
}

// Which weapon setup scores higher at this level: two-hander or main + off hand.
function weaponPlan() {
  const two = pointAt("two_hand")?.items[0];
  const mh = pointAt("main_hand")?.items[0];
  const oh = pointAt("off_hand")?.items[0];
  const pair = (mh ? mh[1] : 0) + (oh ? oh[1] : 0);
  if (two && two[1] >= pair) return { use: ["two_hand"], alt: mh ? ["main_hand", "off_hand"] : [] };
  return { use: ["main_hand", "off_hand"].filter((s) => state.gear.slots[s]), alt: two ? ["two_hand"] : [] };
}

// ---------------------------------------------------------------- equipped / owned
function equippedFor(row) {
  if (state.mode !== "lookup" || !state.char) return null;
  const eq = state.char.equipped;
  const cls = currentClass();
  switch (row.slot) {
    case "ring": return orderedPair(eq.ring_1, eq.ring_2)[row.index];
    case "trinket": return orderedPair(eq.trinket_1, eq.trinket_2)[row.index];
    case "two_hand": return eq.two_hand || eq.main_hand || null;
    case "main_hand": return eq.main_hand || eq.two_hand || null;
    case "relic": return eq.ranged || null;
    case "ranged": return cls?.slug === "druid" || cls?.slug === "shaman" || cls?.slug === "paladin" ? null : eq.ranged || null;
    default: return eq[row.slot] || null;
  }
}

function orderedPair(a, b) {
  const list = [a, b].filter(Boolean);
  list.sort((x, y) => (scoreOf(y) ?? -1) - (scoreOf(x) ?? -1));
  return [list[0] || null, list[1] || null];
}

function scoreOf(eq) {
  if (!eq) return null;
  const s = state.scores[eq.item_id];
  return s === undefined ? eq.score ?? null : s;
}

function ownedKey() { return `owned:${state.gearKey}`; }
function ownedSet() { return new Set(recall(ownedKey(), [])); }
function toggleOwned(iid, on) {
  const set = ownedSet();
  if (on) set.add(iid); else set.delete(iid);
  store(ownedKey(), [...set]);
  render();
}


const describeSource = (src) => describeIn(state.meta, src);

// What you wear in a slot, for comparing a looked-up item: null = nothing there ("new"); rings/trinkets use the weaker one.
function wornScoreFor(slot) {
  if (state.mode === "manual") {
    const owned = ownedSet(), hit = slotPool(slot).find(([id]) => owned.has(id));
    return hit ? { id: hit[0], name: state.gear.items[hit[0]].name, score: hit[1] } : null;
  }
  if (!state.char) return null;
  const eqs = (slot === "ring" || slot === "trinket" ? [0, 1] : [0]).map((index) => equippedFor({ slot, index }));
  if (eqs.some((e) => !e)) return null;
  return eqs.map((e) => ({ id: String(e.item_id), name: e.name, score: scoreOf(e) })).sort((a, b) => (a.score ?? -1) - (b.score ?? -1))[0];
}

// Table view state (not part of the URL): source filter, sort, slot group, opened rows.
// Filters, sort and open/closed sections are remembered in this browser.
const ui = { sort: recall("sort", "slot"), src: new Set(recall("src", [])), slot: recall("slot", "all"), open: new Set(recall("open-rows", [])),
  shut: new Set(recall("shut-groups", [])), boe: recall("boe", true), bop: recall("bop", true), epic: recall("epic", true) };
const srcOk = (s) => !ui.src.size || catsOf(s).some((c) => ui.src.has(c));
const narrowed = () => ui.src.size > 0 || !ui.boe || !ui.bop || !ui.epic;
// Source filter plus the BoE / BoP / epic toggles (quality 4 = epic, 5 = legendary).
const itemOk = (id) => { const it = state.gear.items[id];
  return (ui.boe || it.binding !== "ON_EQUIP") && (ui.bop || it.binding !== "ON_ACQUIRE") && (ui.epic || it.quality < 4) && (it.sources || []).some(srcOk); };
// sources with the allowed ones first, so the shown source is one the filter lets through
const orderedSrcs = (info) => { const all = info.sources || []; return [...all.filter(srcOk), ...all.filter((s) => !srcOk(s))]; };
function effort(srcs) {
  const ok = srcs.filter(srcOk);
  const ranks = (s) => catsOf(s).filter((c) => !ui.src.size || ui.src.has(c)).map((c) => EFFORT[c]);
  const rank = Math.min(...ok.map((s) => Math.min(...ranks(s))));
  const chance = Math.max(0, ...ok.filter((s) => Math.min(...ranks(s)) === rank).map((s) => s.chance || 0));
  return { rank, chance };
}

const reasonsOf = (info) => [...(info.uncertain || []), ...(info.sources?.[0] ? sourceReasons(info.sources[0]) : [])];
const uncBadge = () => Object.assign(el("span", { class: "badge badge-unc" }), { innerHTML: `${ICON_WARN}Uncertain` });

// Every item that was best for this slot at some point up to the viewed level, best score first.
function slotPool(slot) {
  const target = state.level >= 60 && state.tier > 0 ? 60 + state.tier : Math.min(state.level, 60);
  const best = new Map();
  for (const p of slotPoints(slot)) if (pointKey(p) <= target) for (const [id, sc] of p.items) best.set(id, sc);
  return [...best].sort((a, b) => b[1] - a[1]);
}

// What the player has for this row, and the gain from the best pick. Manual mode: ticked items.
function wornFor(r, pick) {
  const [pid, best] = pick;
  // percent over the worn item; Infinity ("new") when its score is 0
  // worn items under 10% of the best pick count as nothing useful ("new"): a percent over ~0 is meaningless
  const gainOver = (score) => { if (!(score > 0) || score < best * 0.1) return Infinity; const g = (best - score) / score * 100; return g >= UP ? g : 0; };
  const named = (id) => ({ id, name: state.gear.items[id]?.name, quality: state.gear.items[id]?.quality });
  if (state.mode === "manual") {
    const owned = ownedSet();
    if (owned.has(pid)) return { ...named(pid), score: best, gain: 0, tag: "Have it" };
    const alt = r.cands.find(([id]) => owned.has(id));
    return alt ? { ...named(alt[0]), score: alt[1], gain: gainOver(alt[1]) } : { gain: Infinity };
  }
  const eq = equippedFor(r);
  if (!eq) return { gain: Infinity };
  const w = { id: String(eq.item_id), name: eq.name, quality: QUALITY_BY_TYPE[eq.quality], score: scoreOf(eq) };
  if (w.id === pid) return { ...w, gain: 0, tag: "Best" };
  if (r.cands.some(([id]) => id === w.id)) return { ...w, gain: 0, tag: "On list" };
  if (w.score == null) return { ...w, gain: 0, tag: "Can't score", unknown: true };
  return { ...w, gain: gainOver(w.score) };
}

// Rows: one per slot (rings and trinkets twice), best pick under the source filter, then sorted.
function buildRows() {
  const { use } = weaponPlan();
  const slots = [...ARMOR_ORDER, "ring", "ring", "trinket", "trinket", ...use, "ranged", "relic"].filter((s) => state.gear.slots[s]);
  const seen = {};
  const rows = slots.map((slot, order) => {
    const index = seen[slot] = (seen[slot] ?? -1) + 1;
    const pair = slot === "ring" || slot === "trinket";
    const cands = pointAt(slot)?.items || [];
    // With a filter on, look beyond the top picks: the whole slotPool.
    const ok = (narrowed() ? slotPool(slot) : cands).filter(([id]) => itemOk(id));
    const top = ok.slice(0, pair ? 2 : 1), pick = ok[pair ? index : 0] || null;
    const row = { slot, order, index, pair, cands, pick, next: pick ? null : nextFill(slot, index), alts: cands.filter((c) => !top.includes(c)), gain: 0, filtered: !pick && narrowed() && cands.length > 0,
      label: pair ? `${SLOT_LABEL[slot]} ${index + 1}` : SLOT_LABEL[slot] };
    if (pick) {
      row.srcs = orderedSrcs(state.gear.items[pick[0]]);
      row.effort = effort(row.srcs);
      row.worn = wornFor(row, pick);
      row.gain = row.worn.gain;
    }
    return row;
  });
  const gainRank = (r) => (!r.pick ? 3 : r.gain >= UP ? 0 : r.worn.unknown ? 1 : 2); // gains, can't score, no gain, no pick
  const cmp = {
    slot: (a, b) => a.order - b.order,
    gain: (a, b) => gainRank(a) - gainRank(b) || b.gain - a.gain,
    easy: (a, b) => !a.pick - !b.pick || (a.pick && (a.effort.rank - b.effort.rank || state.gear.items[a.pick[0]].required_level - state.gear.items[b.pick[0]].required_level || b.effort.chance - a.effort.chance)),
  }[ui.sort];
  return rows.sort((a, b) => cmp(a, b) || a.order - b.order);
}

// ---------------------------------------------------------------- render
function render() {
  if (!state.gear) return;
  const lvl = state.level;
  $("level-out").textContent = String(lvl);
  $("lvl-btn-n").textContent = String(lvl);
  $("level-slider").value = String(lvl);
  $("tier-row").hidden = lvl < 60;
  const tierNote = state.meta.tier_notes?.[state.tier];
  $("tier-note").hidden = !tierNote;
  $("tier-note").textContent = tierNote || "";
  document.querySelectorAll("#tier-buttons button").forEach((b) => b.setAttribute("aria-checked", String(Number(b.dataset.tier) === state.tier)));
  const charLvl = characterLevel();
  $("level-note").textContent = lvl === charLvl ? "Your level" :
    lvl > charLvl ? `${lvl - charLvl} level${lvl - charLvl > 1 ? "s" : ""} ahead of you` : `${charLvl - lvl} below your level`;
  const g = state.gear;
  $("gear-title").textContent = lvl >= 60 && state.tier > 0 ? `Best gear: ${state.meta.tiers[state.tier]}` : `Best gear at level ${lvl}`;
  $("gear-sub").textContent = `${g.spec_name} ${g.class} · ${g.faction === "A" ? "Alliance" : "Horde"}. Click a row for where to get it and alternatives.`;
  const rows = buildRows();
  renderWeaponNote();
  renderRows(rows);
  renderTodo(rows);
  renderUpcoming();
  itemLookup.refresh();
  renderCounts(rows);
  updateReportLink(rows);
  updateUrl();
  refreshTooltips();
}

function renderWeaponNote() {
  const note = $("weapon-note"), plan = weaponPlan();
  const altItems = plan.alt.map((s) => pointAt(s)?.items[0]).filter(Boolean);
  note.hidden = !altItems.length;
  if (!altItems.length) return;
  note.replaceChildren(
    plan.use[0] === "two_hand" ? "A two-handed weapon scores best here. Other option: " : "One-hand + off-hand scores best here. Other option: ",
    ...altItems.flatMap(([id, s], i) => [i ? " + " : "", itemLink(id, state.gear.items[id]), ` (${s})`]));
}

function renderCounts(rows) {
  $("n-all").textContent = rows.length;
  for (const g of ["armour", "weapons", "jewellery"]) $(`n-${g}`).textContent = rows.filter((r) => grpOf(r.slot) === g).length;
  // source picker: how many slots could use each category
  document.querySelectorAll("#srcpick input").forEach((b) => {
    if (b.value !== "all") b.nextElementSibling.textContent = rows.filter((r) => slotPool(r.slot).some(([id]) => (state.gear.items[id].sources || []).some((s) => catsOf(s).includes(b.value)))).length;
  });
}

function renderRows(rows) {
  const ol = $("rows");
  ol.replaceChildren();
  for (const r of rows) {
    const g = grpOf(r.slot);
    const li = el("li", { class: `row${ui.open.has(r.label) ? " open" : ""}`, "data-g": g, hidden: ui.slot !== "all" && g !== ui.slot });
    const main = el("div", { class: "row-main" }, el("span", { class: "slot" }, r.label));
    ol.append(li);
    if (!r.pick) {
      const none = r.filtered ? `No pick with these filters at level ${state.level}.` : `Nothing with useful stats at level ${state.level}.`;
      const n = r.next, nInfo = n && state.gear.items[n.id], nSrc = n && describeSource(orderedSrcs(nInfo)[0]);
      main.append(el("span", { class: "item muted nopick" }, none, ...(n ? [" Next: ", itemLink(n.id, nInfo), ` at ${n.p.tier > 0 ? `raid tier ${n.p.tier}` : `level ${n.p.level}`}${nSrc ? ` (${nSrc.label})` : ""}.`] : [])));
      li.append(main);
      continue;
    }
    const [iid, score] = r.pick, info = state.gear.items[iid], seen = firstSeen(r.slot, iid);
    const reasons = reasonsOf(info);
    main.append(
      el("span", { class: "item" }, itemLink(iid, info),
        seen && seen.tier === 0 && seen.level > 10 ? el("span", { class: "badge", title: `Appears in the list from level ${seen.level}` }, `lvl ${seen.level}`) : null,
        info.binding === "ON_ACQUIRE" ? el("span", { class: "badge badge-bop", title: "Binds when picked up" }, "BoP") : el("span", { class: "badge", title: "Binds when equipped" }, "BoE"),
        info.special ? el("span", { class: "badge badge-fx", title: info.special }, "special") : null,
        reasons.length ? Object.assign(uncBadge(), { title: reasons.join("\n") }) : null),
      scoreCell(score, info));
    const d = r.srcs[0] ? describeSource(r.srcs[0]) : null;
    main.append(el("span", { class: "src", title: d ? `${d.label}. ${d.text}${d.where ? ` ${d.where}.` : ""}` : "" }, d ? d.label : "Source unknown"));
    main.append(wornCell(r, iid));
    const btn = el("button", { type: "button", class: "chev-btn", "aria-expanded": String(ui.open.has(r.label)), "aria-label": `Details for ${r.label}` });
    btn.innerHTML = ICON_CHEV;
    main.append(btn);
    li.append(main, buildDetail(r, info, iid, reasons));
    const toggle = () => {
      const open = li.classList.toggle("open");
      btn.setAttribute("aria-expanded", String(open));
      if (open) ui.open.add(r.label); else ui.open.delete(r.label);
      store("open-rows", [...ui.open]);
    };
    main.addEventListener("click", (e) => { if (!e.target.closest("a, input, label")) toggle(); });
    btn.addEventListener("click", (e) => { e.stopPropagation(); toggle(); });
  }
}

function scoreCell(score, info) {
  const un = info.unscored?.length;
  return el("span", { class: "score", title: un ? `Score for your spec. Not counted: ${info.unscored.join("; ")}` : "Score for your spec (compare within a slot)" }, String(score), un ? "*" : null);
}

// Extra facts from the data: unscored stats, random-enchant note, set bonuses.
function extrasOf(info) {
  const out = [];
  if (info.unscored?.length) out.push(el("p", { class: "muted" }, `* Not counted in the score: ${info.unscored.join("; ").replace(/\.$/, "")}.`));
  if (info.random_enchant?.note) out.push(el("p", { class: "muted" }, info.random_enchant.note));
  const set = info.set;
  if (set) out.push(el("div", { class: "setinfo" }, el("p", {}, `Set: ${set.name}${set.pieces ? ` (${set.pieces.length ?? set.pieces} pieces)` : ""}`),
    set.bonuses?.length ? el("ul", {}, set.bonuses.map((b) => el("li", {}, `(${b.count}) ${b.text}${b.scored ? " — counted in the set score" : ""}`))) : null));
  return out;
}

// "You wear" cell: item + score (or ticked item in manual mode), "I have this" box, gain bar.
function wornCell(r, iid) {
  const w = r.worn, cell = el("span", { class: "worn" });
  if (state.mode === "manual") {
    cell.append(el("input", { type: "checkbox", class: "own-box", checked: ownedSet().has(iid), title: "I have this", "aria-label": `I have ${state.gear.items[iid].name || iid}`, onchange: (e) => toggleOwned(iid, e.target.checked) }));
  }
  if (!w.id) cell.append(el("span", { class: "worn-name muted" }, state.mode === "manual" ? "Not ticked" : "Empty slot"));
  else cell.append(el("span", { class: "worn-name" }, itemLink(w.id, w)), ...(w.score != null ? [el("span", { class: "score" }, String(w.score))] : []));
  cell.append(r.gain >= UP
    ? el("span", { class: "delta", title: r.gain === Infinity ? "Nothing useful worn here" : `Upgrade ${fmtGain(r.gain)} over what you wear` }, el("span", { class: "bar", style: `width:${Math.max(4, Math.round(Math.min(r.gain, BAR_CAP) / BAR_CAP * 34))}px` }), el("span", { class: "gain" }, fmtGain(r.gain)))
    : el("span", { class: "delta" }, el("span", { class: "none" }, w.tag || "none")));
  return cell;
}

function buildDetail(r, info, iid, reasons) {
  const srcs = r.srcs, d = el("div", { class: "detail" });
  if (reasons.length) d.append(el("ul", { class: "reasons" }, reasons.map((x) => el("li", {}, x))));
  d.append(...extrasOf(info));
  if (srcs[0]) { const s = describeSource(srcs[0]); d.append(el("p", {}, `${s.label}. ${s.text} `, pinBtn(srcs[0]), " ", el("a", { class: "ext", href: `${WARCRAFTDB}${iid}`, target: "_blank", rel: "noopener", title: "Open this item on forever.warcraftdb.com" }, "warcraftdb"))); }
  if (srcs.length > 1) d.append(el("h3", {}, `${srcs.length - 1} more source${srcs.length > 2 ? "s" : ""}`), el("ul", {}, srcs.slice(1).map((s) => { const x = describeSource(s); return el("li", {}, `${x.label}. ${x.text} `, pinBtn(s)); })));
  const checks = Object.values(info.checks || {});
  if (!info.uncertain?.length && checks.length && checks.every((c) => c === "single")) d.append(el("p", { class: "one-src" }, "1 source: only one database has this item, so it is not cross-checked."));
  if (r.worn.unknown) d.append(el("p", { class: "muted" }, "Random-stat items (e.g. “… of the Monkey”) and some special items have no fixed score. Compare the stats yourself."));
  if (r.alts.length) d.append(el("h3", {}, `${r.alts.length} alternative${r.alts.length > 1 ? "s" : ""}`), el("ul", {}, r.alts.map(([aid, as]) => {
    const ai = state.gear.items[aid], s = ai.sources?.[0] ? describeSource(ai.sources[0]) : null;
    return el("li", {}, itemLink(aid, ai), el("span", { class: "num muted" }, ` ${as}${ai.unscored?.length ? "*" : ""}`), s ? el("span", { class: "muted" }, ` — ${s.label}`) : null,
      reasonsOf(ai).length ? el("span", { class: "muted" }, " (Uncertain)") : null,
      state.mode === "manual" ? el("label", { class: "own own-small" }, el("input", { type: "checkbox", checked: ownedSet().has(aid), onchange: (e) => toggleOwned(aid, e.target.checked) }), " have") : null);
  })));
  return d;
}

function renderTodo(rows) {
  const charLvl = characterLevel(), viewing = state.level;
  $("todo-sub").textContent = viewing === charLvl ? "Grouped by where to go, biggest gains first."
    : `For the gear at level ${viewing}${viewing > charLvl ? " (plan ahead)" : ""}.`;
  const groups = new Map();
  for (const r of rows) {
    if (!r.pick || r.gain < UP || !r.srcs[0]) continue;
    const d = describeSource(r.srcs[0]);
    const g = groups.get(d.key) || { key: d.key, label: d.label, src: r.srcs[0], items: [] };
    g.items.push({ r, d });
    groups.set(d.key, g);
  }
  // groups by their biggest gain (then most upgrades); items inside by gain. Header shows the upgrade count, not a sum of percents.
  const top = (g) => g.items[0].r.gain;
  for (const g of groups.values()) g.items.sort((a, b) => b.r.gain - a.r.gain);
  const sorted = [...groups.values()].sort((a, b) => (top(a) === top(b) ? b.items.length - a.items.length : top(b) - top(a))).slice(0, 8);
  const box = $("todo-list");
  box.replaceChildren();
  const sugg = suggestions(rows);
  if (sugg.length) box.append(el("h3", { class: "g-sec" }, "Suggested"), ...sugg.map((g) => groupEl(g, `s:${g.kind}`)),
    el("h3", { class: "g-sec" }, "Your Best gear list, by where to get it"));
  for (const g of sorted) box.append(groupEl({ ...g, items: g.items.map(({ r, d }) => ({ label: r.label, id: r.pick[0], gain: r.gain, d })) }, `p:${g.key}`));
  if (!sorted.length) box.append(el("p", { class: "muted" }, state.mode === "manual" ? "Tick the items you have. Then this list shows where to go for the rest." : "Nothing to do at this level: your gear matches the list. Try the next levels on the slider."));
}

// One "What to do next" group: a place, then the items to get there.
// key: remembers if this group is folded (suggestions by activity, places by place).
function groupEl(g, key) {
  const ul = el("ul", { class: "g-list" }, g.items.map(({ label, id, gain, d }) => {
    const info = state.gear.items[id];
    return el("li", { title: `${d.text}${d.where ? ` ${d.where}.` : ""}` },
      el("span", { class: "slot" }, label),
      el("span", { class: "g-it" }, itemLink(id, info), reasonsOf(info).length ? Object.assign(uncBadge(), { style: "margin-left:6px" }) : null),
      el("span", { class: "g-d" }, fmtGain(gain)),
      d.extra ? el("span", { class: "g-x muted" }, d.extra) : null);
  }));
  const n = g.items.length;
  const box = el("details", { class: "group", open: !ui.shut.has(key) },
    el("summary", { class: "g-head" }, el("strong", {}, g.label, " ", pinBtn(g.src)),
      el("span", { class: "g-gain", title: "Slots to upgrade here" }, `${n} upgrade${n > 1 ? "s" : ""}`)), ul);
  box.addEventListener("toggle", () => {
    if (box.open) ui.shut.delete(key); else ui.shut.add(key);
    store("shut-groups", [...ui.shut]);
  });
  return box;
}

// Suggested place per activity: the dungeon (quest, vendor ...) with the most slot upgrades over what the player has,
// counting every item that was a best pick up to this level, not only the top pick.
const SUGGEST = [["Dungeon", ["ddrop"]], ["Quest", ["wq", "dq"]], ["Vendor", ["vendor", "rep"]], ["Craft", ["craft"]], ["Farm", ["wdrop"]]];
function suggestions(rows) {
  const base = {}; // per slot: score of what the player has (pairs: the weaker one)
  const floor = {}; // only items close to the best pick (80%) count: far weaker ones are not worth the trip
  for (const r of rows) {
    if (!r.pick || r.worn?.unknown) continue;
    const have = r.worn.gain === Infinity ? 0 : r.worn.score ?? r.pick[1];
    base[r.slot] = Math.min(base[r.slot] ?? Infinity, have);
    floor[r.slot] = Math.min(floor[r.slot] ?? Infinity, r.pick[1] * 0.8);
  }
  const places = new Map(); // describeSource key -> { kind, label, src, best: Map(slot -> item) }
  for (const [slot, have] of Object.entries(base)) {
    for (const [id, score] of slotPool(slot)) {
      if (!itemOk(id) || score <= have || score < floor[slot]) continue;
      const gain = have < score * 0.1 ? Infinity : (score - have) / have * 100;
      if (gain < UP) continue;
      for (const src of state.gear.items[id].sources || []) {
        if (!srcOk(src)) continue;
        const kind = SUGGEST.find(([, cats]) => catsOf(src).some((c) => cats.includes(c)))?.[0];
        if (!kind) continue;
        const d = describeSource(src);
        const p = places.get(d.key) || { key: d.key, kind, label: d.label, src, best: new Map() };
        const cur = p.best.get(slot);
        if (!cur || gain > cur.gain) p.best.set(slot, { label: SLOT_LABEL[slot], id, gain, d });
        places.set(d.key, p);
      }
    }
  }
  const value = (p) => [...p.best.values()].reduce((t, it) => t + Math.min(it.gain, 100), 0); // "new" counts as +100%
  return SUGGEST.map(([kind]) => [...places.values()].filter((p) => p.kind === kind)
      .sort((a, b) => b.best.size - a.best.size || value(b) - value(a))[0])
    .filter(Boolean)
    .map((p) => ({ ...p, items: [...p.best.values()].sort((a, b) => b.gain - a.gain) }));
}

function renderUpcoming() {
  const list = $("upcoming-list");
  list.replaceChildren();
  const events = [];
  const start = state.level;
  for (const slot of Object.keys(state.gear.slots)) {
    const points = slotPoints(slot);
    let prev = pointAt(slot, start, start >= 60 ? state.tier : 0)?.items[0]?.[0];
    for (const p of points) {
      if (pointKey(p) <= (start >= 60 && state.tier ? 60 + state.tier : start)) continue;
      const top = p.items[0]?.[0];
      if (top && top !== prev) { events.push({ key: pointKey(p), p, slot, iid: top }); prev = top; }
    }
  }
  events.sort((a, b) => a.key - b.key);
  for (const ev of events.slice(0, 6)) {
    const when = ev.p.tier ? tierShort(ev.p.tier) : `Lv ${ev.p.level}`;
    list.append(el("li", {}, el("button", { type: "button", class: "jump", title: "Show the gear for this level", onclick: () => jumpTo(ev.p) }, when),
      el("span", { class: "slot" }, SLOT_LABEL[ev.slot]), itemLink(ev.iid, state.gear.items[ev.iid])));
  }
  if (!events.length) list.append(el("li", { class: "muted" }, "No further upgrades in this list."));
}

function jumpTo(p) {
  state.level = p.tier ? 60 : p.level;
  state.tier = p.tier;
  render();
}


// Weapon types the class can use, from the weapons in the loaded gear JSON.
function weaponTypes() {
  const subs = new Set(Object.values(state.gear.items).filter((it) => it.class === 2).map((it) => String(it.subclass)));
  return [...subs].map((k) => [k, WEAPON_TYPES[k] || `Weapon type ${k}`]).sort((a, b) => a[1].localeCompare(b[1]));
}

function renderCharBar() {
  const cls = currentClass();
  const specSel = el("select", { id: "spec-select", "aria-label": "Spec" });
  for (const [key, name] of Object.entries(cls.specs)) specSel.append(el("option", { value: key, selected: key === state.spec }, name));
  specSel.addEventListener("change", async () => {
    state.spec = specSel.value;
    if (state.mode === "manual") { state.manual.spec = state.spec; store("manual", state.manual); }
    await refreshAll();
  });
  const kv = [el("dt", {}, "Spec"), el("dd", {}, specSel)];
  const types = weaponTypes();
  if (types.length > 1) {
    const wSel = el("select", { id: "weapon-select", "aria-label": "Weapon type", title: "Only show this weapon type in weapon slots, What to do next, Coming up and Item lookup" },
      el("option", { value: "" }, "Best (any)"), types.map(([k, name]) => el("option", { value: k, selected: k === state.wtype }, name)));
    wSel.addEventListener("change", () => { state.wtype = wSel.value; store("weapon", state.wtype); render(); });
    kv.push(el("dt", {}, "Weapon"), el("dd", {}, wSel));
  }
  let name, sub, faction, note;
  if (state.mode === "lookup") {
    const c = state.char.character;
    name = `${c.name}${c.surname ? ` ${c.surname}` : ""}`;
    sub = `Level ${c.level} ${c.race || ""} ${c.class_name || cls.name}`;
    faction = c.faction;
    if (c.ruleset) kv.push(el("dt", {}, "Ruleset"), el("dd", {}, c.ruleset));
    kv.push(el("dt", {}, "Region"), el("dd", {}, c.region.toUpperCase()));
    if (c.guild) kv.push(el("dt", {}, "Guild"), el("dd", {}, c.guild));
    note = state.char.spec_reason;
  } else {
    const race = state.meta.races[String(state.manual.raceId)];
    name = `${race.name} ${cls.name}`;
    sub = `Level ${state.manual.level}`;
    faction = race.faction;
    note = "Entered by hand. Your ticks are saved in this browser.";
  }
  $("char-bar").replaceChildren(el("h2", { class: "char-name" }, name),
    el("div", { class: "sub" }, el("span", {}, sub), el("span", { class: `faction f-${faction}` }, faction === "H" ? "Horde" : "Alliance")),
    el("dl", { class: "kv" }, kv), note ? el("p", { class: "sample" }, note) : null);
  $("top-name").textContent = name;
  $("top-sub").textContent = `${sub} · ${state.gear.spec_name}`;
}

// Button text = the label up to ":" ("Raid tier 1: Barrow Deeps, ..." -> "Raid tier 1"); the full label is the tooltip.
function tierShort(tier) {
  return tier === 0 || tier === "0" ? "Pre-raid" : String(state.meta.tiers[tier] ?? `Tier ${tier}`).split(":")[0];
}
function renderTierButtons() {
  const wrap = $("tier-buttons");
  wrap.innerHTML = "";
  const tiers = [0, ...Object.keys(state.meta.tiers).map(Number).filter((t) => t > 0).sort((a, b) => a - b)];
  for (const tier of tiers) {
    wrap.append(el("button", {
      type: "button", role: "radio", "data-tier": tier, title: state.meta.tiers[tier],
      onclick: () => { state.tier = tier; render(); },
    }, tierShort(tier)));
  }
}


function updateReportLink(rows) {
  const g = state.gear;
  const lines = rows.filter((r) => r.pick).flatMap((r) => {
    const [iid] = r.pick, reasons = reasonsOf(state.gear.items[iid]);
    return reasons.length ? [`- ${state.gear.items[iid].name || iid} (${iid}, ${SLOT_LABEL[r.slot]}): ${reasons.join("; ")}`] : [];
  });
  const title = `Wrong item: ${g.spec_name} ${g.class} (${g.faction}) level ${state.level}${state.tier ? ` tier ${state.tier}` : ""}`;
  const body = [
    `Class/spec: ${g.class} ${g.spec_name} (${g.faction === "A" ? "Alliance" : "Horde"})`,
    `Level: ${state.level}${state.tier ? `, tier ${state.tier}` : ""}`,
    ...(lines.length ? ["", "Items on this page flagged Uncertain (reasons from our data):", ...lines, ""] : []),
    "Slot and item that looks wrong:",
    "What should it be instead (and where did you see that)?",
    `Data built: ${state.meta.built}`,
  ].join("\n");
  $("report-link").href = `${REPORT_URL}?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

function updateUrl() {
  const p = new URLSearchParams();
  if (state.mode === "lookup" && state.char) {
    const c = state.char.character;
    p.set("region", c.region); p.set("name", c.name); p.set("surname", c.surname);
  } else if (state.manual) {
    p.set("race", state.manual.raceId); p.set("class", state.manual.classId); p.set("lvl", state.manual.level);
  }
  p.set("spec", state.spec); p.set("level", state.level);
  if (state.wtype) p.set("weapon", state.wtype);
  if (state.level >= 60 && state.tier) p.set("tier", state.tier);
  history.replaceState(null, "", `?${p}`);
}

// ---------------------------------------------------------------- flows
// ---------------------------------------------------------------- flows
// The level and character sections fold away once a character is shown (a phone gets the table, not the form).
function setOpen(btn, open) {
  $(btn).setAttribute("aria-expanded", String(open));
  $($(btn).getAttribute("aria-controls")).hidden = !open;
}
function showCharacter() {
  setOpen("lvl-btn", recall("open:lvl-btn", false));
  setOpen("chg-btn", false);
  $("side").classList.remove("open");
  $("menu").setAttribute("aria-expanded", "false");
}

async function refreshAll() {
  try {
    await loadGear();
  } catch (e) {
    showStatus(e.message, true);
    return false;
  }
  if (state.mode === "lookup") await rescoreEquipped();
  if (!weaponTypes().some(([k]) => k === state.wtype)) state.wtype = ""; // not usable by this class/spec
  renderCharBar();
  for (const id of ["char-bar", "hr-char", "lvl-disc", "slot-filters", "results"]) $(id).hidden = false;
  hideStatus();
  render();
  return true;
}

async function rescoreEquipped() {
  const c = state.char.character;
  const ids = Object.values(state.char.equipped).map((e) => e.item_id);
  try {
    const resp = await fetch("/api/score", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ class_id: c.class_id, spec: state.spec, level: state.level, race_id: c.race_id, item_ids: ids }),
    });
    if (resp.ok) state.scores = (await resp.json()).scores;
  } catch { /* keep the scores from the lookup */ }
}

async function lookup(event) {
  event?.preventDefault();
  const region = $("region").value;
  const name = $("character").value.trim();
  const surname = $("surname").value.trim();
  if (!/^\p{L}+$/u.test(name) || !/^\p{L}+$/u.test(surname)) { showStatus("Type the first name and the surname, letters only (no spaces or numbers).", true); return; }
  const btn = $("lookup-btn");
  btn.disabled = true;
  showStatus(`Looking up ${name} ${surname}…`);
  try {
    const resp = await fetch(`/api/character?${new URLSearchParams({ region, name, surname })}`);
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.detail || body.message || `Lookup failed (HTTP ${resp.status}).`);
    state.mode = "lookup";
    state.char = body;
    setScene(body.character.race_id);
    state.scores = {};
    const urlSpec = new URLSearchParams(location.search).get("spec");
    const cls = state.meta.classes[String(body.character.class_id)];
    state.spec = urlSpec && cls?.specs[urlSpec] ? urlSpec : body.spec || cls?.leveling_spec;
    state.level = Math.max(10, Math.min(60, body.character.level || 10));
    state.tier = 0;
    store("lookup", { region, name, surname });
    if (await refreshAll()) showCharacter();
  } catch (e) {
    showStatus(e.message, true);
  } finally {
    btn.disabled = false;
  }
}

async function manualSubmit(event) {
  event?.preventDefault();
  const level = Math.max(1, Math.min(60, Number($("m-level").value) || 1));
  state.mode = "manual";
  setScene(Number($("m-race").value));
  state.manual = { raceId: Number($("m-race").value), classId: Number($("m-class").value), spec: $("m-spec").value, level };
  state.spec = state.manual.spec;
  state.level = Math.max(10, level);
  state.tier = 0;
  store("manual", state.manual);
  if (await refreshAll()) showCharacter();
}

// ---------------------------------------------------------------- manual form
function fillManualForm(saved) {
  const raceSel = $("m-race");
  raceSel.innerHTML = "";
  for (const [rid, r] of Object.entries(state.meta.races)) {
    raceSel.append(el("option", { value: rid }, `${r.name} (${r.faction === "A" ? "Alliance" : "Horde"})`));
  }
  if (saved?.raceId) raceSel.value = String(saved.raceId);
  const fillClasses = () => {
    const race = state.meta.races[raceSel.value];
    const clsSel = $("m-class");
    const prev = clsSel.value || String(saved?.classId || "");
    clsSel.innerHTML = "";
    for (const cid of race.classes || Object.keys(state.meta.classes)) clsSel.append(el("option", { value: cid }, state.meta.classes[String(cid)].name));
    if ([...clsSel.options].some((o) => o.value === prev)) clsSel.value = prev;
    fillSpecs();
  };
  const fillSpecs = () => {
    const cls = state.meta.classes[$("m-class").value];
    const specSel = $("m-spec");
    const prev = specSel.value || saved?.spec;
    specSel.innerHTML = "";
    for (const [key, name] of Object.entries(cls.specs)) {
      specSel.append(el("option", { value: key }, `${name}${key === cls.leveling_spec ? " — usual for leveling" : ""}`));
    }
    specSel.value = cls.specs[prev] ? prev : cls.leveling_spec;
  };
  raceSel.onchange = () => { fillClasses(); setScene(Number(raceSel.value)); };
  $("m-class").onchange = fillSpecs;
  fillClasses();
  if (saved?.level) $("m-level").value = saved.level;
}

function selectTab(mode) {
  const lookupOn = mode === "lookup";
  $("tab-lookup").setAttribute("aria-selected", String(lookupOn));
  $("tab-manual").setAttribute("aria-selected", String(!lookupOn));
  $("panel-lookup").hidden = !lookupOn;
  $("panel-manual").hidden = lookupOn;
  $("input-hint").textContent = lookupOn
    ? "Forever characters have a first name and a surname, and no realm. No login needed."
    : "No character needed: pick race, class, spec and level, then tick the items you have.";
  store("tab", mode);
  if (lookupOn) setScene(state.mode === "lookup" ? state.char?.character.race_id : null);
  else setScene(Number($("m-race").value));
}


// Source picker, sort, slot filter, folding sections, mobile menu.
function setupControls() {
  for (const b of ["lvl-btn", "chg-btn", "set-btn"]) $(b).addEventListener("click", () => {
    const open = $(b).getAttribute("aria-expanded") !== "true";
    setOpen(b, open);
    if (b !== "chg-btn") store(`open:${b}`, open);
  });
  for (const b of ["lvl-btn", "set-btn"]) { const o = recall(`open:${b}`); if (o != null) setOpen(b, o); }
  $("menu").addEventListener("click", (e) => { const o = $("side").classList.toggle("open"); e.currentTarget.setAttribute("aria-expanded", String(o)); });
  document.querySelectorAll("#slot-filters button").forEach((b) => b.addEventListener("click", () => {
    ui.slot = b.dataset.f;
    store("slot", ui.slot);
    document.querySelectorAll("#slot-filters button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    document.querySelectorAll("#rows .row").forEach((li) => { li.hidden = ui.slot !== "all" && li.dataset.g !== ui.slot; });
  }));
  const boxes = [...document.querySelectorAll("#srcpick input")];
  const showSrc = () => {
    boxes.forEach((x) => { x.checked = x.value === "all" ? !ui.src.size : ui.src.has(x.value); });
    $("src-sum").textContent = !ui.src.size ? "All sources" : ui.src.size <= 2 ? [...ui.src].map((c) => CATS[c]).join(", ") : `${ui.src.size} sources`;
  };
  boxes.forEach((b) => b.addEventListener("change", () => {
    ui.src = b.value === "all" ? new Set() : new Set(boxes.filter((x) => x.value !== "all" && x.checked).map((x) => x.value));
    store("src", [...ui.src]);
    showSrc();
    render();
  }));
  showSrc();
  document.querySelectorAll("#slot-filters button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.f === ui.slot)));
  $("sort").value = ui.sort;
  const pick = $("srcpick");
  document.addEventListener("click", (e) => { if (pick.open && !pick.contains(e.target)) pick.open = false; });
  pick.addEventListener("keydown", (e) => { if (e.key === "Escape") { pick.open = false; pick.querySelector("summary").focus(); } });
  $("sort").addEventListener("change", (e) => { ui.sort = e.target.value; store("sort", ui.sort); render(); });
  for (const k of ["boe", "bop", "epic"]) {
    const box = $(`${k}-ok`);
    box.checked = ui[k];
    box.addEventListener("change", () => { ui[k] = box.checked; store(k, box.checked); render(); });
  }
}

const itemLookup = setupLookup({ state, $, el, itemLink, slotPoints, pointAt, SLOT_LABEL, describeSource, pinBtn, reasonsOf, uncBadge, extrasOf, wornScoreFor, tierShort, fmtGain, refreshTooltips });

// ---------------------------------------------------------------- init
async function init() {
  initSettings();
  try {
    const resp = await fetch(`${DATA}/meta.json`);
    state.meta = await resp.json();
  } catch {
    showStatus("Could not load the gear data. Reload the page.", true);
    return;
  }
  $("data-date").textContent = `Data built ${state.meta.built}`;
  setupControls();
  renderTierButtons();
  $("tab-lookup").addEventListener("click", () => selectTab("lookup"));
  $("tab-manual").addEventListener("click", () => selectTab("manual"));
  $("panel-lookup").addEventListener("submit", lookup);
  $("panel-manual").addEventListener("submit", manualSubmit);

  let sliderTimer = null;
  $("level-slider").addEventListener("input", (e) => {
    state.level = Number(e.target.value);
    if (state.level < 60) state.tier = 0;
    render();
    if (state.mode === "lookup") {
      clearTimeout(sliderTimer);
      sliderTimer = setTimeout(async () => { await rescoreEquipped(); render(); }, 300);
    }
  });

  const params = new URLSearchParams(location.search);
  state.wtype = params.get("weapon") ?? recall("weapon", "");
  const savedManual = recall("manual");
  fillManualForm(params.get("class") ? {
    raceId: Number(params.get("race")), classId: Number(params.get("class")),
    spec: params.get("spec"), level: Number(params.get("lvl") || params.get("level") || 20),
  } : savedManual);

  const savedLookup = recall("lookup");
  const region = params.get("region") || savedLookup?.region || "eu";
  $("region").value = region;
  const fromUrl = params.get("name") && params.get("surname");
  $("character").value = (fromUrl ? params.get("name") : savedLookup?.name) || "";
  $("surname").value = (fromUrl ? params.get("surname") : savedLookup?.surname) || "";

  if (params.get("class")) {
    selectTab("manual");
    await manualSubmit();
    applyUrlLevel(params);
  } else if (fromUrl) {
    selectTab("lookup");
    await lookup();
    applyUrlLevel(params);
  } else {
    selectTab(recall("tab", "lookup"));
    $("side").classList.add("open"); // nothing to show yet: on a phone the form is the page
  }
}

function applyUrlLevel(params) {
  if (!state.gear) return;
  const lvl = Number(params.get("level"));
  if (lvl >= 10 && lvl <= 60) state.level = lvl;
  const tier = Number(params.get("tier"));
  if (state.level >= 60 && (tier === 0 || state.meta.tiers[tier])) state.tier = tier;
  render();
}

init();
