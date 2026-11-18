// Item lookup card: type-ahead over the item names in the loaded gear JSON, then where that item is best.
const MAX_HITS = 8;

// [22,23,24,27] -> "22–24, 27"
function ranges(levels) {
  const out = [];
  let start = null, prev = null;
  for (const l of [...levels, Infinity]) {
    if (start !== null && l !== prev + 1) { out.push(start === prev ? `${start}` : `${start}–${prev}`); start = null; }
    if (l !== Infinity && start === null) start = l;
    prev = l;
  }
  return out.join(", ");
}

export function setupLookup(ctx) {
  const { state, $, el } = ctx;
  const input = $("lk-in"), list = $("lk-list"), out = $("lk-out");
  let hits = [], active = -1, sel = null; // sel: { id, name }

  // id -> slots it appears in, from the (weapon-filtered) lists
  function index() {
    const map = new Map();
    for (const slot of Object.keys(state.gear.slots)) for (const p of ctx.slotPoints(slot)) for (const [id] of p.items) if (!map.get(id)?.includes(slot)) map.set(id, [...(map.get(id) || []), slot]);
    return map;
  }

  function levelsFor(slot, id) {
    const r = { best: [], top3: [], any: [] };
    for (let l = 10; l <= 60; l++) {
      const i = ctx.pointAt(slot, l, 0)?.items.findIndex(([x]) => x === id) ?? -1;
      if (i < 0) continue;
      r.any.push(l);
      if (i < 3) r.top3.push(l);
      if (i === 0) r.best.push(l);
    }
    return r;
  }

  function where(slot, id) {
    const r = levelsFor(slot, id), parts = [];
    if (r.best.length) parts.push(`Best at ${ranges(r.best)}`);
    if (r.top3.length && r.top3.length !== r.best.length) parts.push(`${r.best.length ? "top 3" : "Top 3"} at ${ranges(r.top3)}`);
    if (!r.top3.length && r.any.length) parts.push(`On the list at ${ranges(r.any)}`);
    const tiers = Object.keys(state.meta.tiers).map(Number).filter((t) => t > 0 && ctx.pointAt(slot, 60, t)?.items[0]?.[0] === id);
    if (tiers.length) parts.push(`best in ${tiers.map(ctx.tierShort).join(", ")}`);
    return parts.length ? parts.join(", ") : "Not on the list for levels 10–60";
  }

  function closeList() { hits = []; active = -1; list.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); }

  function search() {
    const q = input.value.trim().toLowerCase();
    if (!q) return closeList();
    const idx = index();
    hits = [...idx.keys()].map((id) => ({ id, name: state.gear.items[id].name || "" }))
      .filter((h) => h.name.toLowerCase().includes(q))
      .sort((a, b) => (b.name.toLowerCase().startsWith(q) - a.name.toLowerCase().startsWith(q)) || a.name.localeCompare(b.name))
      .slice(0, MAX_HITS);
    active = hits.length ? 0 : -1;
    paintList(idx);
  }

  function paintList(idx = index()) {
    list.replaceChildren(...(hits.length ? hits.map((h, i) => el("li", { role: "option", id: `lk-o-${i}`, "aria-selected": String(i === active),
      onmousedown: (e) => { e.preventDefault(); choose(h); } },
      el("span", {}, h.name), el("span", { class: "muted" }, ctx.SLOT_LABEL[idx.get(h.id)[0]]))) : [el("li", { class: "none", role: "option", "aria-disabled": "true" }, "Not in this spec's lists")]));
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `lk-o-${active}`); else input.removeAttribute("aria-activedescendant");
  }

  function choose(h) { sel = h; input.value = h.name; closeList(); refresh(); }

  input.addEventListener("input", search);
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (list.hidden) search();
      if (!hits.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + hits.length) % hits.length;
      paintList();
    } else if (e.key === "Enter") {
      if (!list.hidden && hits[active]) { e.preventDefault(); choose(hits[active]); }
    } else if (e.key === "Escape") {
      if (!list.hidden) closeList();
      else { input.value = ""; sel = null; refresh(); }
    }
  });
  input.addEventListener("blur", closeList);

  function refresh() {
    out.replaceChildren();
    if (!sel || !state.gear) return;
    const idx = index(), slots = idx.get(sel.id);
    if (!slots) { out.append(el("p", { class: "muted" }, `${sel.name} is not in this spec's lists.`)); return; }
    const info = state.gear.items[sel.id], reasons = ctx.reasonsOf(info);
    out.append(el("div", { class: "lk-name" }, ctx.itemLink(sel.id, info), reasons.length ? Object.assign(ctx.uncBadge(), { title: reasons.join("\n") }) : null));
    out.append(el("ul", {}, slots.map((slot) => {
      const pts = ctx.slotPoints(slot);
      const entry = ctx.pointAt(slot)?.items.find(([x]) => x === sel.id) || pts.flatMap((p) => p.items).find(([x]) => x === sel.id);
      const w = ctx.wornScoreFor(slot);
      let cmp = "";
      if ((info.required_level || 0) > state.level) cmp = ` — needs level ${info.required_level}`;
      else if (!w) cmp = " — new: nothing worn here";
      else if (w.id === sel.id) cmp = " — you have this";
      else if (w.score != null) {
        const pct = w.score > 0 ? (entry[1] - w.score) / w.score * 100 : Infinity;
        cmp = pct === Infinity ? " — new" : pct >= 0.05 ? ` — ${ctx.fmtGain(pct)} over ${w.name}` : pct <= -0.05 ? ` — ${ctx.fmtGain(-pct).slice(1)} below ${w.name}` : ` — same as ${w.name}`;
      }
      return el("li", {}, el("strong", {}, ctx.SLOT_LABEL[slot]), `: score ${entry[1]}${info.unscored?.length ? "*" : ""} at level ${state.level}${cmp}. `, where(slot, sel.id), ".");
    })));
    const srcs = info.sources || [];
    if (srcs.length) out.append(el("h3", {}, "Where to get it"), el("ul", {}, srcs.map((s) => { const d = ctx.describeSource(s); return el("li", {}, `${d.label}. ${d.text}`); })));
    out.append(...ctx.extrasOf(info));
    ctx.refreshTooltips();
  }

  return { refresh };
}
