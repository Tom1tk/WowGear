# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
WoW Forever players, both mid-session (alt-tabbed while levelling: "what is my next upgrade and where do I get it?") and between sessions (planning across levels, specs and raid tiers). Both uses matter equally (owner, 2026-11-18).

## Product Purpose
Shows the best PvE gear for every level from 10 to 60 for each class/spec/faction in WoW Forever, and where to get each item. A character lookup (region + first name + surname, Blizzard API) compares what the character wears with the best picks and lists upgrades grouped by where to go.

## Positioning
Built for Forever specifically: new items, dungeons, races (Skyborne) and rulesets; data cross-referenced across Blizzard (source of truth), warcraftdb and ForeverDB, with disagreements shown openly as "Uncertain" instead of hidden.

## Operating Context
Used next to the game client, often on the same 16:9 desktop screen; also on phones. Item names link to Wowhead Forever tooltips. Shareable URLs restore level, tier, spec and character.

## Capabilities and Constraints
- Static frontend (vanilla HTML/CSS/JS in frontend/) on Vercel; small FastAPI backend for lookup and scoring. No build step.
- Manual mode (pick race/class/spec/level) works without a lookup.
- Levels 10-60; level 60 has tiers (Pre-raid, Raid tier 1 from 9 Dec 2026).
- Data is incomplete and changing; "Uncertain" and "1 source" marks must stay visible and honest.
- Gear data per spec/faction is pre-built JSON (frontend/data/).

## Brand Commitments
Name "WowGear Forever". Owner's call (2026-11-18): first screen must show the top Best-gear rows and the first What-to-do-next entries at 1920x1080 without scrolling; once a character is loaded the lookup form collapses, the character shows as a compact summary, and the level slider may be collapsed by default.

## Evidence on Hand
Real item data in frontend/data/. Race background art in frontend/bg/ (© Blizzard). No testimonials or usage numbers; do not invent any.

## Product Principles
1. The next upgrade first: the answer the player came for is visible without scrolling.
2. Honest data: uncertainty is shown, never smoothed over.
3. Dense but calm: compact rows, no space spent on chrome.
4. Works with or without a character lookup.
