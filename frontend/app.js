const form = document.getElementById("analyze-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const specSelect = document.getElementById("spec");

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
    <h2>${parts.join(" ")}</h2>
    <p class="sub">${sub}</p>
    <p class="stats">${stats}</p>
  `;
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

function renderComparison(comparisons, bisMaxIlvl) {
  const tbody = document.querySelector("#comparison-table tbody");
  tbody.innerHTML = "";
  for (const row of comparisons) {
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

async function analyze(event) {
  event.preventDefault();
  hideStatus();
  resultsEl.hidden = true;
  const button = document.getElementById("analyze-btn");
  button.disabled = true;
  showStatus("Fetching character + BiS data…");

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
    renderCharacter(data.character);
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
  } finally {
    button.disabled = false;
  }
}

form.addEventListener("submit", analyze);
loadSpecs();
