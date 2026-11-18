# Hand-kept tables for WoW Forever (W2)

Built 2026-11-18. Files: `data/forever/instances.json`, `data/forever/classes.json`.

## Key finding for W1/W3

QuestieDB `data/Forever/` is **not Forever data**: `conversion.json` says "this is a converted Era baseline, not complete Forever content" (ItemDB sha256 is identical to the Classic ItemDB; NpcDB is the Classic NPC DB with remapped coordinates). It has none of the new dungeon/raid NPCs and still contains MC/BWL/ZG/AQ/Naxx NPCs. Use it for Classic NPC levels/areas only. warcraftdb has no instance zone ids: NPC nodes carry no zone or level for dungeon bosses, quests carry only a zone *name* (e.g. "Krol'dok Stronghold"). Blizzard `journal-instance` / `journal-encounter` indexes are empty in static-forever-eu. So the NPC-to-instance mapping for new instances must come from names or drop tables, not zone ids.

## Instances (37 rows)

Ids: questie_areas = QuestieDB area ids with NPC spawns (Classic baseline), warcraftdb zone = overworld zone of the entrance, boss levels = min-max of elite+ NPC levels in those areas (Classic baseline).

| key | name | levels | side | tier | type | questie areas | wcdb zone | boss levels |
|---|---|---|---|---|---|---|---|---|
| ragefire_chasm | Ragefire Chasm | 13-18 | H | 0 | dungeon | [2437] | 1454 | [14, 16] |
| wailing_caverns | Wailing Caverns | 15-24 | - | 0 | dungeon | [718] | 1413 | [18, 21] |
| the_deadmines | The Deadmines | 17-26 | - | 0 | dungeon | [1581] | 1436 | [17, 21] |
| shadowfang_keep | Shadowfang Keep | 20-30 | - | 0 | dungeon | [209] | 1421 | [18, 26] |
| blackfathom_deeps | Blackfathom Deeps | 24-32 | - | 0 | dungeon | [719] | 1440 | [23, 28] |
| the_stockade | The Stockade | 24-32 | A | 0 | dungeon | [717] | 1453 | [23, 29] |
| gnomeregan | Gnomeregan | 29-38 | - | 0 | dungeon | [721] | 1426 | [26, 34] |
| razorfen_kraul | Razorfen Kraul | 29-38 | - | 0 | dungeon | [491] | 1413 | [25, 33] |
| sm_graveyard | Scarlet Monastery: Graveyard | 30-38 | - | 0 | dungeon | [796] | 1420 | [31, 42] |
| sm_library | Scarlet Monastery: Library | 33-41 | - | 0 | dungeon | - | 1420 | - |
| sm_armory | Scarlet Monastery: Armory | 36-44 | - | 0 | dungeon | - | 1420 | - |
| sm_cathedral | Scarlet Monastery: Cathedral | 38-46 | - | 0 | dungeon | - | 1420 | - |
| razorfen_downs | Razorfen Downs | 37-46 | - | 0 | dungeon | [722] | 1413 | [35, 41] |
| uldaman | Uldaman | 41-51 | - | 0 | dungeon | [1337] | 1418 | [37, 47] |
| zulfarrak | Zul'Farrak | 44-54 | - | 0 | dungeon | [1176] | 1446 | [35, 48] |
| maraudon | Maraudon | 46-55 | - | 0 | dungeon | [2100] | 1443 | [43, 51] |
| sunken_temple | The Temple of Atal'Hakkar (Sunken Temple) | 50-60 | - | 0 | dungeon | [1477] | 1435 | [47, 55] |
| blackrock_depths | Blackrock Depths | 52-60 | - | 0 | dungeon | [1585] | - | [49, 59] |
| lower_blackrock_spire | Lower Blackrock Spire | 55-60 | - | 0 | dungeon | [1583] | - | [54, 62] |
| upper_blackrock_spire | Upper Blackrock Spire | 59-60 | - | 0 | dungeon | - | - | - |
| dire_maul_east | Dire Maul: East | 54-60 | - | 0 | dungeon | [2557] | 1444 | [52, 62] |
| dire_maul_west | Dire Maul: West | 56-60 | - | 0 | dungeon | - | 1444 | - |
| dire_maul_north | Dire Maul: North | 56-60 | - | 0 | dungeon | - | 1444 | - |
| scholomance | Scholomance | 58-60 | - | 0 | dungeon | [2057] | 1422 | [58, 62] |
| stratholme | Stratholme | 58-60 | - | 0 | dungeon | [2017] | 1423 | [56, 62] |
| hall_of_thanes | Hall of Thanes | 13-18 | - | 0 | dungeon | - | 1455 | - |
| ruins_of_lordaeron | Ruins of Lordaeron | 15-20 | - | 0 | dungeon | - | 1420 | - |
| excavation_site_wetlands | Excavation Site: Wetlands | 24-29 | - | 0 | dungeon | - | 1437 | - |
| city_of_dalaran | City of Dalaran | 28-33 | - | 0 | dungeon | - | 1416 | - |
| the_drowned_city | The Drowned City | 35-40 | - | 0 | dungeon | - | 1434 | - |
| kroldok_stronghold | Krol'dok Stronghold | 40-45 | - | 0 | dungeon | - | 2548 | - |
| alcaz_prison | Alcaz Prison | 48-53 | - | 0 | dungeon | - | 1445 | - |
| blackmaw_hold | Blackmaw Hold | 55-60 | - | 0 | dungeon | - | 1447 | - |
| shapers_terrace | Shaper's Terrace | 58-60 | - | 0 | dungeon | - | 1449 | - |
| barrow_deeps | The Barrow Deeps | 60-60 | - | 1 | raid10 | - | 2482 | - |
| hyjal_summit | Hyjal Summit | 60-60 | - | 1 | raid20 | - | 2482 | - |
| onyxias_lair | Onyxia's Lair | 60-60 | - | 1 | raid40 | [2159] | 1445 | [63, 63] |

Exists in Forever at launch: all 25 Classic dungeon entries (Scarlet wings and Dire Maul wings separate; Stratholme gates merged) plus the 9 new ones. Raids opening 9 Dec 2026: Barrow Deeps (10p, 8 bosses), Hyjal Summit (20p, 13 bosses), Onyxia's Lair (40p, Drakefire Amulet in inventory). Molten Core, BWL, ZG, AQ, Naxxramas are **not** in the launch tier (Blizzard raid overview does not mention them; Warcraft Tavern: other vanilla raids confirmed to return later, unnamed; Scarlet Enclave planned). They are not in the table; add rows when announced. World bosses: no Forever source found, omitted.

Sources: Blizzard news 24301455 (new dungeons) and 24303009 (raids), Blizzard forum post 628618 (ranges), Warcraft Tavern dungeons + raids guides, Icy Veins and Warcraft Tavern news, Gameleap (cites Wowhead guide, read via Gameleap only), forever.warcraftdb.com zone/quest/NPC nodes, QuestieDB. Era table used as baseline. Wowhead and wago.tools were not fetched.

### Uncertain rows
- **Ragefire Chasm**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 13-18); 1 Forever source
- **Ragefire Chasm**: Side: location based (Stormwind / Orgrimmar); Forever sources do not state a restriction
- **Wailing Caverns**: Level range: Warcraft Tavern Forever table 15-24, Classic Era table 17-24; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **The Deadmines**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 17-26); 1 Forever source
- **Shadowfang Keep**: Level range: Warcraft Tavern Forever table 20-30, Classic Era table 22-30; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Blackfathom Deeps**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 24-32); 1 Forever source
- **The Stockade**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 24-32); 1 Forever source
- **The Stockade**: Side: location based (Stormwind / Orgrimmar); Forever sources do not state a restriction
- **Gnomeregan**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 29-38); 1 Forever source
- **Razorfen Kraul**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 29-38); 1 Forever source
- **Scarlet Monastery: Graveyard**: Level range: Warcraft Tavern Forever table 30-38, Classic Era table 26-36; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Scarlet Monastery: Library**: Level range: Warcraft Tavern Forever table 33-41, Classic Era table 29-39; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Scarlet Monastery: Armory**: Level range: Warcraft Tavern Forever table 36-44, Classic Era table 32-42; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Scarlet Monastery: Cathedral**: Level range: Warcraft Tavern Forever table 38-46, Classic Era table 35-45; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Razorfen Downs**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 37-46); 1 Forever source
- **Uldaman**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 41-51); 1 Forever source
- **Zul'Farrak**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 44-54); 1 Forever source
- **Maraudon**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 46-55); 1 Forever source
- **The Temple of Atal'Hakkar (Sunken Temple)**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 50-60); 1 Forever source
- **Blackrock Depths**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 52-60); 1 Forever source
- **Lower Blackrock Spire**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 55-60); 1 Forever source
- **Upper Blackrock Spire**: Level range: Warcraft Tavern Forever table 59-60, Classic Era table 55-60; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Upper Blackrock Spire**: Group size: Classic was 10-player; Forever size not confirmed by any source
- **Dire Maul: East**: Level range: Warcraft Tavern Forever table 54-60, Classic Era table 55-60; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Dire Maul: West**: Level range: Warcraft Tavern Forever table 56-60, Classic Era table 57-60; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Dire Maul: North**: Level range: Warcraft Tavern Forever table 56-60, Classic Era table 57-60; no second Forever source with the same scale (Gameleap/Wowhead uses hard/at-level/easy bands)
- **Scholomance**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 58-60); 1 Forever source
- **Stratholme**: Level range: only Warcraft Tavern gives Forever values (matches Classic Era 58-60); 1 Forever source
- **Hall of Thanes**: Level range: Blizzard news and forum post 13-18, Warcraft Tavern dungeon table 13-20
- **Hall of Thanes**: Side: Blizzard says Alliance reach it easily, no restriction stated, so side left null
- **Hall of Thanes**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **Ruins of Lordaeron**: Level range: Blizzard news and forum post 15-20, Warcraft Tavern dungeon table 15-22
- **Ruins of Lordaeron**: Side: Blizzard says Horde reach it easily, no restriction stated, so side left null
- **Ruins of Lordaeron**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **Excavation Site: Wetlands**: Level range: Blizzard news and forum post 24-29, Warcraft Tavern dungeon table 26-33
- **Excavation Site: Wetlands**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **City of Dalaran**: Level range: Blizzard news and forum post 28-33, Warcraft Tavern dungeon table 28-35
- **City of Dalaran**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **The Drowned City**: Level range: Blizzard news and forum post 35-40, Warcraft Tavern dungeon table 35-42
- **The Drowned City**: Level range: Mobalytics (via search snippet) lists 35-50
- **The Drowned City**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **Krol'dok Stronghold**: Level range: Blizzard news and forum post 40-45, Warcraft Tavern dungeon table 40-47
- **Krol'dok Stronghold**: Level range: BlizzCon listing 40-55 (corrected), Mobalytics 40-55 in snippet
- **Krol'dok Stronghold**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **Alcaz Prison**: Level range: Blizzard news and forum post 48-53, Warcraft Tavern dungeon table 48-55
- **Alcaz Prison**: Name: Gameleap calls it 'Alcaz Island Prison'
- **Alcaz Prison**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **Blackmaw Hold**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **Shaper's Terrace**: No questie_areas: QuestieDB Forever has no new-content NPCs; instance zone id for NPC mapping not available from warcraftdb either
- **The Barrow Deeps**: Opens 9 Dec 2026: loot and boss data are datamined/unreleased; warcraftdb has no boss NPCs for this raid yet
- **Hyjal Summit**: Opens 9 Dec 2026: loot and boss data are datamined/unreleased; warcraftdb has no boss NPCs for this raid yet
- **Onyxia's Lair**: Boss level 63 is the Classic baseline (QuestieDB Forever is a converted Classic DB); Forever boss level unconfirmed
- **Onyxia's Lair**: Blizzard's written recap omits Onyxia's Lair in one article; roadmap slide and raid overview include it
- **Onyxia's Lair**: Opens 9 Dec 2026: loot and boss data are datamined/unreleased; warcraftdb has no boss NPCs for this raid yet

Level-range policy: new dungeons use Blizzard's official ranges (they match the plan's third-party list exactly). Returning dungeons use Warcraft Tavern's Forever table, which shifts several ranges by a few levels vs Era; only one Forever source on that scale, hence flagged.

## Classes and races

Sources: forever.warcraftdb.com `/api/data/node/race/{id}` + `/tab/classes` + `/tab/racials`, Blizzard Game Data API `playable-race`/`playable-class` (static-forever-eu, via coordinator's key), Method.gg and Icy Veins combo guides (search snippets), Warcraft Tavern weapon skills article.

| id | race | faction | classes (ids) |
|---|---|---|---|
| 1 | Human | A | Warrior, Paladin, Hunter, Rogue, Priest, Mage, Warlock (new: Hunter) |
| 3 | Dwarf | A | Warrior, Paladin, Hunter, Rogue, Priest, Shaman (new: Shaman) |
| 4 | Night Elf | A | Warrior, Hunter, Rogue, Priest, Druid |
| 7 | Gnome | A | Warrior, Rogue, Priest, Mage, Warlock (new: Priest) |
| 95 | High Order Skyborne | A | Warrior, Hunter, Rogue, Mage, Druid |
| 2 | Orc | H | Warrior, Hunter, Rogue, Shaman, Mage, Warlock (new: Mage) |
| 5 | Undead | H | Warrior, Paladin, Rogue, Priest, Mage, Warlock (new: Paladin) |
| 6 | Tauren | H | Warrior, Hunter, Shaman, Druid |
| 8 | Troll | H | Warrior, Hunter, Rogue, Priest, Shaman, Mage, Warlock (new: Warlock) |
| 96 | Windshaper Skyborne | H | Warrior, Hunter, Rogue, Shaman, Druid |

Skyborne is two races, one per faction (shared name; both lore name Shen'dorei). The coordinator's note said both factions have Paladins and Shamans; the API list the same note contains (and warcraftdb) does not give Skyborne Paladins, and only the Horde version has Shaman. I used the lists. Racials (warcraftdb tooltips): Skyborne Walk on Air, Wind Blessed (+2% haste; Method says Alliance 3%), Elemental Insight, Read Leyline (A) / Skysight (H).

Specs: three trees per class, Era keys kept (feral_cat / feral_bear split on Feral Combat). Blizzard names: Priest "Shadow Magic", Shaman "Elemental Combat". `leveling_spec` is not in classes.json in Era either (it comes from the weights file), so not added.

### Uncertain
- Proficiencies (armor/weapons/dual-wield levels) are Era values; no Forever source confirms or changes them (warcrafttavern says weaponmaster-style talents replaced weapon specializations, not proficiencies)
- Racial weapon skills: warcraftdb launch racials list no Human Sword/Orc Axe/Dwarf/Troll weapon racial; Warcraft Tavern says Human Sword and Orc Axe Specialization were kept as crit bonuses, Dwarf gun and Troll bow/thrown removed; one commenter claims a Dwarf mace crit racial. None grant weapon skill, so weapon_skill is {} everywhere
- Skyborne class list: both sources agree (A: Warrior Hunter Rogue Mage Druid; H: Warrior Hunter Rogue Shaman Druid); one search snippet (allthings.how) suggested identical lists, outvoted by warcraftdb + Blizzard API
- Blizzard spec names differ from Era: Priest 'Shadow Magic', Shaman 'Elemental Combat', Druid single 'Feral Combat' tree - spec keys kept as Era
- Rulesets (from coordinator, not in classes.json): 1 PvP, 2 Normal, 3 Roleplay, 15 Roleplay PvP (dynamic-forever-eu /ruleset/{id}).

## Open questions
1. Instance zone/area ids for the 9 new dungeons and the raids: not available in QuestieDB or warcraftdb or the Blizzard journal API.
2. Forever level ranges for returning dungeons: only Warcraft Tavern gives them.
3. Whether Hall of Thanes / Ruins of Lordaeron are faction-restricted; UBRS group size; Orc Axe / Human Sword crit racials present or not.
4. Weapon/armor proficiency changes: none found, Era values kept.
