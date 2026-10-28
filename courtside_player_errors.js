
/* Courtside — Expandable Player Prediction Errors */

(async function () {
  "use strict";
  // Clean slate: retain old CSV records, but only show new forecasts from Oct 28, 2026 (Chicago time).
  const CS_RESET_UTC = Date.parse("2026-10-28T05:00:00Z");
  function csFresh(r) {
    const gameDate = String(r.game_date || "").slice(0, 10);
    if (gameDate && gameDate < "2026-10-28") return false;
    const saved = Date.parse(r.saved_utc || "");
    if (Number.isFinite(saved)) return saved >= CS_RESET_UTC;
    // Rows lacking a saved timestamp cannot be proven to be new.
    return false;
  }


  const BASE =
    "https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/";

  const root = document.getElementById("cs-player-errors");
  const content = document.getElementById("cs-error-content");
  const search = document.getElementById("cs-error-search");

  if (!root || !content || !search) return;

  const stats = [
    ["points", "PTS"],
    ["rebounds", "REB"],
    ["assists", "AST"],
    ["three_pointers", "3PM"],
    ["steals", "STL"],
    ["blocks", "BLK"]
  ];

  function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[c]);
  }

  function parseCSV(text) {
    const rows = [];
    let row = [], cell = "", quoted = false;

    for (let i = 0; i < text.length; i++) {
      const c = text[i];

      if (c === '"') {
        if (quoted && text[i + 1] === '"') {
          cell += '"';
          i++;
        } else {
          quoted = !quoted;
        }
      } else if (c === "," && !quoted) {
        row.push(cell);
        cell = "";
      } else if ((c === "\n" || c === "\r") && !quoted) {
        if (c === "\r" && text[i + 1] === "\n") i++;
        row.push(cell);
        if (row.some(v => v !== "")) rows.push(row);
        row = [];
        cell = "";
      } else {
        cell += c;
      }
    }

    if (cell || row.length) {
      row.push(cell);
      rows.push(row);
    }

    const headers = (rows.shift() || [])
      .map(h => h.replace(/^\uFEFF/, ""));

    return rows.map(values =>
      Object.fromEntries(
        headers.map((h, i) => [h, values[i] ?? ""])
      )
    );
  }

  function number(value) {
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
  }

  function format(value) {
    const n = number(value);
    return n === null ? "—" : n.toFixed(1);
  }

  function difference(predicted, actual) {
    const p = number(predicted);
    const a = number(actual);

    if (p === null || a === null) return "—";

    const d = p - a;

    return (d > 0 ? "+" : "") + d.toFixed(1);
  }

  function statTable(player) {
    return `
      <div class="scroll">
        <table>
          <thead>
            <tr>
              <th>Stat</th>
              <th>Predicted</th>
              <th>Actual</th>
              <th>Difference</th>
            </tr>
          </thead>
          <tbody>
            ${stats.map(([key, label]) => `
              <tr>
                <td>${label}</td>
                <td>${format(player["pred_" + key])}</td>
                <td>${format(player["actual_" + key])}</td>
                <td>${difference(
                  player["pred_" + key],
                  player["actual_" + key]
                )}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    `;
  }

  function playerCard(player) {
    const excluded = ["1", "yes", "true"].includes(
      String(player.injury_excluded || "").toLowerCase()
    );

    return `
      <details style="
        margin:10px 0;
        padding:14px;
        background:#172134;
        border:1px solid #293449;
        border-radius:10px;
      ">
        <summary style="cursor:pointer;font-weight:700;">
          ${esc(player.player_name)}
          · ${esc(player.team)} vs ${esc(player.opponent)}
          · ${esc(player.game_date)}
          ${excluded ? " · Injury excluded" : ""}
        </summary>

        <div style="margin-top:14px;">
          ${statTable(player)}
          ${excluded ? `
            <p class="small">
              Excluded from injury-adjusted MAE.
            </p>
          ` : ""}
        </div>
      </details>
    `;
  }

  let players = [];

  function render() {
    const query = search.value.trim().toLowerCase();

    const filtered = players.filter(player =>
      String(player.player_name || "")
        .toLowerCase().includes(query)
    );

    content.innerHTML = `
      <p class="small">
        Showing ${filtered.length} of ${players.length}
        scored player-games.
        Difference = prediction minus actual.
        Positive means overpredicted.
      </p>

      ${filtered.map(playerCard).join("") ||
        '<p class="small">No matching players found.</p>'}
    `;
  }

  search.addEventListener("input", render);

  try {
    const response = await fetch(
      BASE + "nba_prediction_results.csv?t=" + Date.now(),
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw Error("Could not load prediction results.");
    }

    players = parseCSV(await response.text()).filter(csFresh);

    players.sort((a, b) =>
      String(b.game_date).localeCompare(String(a.game_date)) ||
      String(a.player_name).localeCompare(String(b.player_name))
    );

    render();

  } catch (error) {
    content.textContent = error.message;
  }
})();
