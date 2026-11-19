// Where items come from: human-readable source text, and the categories used by the
// "Get it from" filter and the "easiest" sort.

// ---------------------------------------------------------------- sources
const STANDINGS = ["Hated", "Hostile", "Unfriendly", "Neutral", "Friendly", "Honored", "Revered", "Exalted"];
// " Costs about 1g and 15 Warsong Gulch Mark of Honor." for a vendor-like source, or "".
function costText(src) {
  const cost = [Number(src.copper) > 0 ? `about ${formatMoney(src.copper)}` : "", ...(src.tokens || []).map(([n, q]) => `${q} ${n}`)].filter(Boolean);
  return cost.length ? ` Costs ${cost.join(" and ")}.` : "";
}
// PvP ranks 1-14: [Alliance, Horde] title.
const PVP_RANKS = [["Private", "Scout"], ["Corporal", "Grunt"], ["Sergeant", "Sergeant"], ["Master Sergeant", "Senior Sergeant"],
  ["Sergeant Major", "First Sergeant"], ["Knight", "Stone Guard"], ["Knight-Lieutenant", "Blood Guard"], ["Knight-Captain", "Legionnaire"],
  ["Knight-Champion", "Centurion"], ["Lieutenant Commander", "Champion"], ["Commander", "Lieutenant General"], ["Marshal", "General"],
  ["Field Marshal", "Warlord"], ["Grand Marshal", "High Warlord"]];
// Map spot of a source (QuestieDB Forever): {zone, x, y (percent of the zone map), map (uiMapId)}.
export const locText = (l) => `${l.zone} ${l.x.toFixed(1)}, ${l.y.toFixed(1)}`;
// Chat command that drops a map pin: TomTom's /way, or the built-in user waypoint (needs checking in the Forever client).
export const pinCommand = (l, kind) => kind === "builtin"
  ? `/run C_Map.SetUserWaypoint(UiMapPoint.CreateFromCoordinates(${l.map},${l.x / 100},${l.y / 100}))`
  : `/way ${l.zone} ${l.x.toFixed(1)} ${l.y.toFixed(1)}`;
// Wowhead Classic zone map images, keyed by zone name -> Wowhead zone (area) id. Pins use the same 0-100 coordinates.
// ponytail: Forever-only zones (Riverglades, Zephras Isle) have no Wowhead map, so they get no hover map.
const MAP_AREA = { "Alterac Mountains": 36, "Arathi Highlands": 45, "Ashenvale": 331, "Azshara": 16, "Badlands": 3, "Blasted Lands": 4,
  "Burning Steppes": 46, "Darkshore": 148, "Darnassus": 1657, "Deadwind Pass": 41, "Desolace": 405, "Dun Morogh": 1, "Durotar": 14,
  "Duskwood": 10, "Dustwallow Marsh": 15, "Eastern Plaguelands": 139, "Elwynn Forest": 12, "Felwood": 361, "Feralas": 357,
  "Hillsbrad Foothills": 267, "Ironforge": 1537, "Loch Modan": 38, "Moonglade": 493, "Mulgore": 215, "Orgrimmar": 1637,
  "Redridge Mountains": 44, "Searing Gorge": 51, "Silithus": 1377, "Silverpine Forest": 130, "Stonetalon Mountains": 406,
  "Stormwind City": 1519, "Stranglethorn Vale": 33, "Swamp of Sorrows": 8, "Tanaris": 440, "Teldrassil": 141, "The Barrens": 17,
  "The Hinterlands": 47, "Thousand Needles": 400, "Thunder Bluff": 1638, "Tirisfal Glades": 85, "Un'Goro Crater": 490,
  "Undercity": 1497, "Western Plaguelands": 28, "Westfall": 40, "Wetlands": 11, "Winterspring": 618 };
export const mapImage = (zone) => MAP_AREA[zone] ? `https://wow.zamimg.com/images/wow/classic/maps/enus/original/${MAP_AREA[zone]}.jpg` : null;
export function formatMoney(copper) {
  const c = Number(copper), g = Math.floor(c / 10000), s = Math.floor(c / 100) % 100;
  return g ? `${g}g ${s}s` : `${s}s ${c % 100}c`;
}
function describeBase(meta, src) {
  const instanceName = (key) => meta.instances[key]?.name ?? key;
  const instanceLevels = (key) => {
    const inst = meta.instances[key];
    if (!inst || inst.type.startsWith("raid") || inst.type === "world_boss") return "";
    return ` (level ${inst.levels[0]}–${inst.levels[1]})`;
  };
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
      const label = inst && meta.instances[inst]?.tier ? `Quest: ${src.name} — needs ${instanceName(inst)}` : `Quest: ${src.name}${lvl}`;
      return { key: `quest:${src.id}`, label, text: `Quest reward${where}${from}. Can be picked up at level ${src.min_level || 1}.` };
    }
    case "pvp_rank": {
      const name = PVP_RANKS[src.rank - 1]?.[src.faction === "H" ? 1 : 0] || "";
      const price = costText(src);
      const who = src.name ? `${src.name}${src.title ? ` <${src.title}>` : ""}` : "your faction's PvP quartermaster";
      if (!src.rank) return { key: `pvp:${src.id}`, label: `PvP reward from ${src.name}`, text: `PvP reward sold by ${who}; the rank needed is not known.${price}` };
      return { key: `pvp:${src.rank}`, label: `PvP rank ${src.rank}${name ? ` (${name})` : ""}`, text: `Reward for reaching PvP rank ${src.rank}${name ? `, ${name}` : ""}. Sold by ${who}.${price}` };
    }
    case "vendor": {
      // Forever data: rep vendors are named by faction with {standing: 0-7}; plain vendors may have no name.
      const standing = STANDINGS[Number(src.reputation?.standing)];
      const repNeed = src.reputation ? ` Needs ${standing || "some"} reputation with ${src.rep_name || "their faction"}.` : "";
      if (src.reputation && !src.id) return { key: `rep:${src.name}`, label: `Buy from ${src.name} quartermaster`, text: `Needs ${standing || "some"} reputation with ${src.name}.` };
      const who = src.name || "a vendor";
      const price = costText(src);
      return { key: src.name ? `vendor:${src.id}` : "vendor", label: `Buy from ${who}${src.reputation ? ` (${standing ? `${standing} with ` : ""}${src.rep_name || "faction"}${standing ? "" : " rep"})` : src.zone ? ` (${src.zone})` : ""}`, text: `Sold by ${who}${src.title ? ` <${src.title}>` : ""}.${price}${repNeed}` };
    }
    case "craft": {
      const raid = inst ? ` Needs materials from ${instanceName(inst)}.` : "";
      const prof = src.name || "a profession";
      const r = src.recipe || {}, what = r.name || "the recipe", from = r.vendors?.join(" or ");
      const recipe = {
        trainer: " Recipe from the profession trainer.",
        automatic: " Learned automatically with the profession.",
        vendor: ` Needs ${what}, sold by ${from}.`,
        favor: ` Needs ${what}, bought from ${from} for ${r.favor} Merchant's Favor${STANDINGS[r.standing] ? ` (needs ${STANDINGS[r.standing]})` : ""}. Can also turn up on the Auction House, usually expensive.`,
        drop: ` Needs ${what}, a random drop${r.drops ? ` (${r.drops})` : ""}. Sometimes on the Auction House.`,
        unknown: ` Needs ${what}; where to get it is not known yet.`,
      }[r.kind] || "";
      const tag = { favor: ` — pattern for ${r.favor} Merchant's Favor`, drop: " — pattern is a rare drop", unknown: " — pattern source unknown" }[r.kind] || "";
      return { key: `craft:${prof}:${r.kind || ""}`, label: `Craft with ${prof}${tag}`, text: `Crafted with ${prof}${src.skill ? ` (skill ${src.skill})` : ""}.${recipe}${raid}` };
    }
    case "world_drop":
      return { key: "ah", label: "Auction House / world drops", text: "Random drop from many monsters. It is Bind on Equip, so you can often buy it on the Auction House." };
    case "container":
      return { key: `cont:${src.id}`, label: `Open ${src.name || "a container"}`, text: `Found in ${src.name || "a container"}${chance}` };
    default:
      return { key: src.type, label: src.type, text: src.type };
  }
}

// describeBase plus the optional P9 fields: quest chain, crafting reagents, zone. `extra` is just those bits.
export function describeSource(meta, src) {
  const d = describeBase(meta, src), bits = [];
  if (src.chain) bits.push(`Quest ${src.chain.pos} of ${src.chain.len} — starts with ${src.chain.first_name}${src.chain.first_level != null ? ` (level ${src.chain.first_level})` : ""}.`);
  if (src.giver && src.giver !== src.start_npc) bits.push(`From ${src.giver}.`);
  if (src.loc) d.where = locText(src.loc);
  if (src.reagents?.length) bits.push(`Needs ${src.reagents.map(([n, c]) => `${c}× ${n}`).join(", ")}.`);
  if (src.zone && !src.loc && !`${d.label} ${d.text}`.includes(src.zone)) bits.push(`Zone: ${src.zone}.`);
  if (!bits.length) return d;
  const extra = bits.join(" ");
  return { ...d, text: `${d.text}${/[.!?]$/.test(d.text) ? "" : "."} ${extra}`, extra };
}

export const CATS = { vendor: "Vendor / AH", rep: "Reputation / Favor vendors", ddrop: "Dungeon drops", wdrop: "World drops", craft: "Crafted", wq: "World quests", dq: "Dungeon quests", pvp: "PvP rank rewards" };
export const EFFORT = { vendor: 1, rep: 2, craft: 2, wq: 3, wdrop: 4, dq: 5, ddrop: 6, pvp: 7 };
// Open-world drop under 1%: hidden unless "Rare drops" is ticked (same rule as build_gear.py source_level).
export const isRare = (src) => src.type === "drop" && !src.instance && src.chance != null && src.chance < 1;
export function catsOf(src) {
  switch (src.type) {
    case "vendor": return [src.reputation ? "rep" : "vendor"];
    case "craft": return src.recipe?.kind === "favor" ? ["rep"] : src.recipe?.kind === "drop" ? ["wdrop"] : ["craft"]; // the pattern decides
    case "pvp_rank": return ["pvp"];
    case "world_drop": return ["wdrop", "vendor"]; // BoE: also on the Auction House
    case "quest": return [src.instance ? "dq" : "wq"];
    default: return [src.instance ? "ddrop" : "wdrop"]; // drop, boss, instance_trash, object, container
  }
}
