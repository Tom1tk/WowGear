// WowGear Classic — per-level best-in-slot planner for WoW Classic Era.
// Gear lists are static JSON (frontend/data/gear, built by scripts/data/build_gear.py);
// the API is only used for the Blizzard character lookup and item scores.

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
const ARMOR_ORDER = ["head", "neck", "shoulders", "back", "chest", "wrist", "hands", "waist", "legs", "feet"];
// Race id -> background scene (the race's home area) and colour theme.
const RACE_SCENE = { 1: "human", 3: "dwarf", 4: "night-elf", 7: "gnome", 2: "orc", 5: "undead", 6: "tauren", 8: "troll" };
const TIER_SHORT = { 0: "Pre-raid", 1: "MC / Ony", 2: "BWL / ZG", 3: "AQ", 4: "Naxx" };

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
let sceneKey = "default";
let sceneToken = 0;

// Cross-fade the background to a race's home area and switch the colour theme.
function setScene(raceId) {
  const key = RACE_SCENE[raceId] || "default";
  if (key === sceneKey) return;
  sceneKey = key;
  const token = ++sceneToken;
  const img = new Image();
  img.onload = () => {
    if (token !== sceneToken) return; // a newer choice won
    const [a, b] = [$("scene-a"), $("scene-b")];
    const [shown, hidden] = a.classList.contains("on") ? [a, b] : [b, a];
    hidden.style.backgroundImage = `url('${img.src}')`;
    hidden.classList.add("on");
    shown.classList.remove("on");
  };
  img.src = `/static/bg/${key}.jpg`;
  if (key === "default") delete document.documentElement.dataset.race;
  else document.documentElement.dataset.race = key;
}

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
    class: `item-link q-${q}`, href: `https://www.wowhead.com/classic/item=${id}`,
    target: "_blank", rel: "noopener", "data-wh-icon-size": "small",
  }, info?.name || `Item ${id}`);
}

function refreshTooltips() {
  try { window.$WowheadPower?.refreshLinks(); } catch { /* tooltips are optional */ }
}

function instanceName(key) {
  const inst = state.meta.instances[key];
  return inst ? inst.name : key;
}
function instanceLevels(key) {
  const inst = state.meta.instances[key];
  if (!inst || inst.type.startsWith("raid") || inst.type === "world_boss") return "";
  return ` (level ${inst.levels[0]}–${inst.levels[1]})`;
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

// ---------------------------------------------------------------- sources
function describeSource(src) {
  const inst = src.instance;
  const chance = src.chance != null ? ` — ${src.chance < 1 ? src.chance.toFixed(1) : Math.round(src.chance)}% drop chance` : "";
  switch (src.type) {
    case "drop": {
      const rank = src.rank && src.rank !== "normal" ? ` (${src.rank})` : "";
      if (inst) return { key: `inst:${inst}`, label: `Run ${instanceName(inst)}${instanceLevels(inst)}`, text: `Dropped by ${src.name}${rank}${chance}` };
      return { key: `npc:${src.id}`, label: `Kill ${src.name}${src.zone ? ` in ${src.zone}` : ""}`, text: `Dropped by ${src.name}${rank}${src.level?.[0] ? `, level ${src.level[0]}` : ""}${chance}` };
    }
    case "boss":
      return { key: `inst:${inst}`, label: `Run ${instanceName(inst)}${instanceLevels(inst)}`, text: `Dropped by ${src.name}` };
    case "instance_trash":
      return { key: `inst:${inst}`, label: `Run ${instanceName(inst)}${instanceLevels(inst)}`, text: `Random drop from the normal monsters (trash)${chance}` };
    case "object":
      if (inst) return { key: `inst:${inst}`, label: `Run ${instanceName(inst)}${instanceLevels(inst)}`, text: `Found in ${src.name || "a chest"}${chance}` };
      return { key: `obj:${src.id}`, label: `Open ${src.name || "a chest"}${src.zone ? ` in ${src.zone}` : ""}`, text: `Found in ${src.name || "a chest"}${chance}` };
    case "quest": {
      const where = src.zone ? ` in ${src.zone}` : "";
      const from = src.start_npc ? ` from ${src.start_npc}` : "";
      const lvl = src.level ? ` (level ${src.level})` : "";
      const label = inst && state.meta.instances[inst]?.tier ? `Quest: ${src.name} — needs ${instanceName(inst)}` : `Quest: ${src.name}${lvl}`;
      return { key: `quest:${src.id}`, label, text: `Quest reward${where}${from}. Can be picked up at level ${src.min_level || 1}.` };
    }
    case "vendor": {
      const rep = src.reputation ? ` Needs ${src.reputation.faction} reputation.` : "";
      return { key: `vendor:${src.id}`, label: `Buy from ${src.name}${src.zone ? ` (${src.zone})` : ""}`, text: `Sold by ${src.name}${src.title ? ` <${src.title}>` : ""}.${rep}` };
    }
    case "craft": {
      const recipe = src.recipe ? ` Recipe: ${src.recipe.name}${src.recipe.from?.length ? ` (${src.recipe.from.join(" / ")})` : ""}.` : " Recipe from the profession trainer.";
      const raid = inst ? ` Needs materials from ${instanceName(inst)}.` : "";
      return { key: `craft:${src.id}`, label: `${src.id} (crafted)`, text: `Crafted with ${src.id}${src.skill ? ` (skill ${src.skill})` : ""}.${recipe}${raid}` };
    }
    case "world_drop":
      return { key: "ah", label: "Auction House / world drops", text: "Random drop from many monsters. It is Bind on Equip, so you can often buy it on the Auction House." };
    case "container":
      return { key: `cont:${src.id}`, label: `Open ${src.name || "a container"}`, text: `Found in ${src.name || "a container"}${chance}` };
    default:
      return { key: src.type, label: src.type, text: src.type };
  }
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

function pointAt(slot, level = state.level, tier = state.tier) {
  const points = state.gear.slots[slot] || [];
  const target = level >= 60 && tier > 0 ? 60 + tier : Math.min(level, 60);
  let found = null;
  for (const p of points) if (pointKey(p) <= target) found = p;
  return found;
}

function firstSeen(slot, iid) {
  for (const p of state.gear.slots[slot] || []) {
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

// Displayed rows: [{slot, index, picks: [[id, score], ...]}]
function displayRows() {
  const rows = [];
  for (const slot of ARMOR_ORDER) if (state.gear.slots[slot]) rows.push({ slot, index: 0 });
  for (const slot of ["ring", "trinket"]) {
    if (state.gear.slots[slot]) { rows.push({ slot, index: 0 }); rows.push({ slot, index: 1 }); }
  }
  const plan = weaponPlan();
  for (const slot of plan.use) rows.push({ slot, index: 0 });
  for (const slot of ["ranged", "relic"]) if (state.gear.slots[slot]) rows.push({ slot, index: 0 });
  for (const row of rows) {
    const items = pointAt(row.slot)?.items || [];
    if (row.slot === "ring" || row.slot === "trinket") {
      // pick index 0/1 = the two best; the rest are alternatives for both
      row.pick = items[row.index] || null;
      row.alts = items.slice(2);
    } else {
      row.pick = items[0] || null;
      row.alts = items.slice(1);
    }
  }
  return { rows, plan };
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

function rowStatus(row) {
  const pick = row.pick;
  if (!pick) return { cls: "none", text: "No item", gain: 0 };
  const [iid, best] = pick;
  if (state.mode === "manual") {
    const owned = ownedSet();
    if (owned.has(iid)) return { cls: "bis", text: "✓ You have it", gain: 0 };
    const alt = row.alts.find(([id]) => owned.has(id));
    if (alt) return { cls: "good", text: "Good (you have an alternative)", gain: best - alt[1] };
    return { cls: "need", text: "Get this", gain: best };
  }
  const eq = equippedFor(row);
  if (!eq) return { cls: "empty", text: "Empty slot", gain: best };
  if (String(eq.item_id) === iid) return { cls: "bis", text: "✓ Best in slot", gain: 0 };
  if (row.alts.some(([id]) => id === String(eq.item_id)) ||
      ((row.slot === "ring" || row.slot === "trinket") && pointAt(row.slot)?.items.slice(0, 2).some(([id]) => id === String(eq.item_id)))) {
    return { cls: "good", text: "Good — on the list", gain: 0 };
  }
  const have = scoreOf(eq);
  if (have == null) return { cls: "unknown", text: "Can't score your item", gain: 0, note: "Random-stat items (e.g. “… of the Monkey”) and some special items have no fixed score. Compare the stats yourself." };
  const gain = Math.round((best - have) * 10) / 10;
  if (gain <= 0) return { cls: "ahead", text: "Yours is as good or better", gain: 0 };
  if (have >= 0.9 * best) return { cls: "close", text: `Close (+${gain})`, gain };
  return { cls: "need", text: `Upgrade +${gain}`, gain };
}

// ---------------------------------------------------------------- render
function render() {
  if (!state.gear) return;
  const lvl = state.level;
  $("level-out").textContent = String(lvl);
  $("level-slider").value = String(lvl);
  $("tier-row").hidden = lvl < 60;
  document.querySelectorAll("#tier-buttons button").forEach((b) => {
    b.setAttribute("aria-checked", String(Number(b.dataset.tier) === state.tier));
  });
  const charLvl = characterLevel();
  $("level-note").textContent = lvl === charLvl ? "Your level" :
    lvl > charLvl ? `${lvl - charLvl} level${lvl - charLvl > 1 ? "s" : ""} ahead of you` : `${charLvl - lvl} below your level`;
  const g = state.gear;
  $("gear-title").textContent = lvl >= 60 && state.tier > 0 ? `Best gear — ${state.meta.tiers[state.tier]}` : `Best gear at level ${lvl}`;
  $("gear-sub").textContent = `${g.spec_name} ${g.class} · ${g.faction === "A" ? "Alliance" : "Horde"}`;
  renderSlots();
  renderTodo();
  renderUpcoming();
  updateReportLink();
  updateUrl();
  refreshTooltips();
}

function renderSlots() {
  const list = $("slot-list");
  list.innerHTML = "";
  const { rows, plan } = displayRows();
  const note = $("weapon-note");
  if (plan.alt.length && state.gear.slots[plan.alt[0]]) {
    const altItems = plan.alt.map((s) => pointAt(s)?.items[0]).filter(Boolean);
    note.hidden = !altItems.length;
    note.replaceChildren(
      plan.use[0] === "two_hand" ? "A two-handed weapon scores best here. Other option: " : "One-hand + off-hand scores best here. Other option: ",
      ...altItems.flatMap(([id, s], i) => [i ? " + " : "", itemLink(id, state.gear.items[id]), ` (${s})`]),
    );
  } else note.hidden = true;

  for (const row of rows) {
    const label = row.slot === "ring" || row.slot === "trinket" ? `${SLOT_LABEL[row.slot]} ${row.index + 1}` : SLOT_LABEL[row.slot];
    const status = rowStatus(row);
    const li = el("li", { class: `slot-row st-${status.cls}` });
    li.append(el("div", { class: "slot-name" }, label));
    const main = el("div", { class: "slot-main" });
    if (!row.pick) {
      main.append(el("span", { class: "muted" }, "No known item for this slot at this level."));
    } else {
      const [iid, score] = row.pick;
      const info = state.gear.items[iid];
      const seen = firstSeen(row.slot, iid);
      main.append(el("div", { class: "pick" },
        itemLink(iid, info),
        el("span", { class: "score", title: "Score for your spec (compare within a slot)" }, String(score)),
        seen && seen.tier === 0 && seen.level > 10 ? el("span", { class: "badge" }, `from lvl ${seen.level}`) : null,
        info.binding === "ON_ACQUIRE" ? el("span", { class: "badge badge-bop", title: "Binds when picked up" }, "BoP") : null,
        info.special ? el("span", { class: "badge badge-fx", title: info.special }, "special effect") : null,
      ));
      const srcs = info.sources || [];
      if (srcs.length) {
        const d = describeSource(srcs[0]);
        main.append(el("div", { class: "source" }, d.label === d.text ? d.text : `${d.label}. ${d.text}`,
          srcs.length > 1 ? el("span", { class: "muted" }, ` (+${srcs.length - 1} more source${srcs.length > 2 ? "s" : ""})`) : null));
      }
      const eq = equippedFor(row);
      if (state.mode === "lookup") {
        main.append(el("div", { class: "equipped" }, "You: ",
          eq ? itemLink(eq.item_id, { name: eq.name, quality: QUALITY_BY_TYPE[eq.quality] }) : el("span", { class: "muted" }, "nothing equipped"),
          eq && scoreOf(eq) != null ? el("span", { class: "score" }, String(scoreOf(eq))) : null));
      } else {
        const owned = ownedSet().has(iid);
        main.append(el("label", { class: "own" },
          el("input", { type: "checkbox", checked: owned, onchange: (e) => toggleOwned(iid, e.target.checked) }),
          " I have this"));
      }
      if (row.alts.length) {
        const details = el("details", { class: "alts" }, el("summary", {}, `${row.alts.length} alternative${row.alts.length > 1 ? "s" : ""}`));
        const ul = el("ul");
        for (const [aid, ascore] of row.alts) {
          const ainfo = state.gear.items[aid];
          const d = ainfo.sources?.[0] ? describeSource(ainfo.sources[0]) : null;
          const altLi = el("li", {}, itemLink(aid, ainfo), el("span", { class: "score" }, String(ascore)),
            d ? el("span", { class: "muted" }, ` — ${d.label}`) : null);
          if (state.mode === "manual") {
            altLi.append(el("label", { class: "own own-small" },
              el("input", { type: "checkbox", checked: ownedSet().has(aid), onchange: (e) => toggleOwned(aid, e.target.checked) }), " have"));
          }
          ul.append(altLi);
        }
        details.append(ul);
        main.append(details);
      }
      if (status.note) main.append(el("div", { class: "note" }, status.note));
    }
    li.append(main);
    li.append(el("div", { class: "slot-status" }, status.text));
    list.append(li);
  }
}

function renderTodo() {
  const list = $("todo-list");
  list.innerHTML = "";
  const charLvl = characterLevel();
  const viewing = state.level;
  $("todo-sub").textContent = viewing === charLvl
    ? "Grouped by where to go. The biggest gains are first."
    : `For the gear at level ${viewing}${viewing > charLvl ? " (plan ahead)" : ""}.`;
  const groups = new Map();
  const { rows } = displayRows();
  for (const row of rows) {
    if (!row.pick) continue;
    const st = rowStatus(row);
    if (!["need", "empty", "close"].includes(st.cls)) continue;
    const [iid] = row.pick;
    const info = state.gear.items[iid];
    const src = info.sources?.[0];
    if (!src) continue;
    const d = describeSource(src);
    const g = groups.get(d.key) || { label: d.label, gain: 0, items: [] };
    g.gain += st.gain;
    g.items.push({ iid, info, text: d.text, slot: row.slot });
    groups.set(d.key, g);
  }
  const sorted = [...groups.values()].sort((a, b) => b.gain - a.gain).slice(0, 8);
  if (!sorted.length) {
    list.append(el("li", { class: "todo-done" }, state.mode === "manual"
      ? "Tick the items you have. Then this list shows where to go for the rest."
      : "Nothing to do at this level — your gear matches the list. Try the next levels on the slider."));
    return;
  }
  for (const g of sorted) {
    const ul = el("ul");
    for (const it of g.items) ul.append(el("li", {}, itemLink(it.iid, it.info), el("span", { class: "muted" }, ` — ${SLOT_LABEL[it.slot]}. ${it.text}`)));
    list.append(el("li", {}, el("div", { class: "todo-head" }, el("strong", {}, g.label),
      el("span", { class: "gain", title: "Total score gain" }, `+${Math.round(g.gain)}`)), ul));
  }
}

function renderUpcoming() {
  const list = $("upcoming-list");
  list.innerHTML = "";
  const events = [];
  const start = state.level;
  for (const [slot, points] of Object.entries(state.gear.slots)) {
    let prev = pointAt(slot, start, start >= 60 ? state.tier : 0)?.items[0]?.[0];
    for (const p of points) {
      if (pointKey(p) <= (start >= 60 && state.tier ? 60 + state.tier : start)) continue;
      const top = p.items[0]?.[0];
      if (top && top !== prev) {
        events.push({ key: pointKey(p), p, slot, iid: top });
        prev = top;
      }
    }
  }
  events.sort((a, b) => a.key - b.key);
  for (const ev of events.slice(0, 10)) {
    const when = ev.p.tier ? TIER_SHORT[ev.p.tier] : `Level ${ev.p.level}`;
    list.append(el("li", {},
      el("button", { type: "button", class: "jump", onclick: () => jumpTo(ev.p) }, when),
      el("span", {}, ` ${SLOT_LABEL[ev.slot]}: `), itemLink(ev.iid, state.gear.items[ev.iid])));
  }
  if (!events.length) list.append(el("li", { class: "muted" }, "No further upgrades in this list."));
}

function jumpTo(p) {
  state.level = p.tier ? 60 : p.level;
  state.tier = p.tier;
  render();
}

function renderCharBar() {
  const bar = $("char-bar");
  bar.innerHTML = "";
  const cls = currentClass();
  const specSel = el("select", { id: "spec-select", "aria-label": "Spec" });
  for (const [key, name] of Object.entries(cls.specs)) {
    specSel.append(el("option", { value: key, selected: key === state.spec }, name));
  }
  specSel.addEventListener("change", async () => {
    state.spec = specSel.value;
    if (state.mode === "manual") { state.manual.spec = state.spec; store("manual", state.manual); }
    await refreshAll();
  });
  if (state.mode === "lookup") {
    const c = state.char.character;
    bar.append(
      c.avatar_url ? el("img", { class: "avatar", src: c.avatar_url, alt: "" }) : el("div", { class: "avatar avatar-empty" }),
      el("div", { class: "char-info" },
        el("div", { class: "char-name" }, c.name, el("span", { class: `faction f-${c.faction}` }, c.faction === "H" ? "Horde" : "Alliance")),
        el("div", { class: "char-meta" }, `Level ${c.level} ${c.race || ""} ${c.class_name || ""} · ${c.realm} (${c.region.toUpperCase()})${c.guild ? ` · <${c.guild}>` : ""}`),
        el("div", { class: "char-spec" }, el("label", { for: "spec-select" }, "Spec: "), specSel,
          el("span", { class: "muted" }, ` ${state.char.spec_reason || ""}`))),
    );
  } else {
    const race = state.meta.races[String(state.manual.raceId)];
    bar.append(
      el("div", { class: "avatar avatar-empty", "aria-hidden": "true" }, "?"),
      el("div", { class: "char-info" },
        el("div", { class: "char-name" }, `${race.name} ${cls.name}`, el("span", { class: `faction f-${race.faction}` }, race.faction === "H" ? "Horde" : "Alliance")),
        el("div", { class: "char-meta" }, `Level ${state.manual.level} · entered by hand · your ticks are saved in this browser`),
        el("div", { class: "char-spec" }, el("label", { for: "spec-select" }, "Spec: "), specSel)),
    );
  }
}

function renderTierButtons() {
  const wrap = $("tier-buttons");
  wrap.innerHTML = "";
  for (const [tier, label] of Object.entries(TIER_SHORT)) {
    wrap.append(el("button", {
      type: "button", role: "radio", "data-tier": tier, title: state.meta.tiers[tier],
      onclick: () => { state.tier = Number(tier); render(); },
    }, label));
  }
}

function updateReportLink() {
  const g = state.gear;
  const title = `Wrong item: ${g.spec_name} ${g.class} (${g.faction}) level ${state.level}${state.tier ? ` tier ${state.tier}` : ""}`;
  const body = [
    `Class/spec: ${g.class} ${g.spec_name} (${g.faction === "A" ? "Alliance" : "Horde"})`,
    `Level: ${state.level}${state.tier ? `, tier ${state.tier}` : ""}`,
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
    p.set("region", c.region); p.set("realm", $("realm").value || c.realm); p.set("name", c.name);
  } else if (state.manual) {
    p.set("race", state.manual.raceId); p.set("class", state.manual.classId); p.set("lvl", state.manual.level);
  }
  p.set("spec", state.spec); p.set("level", state.level);
  if (state.level >= 60 && state.tier) p.set("tier", state.tier);
  history.replaceState(null, "", `?${p}`);
}

// ---------------------------------------------------------------- flows
async function refreshAll() {
  try {
    await loadGear();
  } catch (e) {
    showStatus(e.message, true);
    return;
  }
  if (state.mode === "lookup") await rescoreEquipped();
  renderCharBar();
  $("results").hidden = false;
  hideStatus();
  render();
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
  const realm = $("realm").value.trim();
  const name = $("character").value.trim();
  if (!realm || !name) { showStatus("Choose a realm and type a character name.", true); return; }
  const btn = $("lookup-btn");
  btn.disabled = true;
  showStatus(`Looking up ${name} on ${$("realm-label").textContent}…`);
  try {
    const resp = await fetch(`/api/character?${new URLSearchParams({ region, realm, name })}`);
    const body = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(body.detail || `Lookup failed (HTTP ${resp.status}).`);
    state.mode = "lookup";
    state.char = body;
    setScene(body.character.race_id);
    state.scores = {};
    const urlSpec = new URLSearchParams(location.search).get("spec");
    const cls = state.meta.classes[String(body.character.class_id)];
    state.spec = urlSpec && cls?.specs[urlSpec] ? urlSpec : body.spec || cls?.leveling_spec;
    state.level = Math.max(10, Math.min(60, body.character.level || 10));
    state.tier = 0;
    store("lookup", { region, realm, name });
    await refreshAll();
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
  await refreshAll();
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
    for (const cid of race.classes) clsSel.append(el("option", { value: cid }, state.meta.classes[String(cid)].name));
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
    ? "Classic Era realms only. No login needed."
    : "No character needed: pick race, class, spec and level, then tick the items you have.";
  store("tab", mode);
  if (lookupOn) setScene(state.mode === "lookup" ? state.char?.character.race_id : null);
  else setScene(Number($("m-race").value));
}

// ---------------------------------------------------------------- realm combobox
const realmState = { items: [], filtered: [], active: -1, ready: false, fallback: false };

function selectRealm(slug, name) {
  $("realm").value = slug;
  $("realm-label").textContent = name || slug;
  store(`realm:${$("region").value}`, slug);
}

function renderRealmOptions(items) {
  const list = $("realm-list");
  list.innerHTML = "";
  realmState.filtered = items;
  realmState.active = -1;
  $("realm-empty").hidden = items.length > 0;
  for (const realm of items) {
    const selected = realm.slug === $("realm").value;
    const li = el("li", { class: `combo-option${selected ? " selected" : ""}`, role: "option", "aria-selected": String(selected) }, realm.name);
    li.addEventListener("mousedown", (e) => { e.preventDefault(); selectRealm(realm.slug, realm.name); closeRealmCombo(); });
    list.append(li);
  }
}

function openRealmCombo() {
  if (!realmState.ready || realmState.fallback) return;
  $("realm-popover").hidden = false;
  $("realm-trigger").setAttribute("aria-expanded", "true");
  $("realm-search").value = "";
  renderRealmOptions(realmState.items);
  $("realm-search").focus();
}

function closeRealmCombo() {
  $("realm-popover").hidden = true;
  $("realm-trigger").setAttribute("aria-expanded", "false");
}

function setActive(index) {
  const n = realmState.filtered.length;
  if (!n) return;
  realmState.active = (index + n) % n;
  $("realm-list").querySelectorAll(".combo-option").forEach((li, i) => {
    li.toggleAttribute("data-active", i === realmState.active);
    if (i === realmState.active) li.scrollIntoView({ block: "nearest" });
  });
}

async function loadRealms(region) {
  const cacheKey = `realms:${region}`;
  const cached = recall(cacheKey);
  const apply = (realms) => {
    realmState.items = realms;
    realmState.ready = true;
    $("realm-trigger").disabled = false;
    const saved = recall(`realm:${region}`);
    const pick = realms.find((r) => r.slug === ($("realm").value || saved)) || null;
    if (pick) selectRealm(pick.slug, pick.name);
    else { $("realm").value = ""; $("realm-label").textContent = "Choose a realm"; }
  };
  if (cached && Date.now() - cached.ts < 7 * 864e5) apply(cached.realms);
  try {
    const resp = await fetch(`/api/realms?region=${encodeURIComponent(region)}`);
    if (!resp.ok) throw new Error();
    const data = await resp.json();
    apply(data.realms);
    store(cacheKey, { ts: Date.now(), realms: data.realms });
  } catch {
    if (!realmState.ready) {
      realmState.fallback = true;
      $("realm-trigger").hidden = true;
      $("realm-fallback").hidden = false;
    }
  }
}

function wireRealmCombo() {
  $("realm-trigger").addEventListener("click", () => ($("realm-popover").hidden ? openRealmCombo() : closeRealmCombo()));
  $("realm-search").addEventListener("input", () => {
    const q = $("realm-search").value.trim().toLowerCase();
    renderRealmOptions(q ? realmState.items.filter((r) => r.name.toLowerCase().includes(q) || r.slug.includes(q)) : realmState.items);
  });
  $("realm-search").addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setActive(realmState.active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(realmState.active - 1); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const item = realmState.filtered[Math.max(0, realmState.active)];
      if (item) { selectRealm(item.slug, item.name); closeRealmCombo(); $("character").focus(); }
    } else if (e.key === "Escape") { closeRealmCombo(); $("realm-trigger").focus(); }
  });
  $("realm-fallback").addEventListener("input", () => {
    $("realm").value = $("realm-fallback").value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-");
  });
  document.addEventListener("click", (e) => {
    if (!$("realm-popover").hidden && !$("realm-combo").contains(e.target)) closeRealmCombo();
  });
  $("region").addEventListener("change", () => {
    $("realm").value = "";
    $("realm-label").textContent = "Loading realms…";
    $("realm-trigger").disabled = true;
    realmState.ready = false;
    loadRealms($("region").value);
  });
}

// ---------------------------------------------------------------- init
async function init() {
  try {
    const resp = await fetch(`${DATA}/meta.json`);
    state.meta = await resp.json();
  } catch {
    showStatus("Could not load the gear data. Reload the page.", true);
    return;
  }
  $("data-date").textContent = `Data built ${state.meta.built}`;
  renderTierButtons();
  wireRealmCombo();
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
  const savedManual = recall("manual");
  fillManualForm(params.get("class") ? {
    raceId: Number(params.get("race")), classId: Number(params.get("class")),
    spec: params.get("spec"), level: Number(params.get("lvl") || params.get("level") || 20),
  } : savedManual);

  const savedLookup = recall("lookup");
  const region = params.get("region") || savedLookup?.region || "eu";
  $("region").value = region;
  if (params.get("realm")) store(`realm:${region}`, params.get("realm"));
  if (params.get("name") || savedLookup?.name) $("character").value = params.get("name") || savedLookup.name;
  await loadRealms(region);

  if (params.get("class")) {
    selectTab("manual");
    await manualSubmit();
    applyUrlLevel(params);
  } else if (params.get("name") && $("realm").value) {
    selectTab("lookup");
    await lookup();
    applyUrlLevel(params);
  } else {
    selectTab(recall("tab", "lookup"));
  }
}

function applyUrlLevel(params) {
  if (!state.gear) return;
  const lvl = Number(params.get("level"));
  if (lvl >= 10 && lvl <= 60) state.level = lvl;
  const tier = Number(params.get("tier"));
  if (state.level >= 60 && tier >= 0 && tier <= 4) state.tier = tier;
  render();
}

init();
