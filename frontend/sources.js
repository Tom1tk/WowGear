// Where items come from: human-readable source text, and the categories used by the
// "Get it from" filter and the "easiest" sort.

// ---------------------------------------------------------------- sources
const STANDINGS = ["Hated", "Hostile", "Unfriendly", "Neutral", "Friendly", "Honored", "Revered", "Exalted"];
// Map spot of a source (QuestieDB Forever): {zone, x, y (percent of the zone map), map (uiMapId)}.
export const locText = (l) => `${l.zone} ${l.x.toFixed(1)}, ${l.y.toFixed(1)}`;
// Chat command that drops a map pin: TomTom's /way, or the built-in user waypoint (needs checking in the Forever client).
export const pinCommand = (l, kind) => kind === "builtin"
  ? `/run C_Map.SetUserWaypoint(UiMapPoint.CreateFromCoordinates(${l.map},${l.x / 100},${l.y / 100}))`
  : `/way ${l.zone} ${l.x.toFixed(1)} ${l.y.toFixed(1)}`;
// Zone and dungeon pages on wowforevermap.com (from its sitemap, 2026-11-18). The site has no coordinate links, so we open the zone page.
const MAP_ZONES = new Set("alterac-mountains arathi-highlands ashenvale azshara badlands blasted-lands burning-steppes darkshore darnassus deadwind-pass desolace dun-morogh durotar duskwood dustwallow-marsh eastern-plaguelands elwynn-forest felwood feralas hillsbrad-foothills ironforge loch-modan moonglade mount-hyjal mulgore orgrimmar redridge-mountains riverglades searing-gorge shendralas silithus silverpine-forest stonetalon-mountains stormwind-city stranglethorn-vale swamp-of-sorrows tanaris teldrassil the-barrens the-hinterlands thousand-needles thunder-bluff tirisfal-glades undercity ungoro-crater western-plaguelands westfall wetlands winterspring zephras-isle".split(" "));
const MAP_DUNGEONS = new Set("blackfathom-deeps blackrock-spire city-of-dalaran dire-maul excavation-site-wetlands gnomeregan maraudon onyxias-lair ragefire-chasm razorfen-downs razorfen-kraul ruins-of-lordaeron scarlet-monastery scholomance shadowfang-keep stormwind-stockade stratholme sunken-temple the-hall-of-thanes uldaman wailing-caverns zulfarrak".split(" "));
export function mapUrl(zone) {
  const s = zone === "The Stockade" ? "stormwind-stockade" : zone.toLowerCase().replace(/'/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  if (MAP_ZONES.has(s)) return `https://wowforevermap.com/zone/${s}`;
  if (MAP_DUNGEONS.has(s)) return `https://wowforevermap.com/dungeons/${s}`;
  return null;
}
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
    case "vendor": {
      // Forever data: rep vendors are named by faction with {standing: 0-7}; plain vendors may have no name.
      const standing = STANDINGS[Number(src.reputation?.standing)];
      const repNeed = src.reputation ? ` Needs ${standing || "some"} reputation with ${src.rep_name || "their faction"}.` : "";
      if (src.reputation && !src.id) return { key: `rep:${src.name}`, label: `Buy from ${src.name} quartermaster`, text: `Needs ${standing || "some"} reputation with ${src.name}.` };
      const who = src.name || "a vendor";
      const price = Number(src.copper) > 0 ? ` Costs about ${formatMoney(src.copper)}.` : "";
      return { key: src.name ? `vendor:${src.id}` : "vendor", label: `Buy from ${who}${src.zone ? ` (${src.zone})` : ""}`, text: `Sold by ${who}${src.title ? ` <${src.title}>` : ""}.${price}${repNeed}` };
    }
    case "craft": {
      const recipe = src.recipe ? ` Recipe: ${src.recipe.name}${src.recipe.from?.length ? ` (${src.recipe.from.join(" / ")})` : ""}.` : " Recipe from the profession trainer.";
      const raid = inst ? ` Needs materials from ${instanceName(inst)}.` : "";
      const prof = src.name || "a profession";
      return { key: `craft:${prof}`, label: `Craft with ${prof}`, text: `Crafted with ${prof}${src.skill ? ` (skill ${src.skill})` : ""}.${recipe}${raid}` };
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

export const CATS = { vendor: "Vendor / AH", rep: "Reputation vendors", ddrop: "Dungeon drops", wdrop: "World drops", craft: "Crafted", wq: "World quests", dq: "Dungeon quests" };
export const EFFORT = { vendor: 1, rep: 2, craft: 2, wq: 3, wdrop: 4, dq: 5, ddrop: 6 };
export function catsOf(src) {
  switch (src.type) {
    case "vendor": return [src.reputation ? "rep" : "vendor"];
    case "craft": return ["craft"];
    case "world_drop": return ["wdrop", "vendor"]; // BoE: also on the Auction House
    case "quest": return [src.instance ? "dq" : "wq"];
    default: return [src.instance ? "ddrop" : "wdrop"]; // drop, boss, instance_trash, object, container
  }
}
