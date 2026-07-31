const form = document.getElementById("analyze-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const specSelect = document.getElementById("spec");
const realmSelect = document.getElementById("realm");
const regionSelect = document.getElementById("region");

const REALM_STORAGE_KEY = "wowgear:realm";

const CATEGORY_LABELS = {
  gear: "Gear",
  upgrade: "Upgrade",
  craft: "Craft",
  catchup: "Catch up",
};

function showStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.hidden = false;
  statusEl.classList.toggle("error", isError);
}

function hideStatus() {
  statusEl.hidden = true;
}

// Top loading bar: fills slowly while a request is in flight, snaps to
// 100% and fades out when it completes.
const topBar = document.getElementById("top-bar");
let loadingActive = false;
let loadingResetTimer = null;

function setLoading(on) {
  if (on && !loadingActive) {
    loadingActive = true;
    clearTimeout(loadingResetTimer);
    topBar.classList.add("active");
    topBar.style.transition = "none";
    topBar.style.width = "0%";
    requestAnimationFrame(() => {
      topBar.style.transition = "width 45s linear";
      topBar.style.width = "90%";
    });
  } else if (!on && loadingActive) {
    loadingActive = false;
    topBar.style.transition = "width 0.25s ease";
    topBar.style.width = "100%";
    loadingResetTimer = setTimeout(() => {
      topBar.classList.remove("active");
      topBar.style.width = "0%";
    }, 450);
  }
}

async function loadSpecs() {
  try {
    const resp = await fetch("/api/specs");
    const classes = await resp.json();
    for (const [className, data] of Object.entries(classes)) {
      const group = document.createElement("optgroup");
      group.label = className;
      for (const spec of data.specs) {
        const option = document.createElement("option");
        option.value = spec.slug;
        option.textContent = spec.name;
        group.appendChild(option);
      }
      specSelect.appendChild(group);
    }
  } catch {
    // spec dropdown is optional; auto-detect still works
  }
}

function slotDeltaClass(gap) {
  if (gap === null || gap === undefined) return "";
  if (gap <= 0) return "ok";
  if (gap < 15) return "warn";
  return "bad";
}

const QUALITY_COLORS = {
  Poor: "#9d9d9d",
  Common: "#ffffff",
  Uncommon: "#1eff00",
  Rare: "#0070dd",
  Epic: "#a335ee",
  Legendary: "#ff8000",
  Artifact: "#e6cc80",
  Heirloom: "#00ccff",
};

function qualityColor(quality) {
  return QUALITY_COLORS[quality] ?? "#ffffff";
}

const SLOT_SHORT = {
  head: "HEAD", neck: "NECK", shoulders: "SHOULD", back: "BACK",
  chest: "CHEST", wrist: "WRIST", hands: "HANDS", waist: "WAIST",
  legs: "LEGS", feet: "FEET", ring_1: "RING 1", ring_2: "RING 2",
  trinket_1: "TRINKET 1", trinket_2: "TRINKET 2",
  main_hand: "MAIN HAND", off_hand: "OFF HAND",
};

// Paperdoll layout mirrors the retail character frame (verified against the
// game's PaperDollFrame.xml): left column head→wrist, right column
// hands→waist→legs→feet→rings→trinkets, weapons on a bottom row beneath the
// character render. Shirt/tabard slots are omitted (no data for them).
const PAPERDOLL_COLUMNS = {
  left: ["head", "neck", "shoulders", "back", "chest", "wrist"],
  right: ["hands", "waist", "legs", "feet", "ring_1", "ring_2", "trinket_1", "trinket_2"],
  bottom: ["main_hand", "off_hand"],
};

function renderCharacter(summary) {
  const parts = [
    summary.name,
    `@${summary.realm}`,
    summary.region.toUpperCase(),
  ];
  if (summary.faction) parts.push(summary.faction);
  const sub = [
    summary.race,
    summary.class_name,
    summary.spec ? `${summary.spec} (${summary.level})` : `Level ${summary.level}`,
  ].filter(Boolean).join(" · ");
  const stats = [
    `Avg ilvl ${summary.average_item_level ?? "—"}`,
    `Achievements ${summary.achievement_points ?? "—"}`,
    summary.mythic_plus_rating ? `Mythic+ ${summary.mythic_plus_rating}` : null,
  ].filter(Boolean).join("  ·  ");

  const card = document.getElementById("character-card");
  card.innerHTML = `
    <div class="char-info">
      <h2>${parts.join(" ")}</h2>
      <p class="sub">${sub}</p>
      <p class="stats">${stats}</p>
    </div>
    <div class="equipment" id="equipment-grid"></div>
  `;
}

function makeItemCell(slot, bySlot, bisMaxIlvl) {
  const comparison = bySlot.get(slot);
  const equipped = comparison?.equipped;
  const bis = comparison?.bis;
  const cell = document.createElement("div");
  cell.className = "item-cell";
  if (equipped) {
    if (comparison.status === "upgrade" || comparison.status === "empty") {
      cell.classList.add("needs-upgrade");
    } else if (comparison.status === "match") {
      cell.classList.add("matched");
    }
    cell.dataset.slot = slot;
    cell.dataset.slotLabel = comparison.slot_label;
    cell.dataset.itemName = equipped.name;
    cell.dataset.itemIlvl = equipped.ilvl;
    cell.dataset.itemQuality = equipped.quality ?? "";
    cell.dataset.enchant = equipped.enchant ?? "";
    cell.dataset.bisName = bis ? bis.name : "";
    cell.dataset.bisIlvl = bis ? (bis.ilvl || bisMaxIlvl) : "";
    cell.dataset.status = comparison.status;

    const icon = document.createElement("img");
    icon.className = "item-icon";
    icon.src = equipped.icon_url || "";
    icon.alt = equipped.name;
    if (!equipped.icon_url) {
      icon.classList.add("icon-fallback");
      icon.alt = SLOT_SHORT[slot] ?? slot;
      icon.src = "";
    }
    cell.appendChild(icon);

    if (comparison.status === "upgrade" || comparison.status === "empty") {
      const marker = document.createElement("span");
      marker.className = "upgrade-marker";
      marker.textContent = "▲";
      cell.appendChild(marker);
    }
    const ilvlBadge = document.createElement("span");
    ilvlBadge.className = "ilvl-badge";
    ilvlBadge.textContent = equipped.ilvl;
    cell.appendChild(ilvlBadge);
  } else {
    cell.classList.add("empty-slot");
    cell.textContent = SLOT_SHORT[slot] ?? slot;
  }
  return cell;
}

function renderEquipment(comparisons, bisMaxIlvl, renderUrl, avatarUrl) {
  const grid = document.getElementById("equipment-grid");
  grid.innerHTML = "";
  const bySlot = new Map(comparisons.map((c) => [c.slot, c]));
  const tooltip = document.getElementById("tooltip");

  const portrait = document.createElement("div");
  portrait.className = "pd-portrait";
  const img = document.createElement("img");
  img.alt = "";
  const applySource = (src) => {
    img.src = src;
    img.onerror = () => {
      if (renderUrl && avatarUrl && img.src === renderUrl) {
        applySource(avatarUrl);
      } else {
        img.remove();
      }
    };
  };
  if (renderUrl || avatarUrl) {
    portrait.appendChild(img);
    applySource(renderUrl || avatarUrl);
  }
  grid.appendChild(portrait);

  const leftCol = document.createElement("div");
  leftCol.className = "pd-col pd-left";
  const rightCol = document.createElement("div");
  rightCol.className = "pd-col pd-right";
  for (const slot of PAPERDOLL_COLUMNS.left) {
    leftCol.appendChild(makeItemCell(slot, bySlot, bisMaxIlvl));
  }
  for (const slot of PAPERDOLL_COLUMNS.right) {
    rightCol.appendChild(makeItemCell(slot, bySlot, bisMaxIlvl));
  }
  grid.append(leftCol, rightCol);

  const weapons = document.createElement("div");
  weapons.className = "pd-col pd-weapons";
  for (const slot of PAPERDOLL_COLUMNS.bottom) {
    weapons.appendChild(makeItemCell(slot, bySlot, bisMaxIlvl));
  }
  grid.appendChild(weapons);

  grid.querySelectorAll(".item-cell[data-slot]").forEach((cell) => {
    cell.addEventListener("mouseenter", (event) => {
      const d = cell.dataset;
      const status = {
        match: "✓ BiS match",
        upgrade: "▲ needs upgrade",
        ahead: "✓ above BiS ilvl",
        empty: "✗ empty",
      }[d.status] ?? "";
      let html = `
        <div class="tt-name" style="color:${qualityColor(d.itemQuality)}">${d.itemName}</div>
        <div class="tt-line">Item level ${d.itemIlvl}</div>
      `;
      if (d.enchant) html += `<div class="tt-line">${d.enchant}</div>`;
      if (d.bisName) {
        html += `<div class="tt-bis">BiS: ${d.bisName} (${d.bisIlvl})</div>`;
      }
      if (status) html += `<div class="tt-status">${status}</div>`;
      tooltip.innerHTML = html;
      tooltip.hidden = false;
      positionTooltip(tooltip, event.clientX, event.clientY);
    });
    cell.addEventListener("mousemove", (event) => {
      positionTooltip(tooltip, event.clientX, event.clientY);
    });
    cell.addEventListener("mouseleave", () => {
      tooltip.hidden = true;
    });
  });
}

function positionTooltip(tooltip, x, y) {
  const pad = 14;
  tooltip.style.left = `${x + pad}px`;
  tooltip.style.top = `${y + pad}px`;
  const rect = tooltip.getBoundingClientRect();
  if (rect.right > window.innerWidth - 8) {
    tooltip.style.left = `${x - rect.width - pad}px`;
  }
  if (rect.bottom > window.innerHeight - 8) {
    tooltip.style.top = `${y - rect.height - pad}px`;
  }
}

function renderActions(actions) {
  const list = document.getElementById("action-list");
  list.innerHTML = "";
  if (actions.length === 0) {
    const li = document.createElement("li");
    li.className = "action done";
    li.textContent = "Nothing to do — you're already at (or above) BiS for every slot.";
    list.appendChild(li);
    return;
  }
  for (const action of actions) {
    const li = document.createElement("li");
    li.className = `action ${action.category}`;
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = CATEGORY_LABELS[action.category] ?? action.category;
    const title = document.createElement("div");
    title.className = "action-title";
    title.textContent = action.title;
    const detail = document.createElement("div");
    detail.className = "action-detail";
    detail.textContent = action.detail;
    li.append(badge, title, detail);
    list.appendChild(li);
  }
}

let comparisonSortAsc = false;
const sortToggle = document.getElementById("sort-toggle");
let lastComparisons = null;
let lastBisMaxIlvl = null;

function sortedComparisons(comparisons) {
  return [...comparisons].sort((a, b) => {
    const gapA = a.ilvl_gap ?? -1;
    const gapB = b.ilvl_gap ?? -1;
    return comparisonSortAsc ? gapA - gapB : gapB - gapA;
  });
}

function renderComparison(comparisons, bisMaxIlvl) {
  lastComparisons = comparisons;
  lastBisMaxIlvl = bisMaxIlvl;
  sortToggle.textContent = comparisonSortAsc
    ? "Smallest Δ first"
    : "Biggest Δ first";
  const tbody = document.querySelector("#comparison-table tbody");
  tbody.innerHTML = "";
  for (const row of sortedComparisons(comparisons)) {
    const tr = document.createElement("tr");
    const equippedName = row.equipped ? `${row.equipped.name}` : "—";
    const equippedIlvl = row.equipped ? `${row.equipped.ilvl}` : "—";
    const bisName = row.bis ? `${row.bis.name}` : "—";
    const bisIlvl = row.bis ? `${row.bis.ilvl || bisMaxIlvl}` : "—";
    const gap = row.ilvl_gap !== null && row.ilvl_gap !== undefined
      ? (row.ilvl_gap > 0 ? `+${row.ilvl_gap}` : "0")
      : "—";
    const status = {
      match: "✓ match",
      upgrade: "▲ upgrade",
      ahead: "✓ ahead",
      empty: "✗ empty",
      no_bis: "—",
    }[row.status] ?? row.status;

    tr.innerHTML = `
      <td class="slot">${row.slot_label}</td>
      <td>${equippedName}</td>
      <td>${equippedIlvl}</td>
      <td class="bis-name">${bisName}</td>
      <td>${bisIlvl}</td>
      <td class="delta ${slotDeltaClass(row.ilvl_gap)}">${gap}</td>
      <td class="status">${status}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderFarmTips(tips) {
  const container = document.getElementById("farm-tips");
  container.innerHTML = "";
  for (const tip of tips) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = tip.title.replace("?", "");
    const text = document.createElement("p");
    text.textContent = tip.text;
    details.append(summary, text);
    container.appendChild(details);
  }
  if (tips.length === 0) {
    container.textContent = "No farm tips available on this guide page.";
  }
}

sortToggle.addEventListener("click", () => {
  comparisonSortAsc = !comparisonSortAsc;
  if (lastComparisons) renderComparison(lastComparisons, lastBisMaxIlvl);
});

async function analyze(event) {
  event.preventDefault();
  hideStatus();
  setLoading(true);
  resultsEl.hidden = false;
  const skeletons = document.getElementById("skeletons");
  const resultsLayout = document.getElementById("results-layout");
  skeletons.hidden = false;
  resultsLayout.hidden = true;
  const button = document.getElementById("analyze-btn");
  button.disabled = true;

  const payload = {
    region: document.getElementById("region").value,
    realm: document.getElementById("realm").value,
    character: document.getElementById("character").value,
    spec: document.getElementById("spec").value || null,
  };

  try {
    const resp = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || `Request failed (HTTP ${resp.status})`);
    }
    skeletons.hidden = true;
    resultsLayout.hidden = false;
    renderCharacter(data.character);
    renderEquipment(data.comparisons, data.bis_max_ilvl, data.character.render_url, data.character.avatar_url);
    renderActions(data.actions);
    renderComparison(data.comparisons, data.bis_max_ilvl);
    renderFarmTips(data.farm_tips);
    const source = document.getElementById("source-link");
    const dataSource = data.source === "armory"
      ? "Armory (Blizzard API unavailable for this key — check API Access at develop.battle.net)"
      : "Blizzard API";
    source.innerHTML = `Data: ${dataSource}. BiS list: <a href="${data.bis_url}" target="_blank" rel="noopener">${data.spec_label} on Icy Veins</a>`;
    hideStatus();
    resultsEl.hidden = false;
  } catch (err) {
    showStatus(err.message, true);
    resultsEl.hidden = true;
  } finally {
    setLoading(false);
    button.disabled = false;
  }
}

async function loadRealms(region, preferredSlug) {
  let loaded = false;
  try {
    const resp = await fetch(`/api/realms?region=${encodeURIComponent(region)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    realmSelect.innerHTML = "";
    for (const realm of data.realms) {
      const option = document.createElement("option");
      option.value = realm.slug;
      option.textContent = realm.name;
      realmSelect.appendChild(option);
    }
    loaded = true;
  } catch {
    // Keep whatever list we have; if empty, show a placeholder option.
    if (realmSelect.options.length === 0) {
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "— select realm —";
      realmSelect.appendChild(option);
    }
  }
  const stored = preferredSlug || localStorage.getItem(REALM_STORAGE_KEY) || "draenor";
  let match = [...realmSelect.options].find((option) => option.value === stored);
  if (!match && stored) {
    const option = document.createElement("option");
    option.value = stored;
    option.textContent = stored;
    realmSelect.appendChild(option);
    match = option;
  }
  realmSelect.value = match ? match.value : (realmSelect.options[0]?.value ?? "");
  return loaded;
}

regionSelect.addEventListener("change", () => {
  const region = regionSelect.value;
  loadRealms(region, localStorage.getItem(REALM_STORAGE_KEY) || "");
});

realmSelect.addEventListener("change", () => {
  localStorage.setItem(REALM_STORAGE_KEY, realmSelect.value);
});

form.addEventListener("submit", analyze);
loadSpecs();
loadRealms("eu");
