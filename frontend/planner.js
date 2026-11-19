// Gear planner: the player picks a wanted item per slot; the route orders where to go for them.
// Plan is kept per class/spec/faction in this browser: { "Head": itemId, "Ring 2": itemId, ... } (row labels).
const MAX_HITS = 10;
// Zones on Kalimdor; any other known zone counts as Eastern Kingdoms. Crossing the sea is the big cost.
const KALIMDOR = new Set(["Ashenvale", "Azshara", "Darkshore", "Darnassus", "Desolace", "Durotar", "Dustwallow Marsh", "Felwood",
  "Feralas", "Moonglade", "Mulgore", "Orgrimmar", "Silithus", "Stonetalon Mountains", "Tanaris", "Teldrassil", "The Barrens",
  "Thousand Needles", "Thunder Bluff", "Un'Goro Crater", "Winterspring"]);
// ponytail: Forever-only zones (Riverglades, Zephras Isle) have no continent here, so they get the "unknown" cost.
const continent = (zone) => (!zone ? null : KALIMDOR.has(zone) ? "K" : /Riverglades|Zephras/.test(zone) ? null : "E");
const ANYWHERE = /^(craft:|ah$|rep:|vendor$)/; // crafting, the Auction House, rep quartermasters: no trip planned

export function setupPlanner(ctx) {
  const { state, $, el } = ctx;
  const list = el("ul", { id: "plan-list", role: "listbox", class: "plan-list", "aria-label": "Matching items", hidden: true });
  let open = null, hits = [], active = -1; // open: { input, row }

  const key = () => `plan:${state.gearKey}`;
  const plan = () => ctx.recall(key(), {});
  function setPlan(label, id) {
    const p = { ...plan() };
    if (id) p[label] = id; else delete p[label];
    ctx.store(key(), p);
    ctx.render();
  }

  // Planner rows: every slot this spec has, rings and trinkets twice, all weapon slots.
  function rows() {
    return Object.keys(ctx.SLOT_LABEL).filter((s) => state.gear.slots[s]).flatMap((slot) => {
      const pair = slot === "ring" || slot === "trinket";
      return (pair ? [0, 1] : [0]).map((index) => ({ slot, index, label: pair ? `${ctx.SLOT_LABEL[slot]} ${index + 1}` : ctx.SLOT_LABEL[slot] }));
    });
  }
  // Every item on this slot's lists, with its score at the viewed level (or the last level it was listed).
  function slotItems(slot) {
    const out = new Map();
    for (const p of ctx.slotPoints(slot)) for (const [id, sc] of p.items) out.set(id, sc);
    for (const [id, sc] of state.gear.extra?.[slot] || []) out.set(id, sc); // set pieces off the top lists
    for (const [id, sc] of ctx.pointAt(slot)?.items || []) out.set(id, sc);
    return out;
  }
  const slotOf = (id) => Object.keys(state.gear.slots).find((s) => slotItems(s).has(id));

  // Gain of a planned item over what is worn: Infinity = nothing useful worn.
  function status(r, id) {
    const score = slotItems(r.slot).get(id) ?? 0, w = ctx.wornAt(r.slot, r.index);
    const done = state.mode === "manual" ? ctx.ownedSet().has(id) : w?.id === id;
    const gain = !w || !(w.score > 0) || w.score < score * 0.1 ? Infinity : (score - w.score) / w.score * 100; // negative = worse than worn
    return { score, worn: w, done, gain };
  }
  // "+12%" / "−8%" (a loss against what is worn) / "same"
  const fmt = (g) => (g >= 0.05 ? ctx.fmtGain(g) : g <= -0.05 ? `\u2212${Math.abs(g) >= 10 ? Math.round(-g) : (-g).toFixed(1)}%` : "same");
  const gainSpan = (cls, g) => el("span", { class: g <= -0.05 ? `${cls} loss` : cls }, fmt(g));

  // ------------------------------------------------------------ planner table
  function renderTable() {
    const p = plan(), lvl = ctx.characterLevel();
    $("plan-rows").replaceChildren(...rows().map((r) => {
      const id = p[r.label], info = id && state.gear.items[id], st = info && status(r, id);
      const input = el("input", { type: "search", class: "plan-in", role: "combobox", "aria-autocomplete": "list", "aria-expanded": "false",
        "aria-controls": "plan-list", "aria-label": `Search an item for ${r.label}`, placeholder: info ? "Change…" : `Search ${r.label.toLowerCase()} items`,
        autocomplete: "off", spellcheck: "false" });
      input.addEventListener("focus", () => search(input, r));
      input.addEventListener("input", () => search(input, r));
      input.addEventListener("keydown", (e) => keys(e, input));
      input.addEventListener("blur", close);
      const want = info ? el("span", { class: "plan-want" }, ctx.itemLink(id, info),
        info.required_level > lvl ? el("span", { class: "badge", title: "You can't wear it yet" }, `Lv ${info.required_level}`) : null)
        : el("span", { class: "muted" }, "Nothing planned");
      const gainEl = !info ? el("span") : st.done ? el("span", { class: "plan-done" }, state.mode === "manual" ? "Have it" : "Wearing")
        : gainSpan("gain", st.gain);
      const li = el("li", { class: `plan-row${st?.done ? " done" : ""}` }, el("span", { class: "slot" }, r.label), want,
        el("span", { class: "score" }, info ? String(st.score) : ""), gainEl, el("span", { class: "plan-pick" }, input),
        info ? el("button", { type: "button", class: "plan-x", title: `Remove ${info.name} from the plan`, "aria-label": `Remove ${r.label} from the plan`, onclick: () => setPlan(r.label, null) }, "Remove") : el("span"));
      if (info?.set) li.append(setHint(info, p));
      return li;
    }));
    const n = Object.keys(p).filter((k) => state.gear.items[p[k]]).length;
    $("plan-clear").hidden = !n;
  }

  // "Part of <set>": the other pieces on our lists, one click to plan each.
  function setHint(info, p) {
    const planned = new Set(Object.values(p));
    const pieces = info.set.pieces.map(String).filter((pid) => pid in state.gear.items);
    const missing = info.set.pieces.length - pieces.length;
    const rest = pieces.filter((pid) => !planned.has(pid));
    const btns = rest.map((pid) => el("button", { type: "button", class: "plan-add", onclick: () => planPiece(pid) },
      `Add ${state.gear.items[pid].name}`));
    if (rest.length > 1) btns.unshift(el("button", { type: "button", class: "plan-add", onclick: () => rest.forEach(planPiece) }, "Add the rest of the set"));
    if (!btns.length && !missing) return el("p", { class: "plan-set muted" }, `${info.set.name}: every piece is planned.`);
    return el("p", { class: "plan-set muted" }, `${info.set.name}: `, ...btns,
      missing ? ` ${missing} piece${missing > 1 ? "s are" : " is"} not wearable by this spec or has no known source.` : "");
  }
  function planPiece(pid) {
    const slot = slotOf(pid), p = plan();
    const free = rows().filter((r) => r.slot === slot);
    const r = free.find((x) => !p[x.label]) || free[0];
    if (r) setPlan(r.label, pid);
  }

  // ------------------------------------------------------------ search box (one shared listbox)
  function search(input, r) {
    const q = input.value.trim().toLowerCase(), items = slotItems(r.slot), lvl = ctx.characterLevel();
    const wearable = (id) => Number((state.gear.items[id].required_level || 0) > lvl); // items you can wear now first
    const pool = q ? [...items].filter(([id]) => (state.gear.items[id].name || "").toLowerCase().includes(q)).sort((a, b) => wearable(a[0]) - wearable(b[0]) || b[1] - a[1])
      : (ctx.pointAt(r.slot)?.items || []); // empty box: the best list at the viewed level
    hits = pool.slice(0, MAX_HITS).map(([id]) => id);
    active = hits.length ? 0 : -1;
    open = { input, r };
    input.after(list);
    paint();
  }
  function paint() {
    const { input, r } = open, lvl = ctx.characterLevel();
    list.replaceChildren(...(hits.length ? hits.map((id, i) => {
      const info = state.gear.items[id], st = status(r, id);
      return el("li", { role: "option", id: `plan-o-${i}`, "aria-selected": String(i === active), onmousedown: (e) => { e.preventDefault(); choose(id); } },
        el("span", { class: `q-${["", "common", "uncommon", "rare", "epic", "legendary"][info.quality] || "common"}` }, info.name),
        el("span", { class: "muted" }, `${st.score}${info.required_level > lvl ? ` · Lv ${info.required_level}` : ""}${st.done ? " · worn" : ` · ${fmt(st.gain)}`}`));
    }) : [el("li", { class: "none", role: "option", "aria-disabled": "true" }, `No ${r.label.toLowerCase()} item by that name on this spec's lists`)]));
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `plan-o-${active}`); else input.removeAttribute("aria-activedescendant");
  }
  function close() {
    if (!open) return;
    open.input.setAttribute("aria-expanded", "false");
    open.input.removeAttribute("aria-activedescendant");
    list.hidden = true;
    open = null;
  }
  function choose(id) { const { r } = open; close(); setPlan(r.label, id); }
  function keys(e, input) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!hits.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length;
      paint();
    } else if (e.key === "Enter" && open && hits[active]) { e.preventDefault(); choose(hits[active]); }
    else if (e.key === "Escape") { input.value = ""; close(); }
  }

  // ------------------------------------------------------------ route
  // One stop per place (same describeSource key = same dungeon, vendor, quest ...).
  function stops() {
    const p = plan(), byLabel = new Map(rows().map((r) => [r.label, r]));
    const wanted = Object.entries(p).filter(([label, id]) => byLabel.has(label) && state.gear.items[id]);
    // An item with several sources goes where the most other planned items can also be had.
    const keyCount = new Map();
    for (const [, id] of wanted) for (const k of new Set((state.gear.items[id].sources || []).map((s) => ctx.describeSource(s).key))) keyCount.set(k, (keyCount.get(k) || 0) + 1);
    const out = new Map();
    let done = 0;
    for (const [label, id] of wanted) {
      const r = byLabel.get(label), info = state.gear.items[id], st = status(r, id);
      if (st.done) { done++; continue; }
      const srcs = info.sources || [];
      let src = srcs.reduce((best, s) => ((keyCount.get(ctx.describeSource(s).key) || 0) > (keyCount.get(ctx.describeSource(best).key) || 0) ? s : best), srcs[0]);
      const farm = farmOf(srcs);
      const d = farm?.d ?? (src ? ctx.describeSource(src) : { key: "unknown", label: "Source unknown", text: "" });
      if (farm) src = farm.src;
      const inst = src?.instance && state.meta.instances[src.instance];
      const loc = src?.loc ?? inst?.entrance ?? null;
      const stop = out.get(d.key) || { key: d.key, label: d.label, src: farm?.src ?? src, note: farm?.note, items: [], level: 0, value: 0,
        zone: loc?.zone ?? inst?.zone ?? src?.zone ?? null, loc, anywhere: ANYWHERE.test(d.key) };
      const need = Math.max(info.required_level || 0, inst && !inst.type.startsWith("raid") ? inst.levels?.[0] || 0 : 0, src?.type === "quest" ? src.min_level || 0 : 0);
      stop.level = Math.max(stop.level, need);
      stop.value += (Math.max(0, Math.min(st.gain, 100)) + 1) * (farm ? 0.25 : 1); // "new" counts as +100%; rare farms count a quarter
      stop.items.push({ label, id, gain: st.gain, d });
      out.set(d.key, stop);
    }
    return { list: [...out.values()], done, total: wanted.length };
  }

  // Rare open-world drop from several monsters in one zone: one "farm" stop, pinned on the best-rate monster.
  function farmOf(srcs) {
    const drops = srcs.filter((s) => s.type === "drop" && !s.instance);
    const zones = new Set(drops.map((s) => s.zone).filter(Boolean));
    const rates = drops.map((s) => s.chance).filter((c) => c != null);
    if (drops.length < 2 || drops.length !== srcs.length || zones.size !== 1 || !rates.length || Math.max(...rates) >= 1) return null;
    const [zone] = zones, lo = Math.min(...rates), hi = Math.max(...rates);
    const src = drops.filter((s) => s.loc).sort((a, b) => (b.chance ?? 0) - (a.chance ?? 0))[0];
    const pct = (c) => `${c.toFixed(2)}%`;
    return { src, d: { key: `farm:${zone}`, label: `Farm monsters in ${zone}`, text: `Rare drop from ${drops.map((s) => s.name).join(", ")}` },
      note: `Rare drop: ${lo === hi ? pct(hi) : `${pct(lo)}–${pct(hi)}`} a kill, about 1 in ${Math.round(100 / hi)} at best. Best farmed alongside quests in ${zone}.` };
  }

  // Travel cost between two stops: 0 same spot .. 3 other continent.
  function cost(a, b) {
    if (!a || b.anywhere) return 0.3;
    if (a.zone && a.zone === b.zone) return a.loc && b.loc ? Math.hypot(a.loc.x - b.loc.x, a.loc.y - b.loc.y) / 200 : 0.2;
    const ca = continent(a.zone), cb = continent(b.zone);
    return ca && cb ? (ca === cb ? 1 : 3) : 1.5;
  }

  // Greedy route: from where you are, the stop with the most upgrade per unit of travel; stops you are too low for come after.
  function route() {
    const { list: all, done, total } = stops(), lvl = ctx.characterLevel();
    const ready = all.filter((s) => s.level <= lvl), later = all.filter((s) => s.level > lvl).sort((a, b) => a.level - b.level || b.value - a.value);
    const order = [];
    let here = null;
    const top = Math.max(0, ...ready.map((s) => s.value));
    while (ready.length) {
      const i = ready.reduce((bi, s, j) => (s.value / (1 + cost(here, s)) > ready[bi].value / (1 + cost(here, ready[bi])) ? j : bi), 0);
      const s = ready.splice(i, 1)[0];
      s.why = s.note ? "" : !order.length ? (s.value === top ? "Biggest upgrade first: it makes the rest easier." : `Closest big upgrade${s.zone ? ` (${s.zone})` : ""}.`)
        : s.anywhere ? "Can be done from anywhere." : here?.zone && here.zone === s.zone ? `Also in ${s.zone}.`
        : continent(here?.zone) && continent(here?.zone) === continent(s.zone) ? `Same continent, ${s.zone}.` : "Next biggest upgrade.";
      order.push(s);
      if (!s.anywhere && s.zone) here = s;
    }
    for (const s of later) s.why = `Needs level ${s.level}.`;
    return { order, later, done, total };
  }

  function stepEl(s, n) {
    const ul = el("ul", { class: "g-list" }, s.items.sort((a, b) => b.gain - a.gain).map(({ label, id, gain, d }) => el("li", { title: d.text },
      el("span", { class: "slot" }, label), el("span", { class: "g-it" }, ctx.itemLink(id, state.gear.items[id])),
      gainSpan("g-d", gain))));
    return el("li", { class: "step" }, el("span", { class: "step-n", "aria-hidden": "true" }, String(n)),
      el("div", { class: "step-body" }, el("strong", { class: "g-title" }, s.label), el("p", { class: "step-why muted" }, s.note || s.why), ctx.pinBtn(s.src), ul));
  }

  function renderRoute() {
    const { order, later, done, total } = route();
    $("itin-sub").textContent = total ? `${done} of ${total} planned item${total > 1 ? "s" : ""} worn` : "";
    const out = [];
    if (order.length) out.push(el("ol", { class: "steps" }, order.map((s, i) => stepEl(s, i + 1))));
    if (later.length) out.push(el("h3", { class: "steps-h" }, "Later, when you level up"), el("ol", { class: "steps", start: order.length + 1 }, later.map((s, i) => stepEl(s, order.length + i + 1))));
    if (!total) out.push(el("p", { class: "muted" }, "Pick the item you want in each slot. The route then lists where to go, in a good order."));
    else if (!order.length && !later.length) out.push(el("p", { class: "muted" }, "You wear everything in your plan."));
    $("itin").replaceChildren(...out);
  }

  return {
    render() { if (!state.gear) return; close(); renderTable(); renderRoute(); },
    plan, setPlan,
    clear() { ctx.store(key(), {}); ctx.render(); },
    _route: route, // for tests
  };
}
