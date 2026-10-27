
/* Courtside accuracy dashboard: saved pregame forecasts and MAE. */
(async function () {
  "use strict";

  const BASE =
    "https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/";

  const stats = [
    ["points", "PTS"],
    ["rebounds", "REB"],
    ["assists", "AST"],
    ["three_pointers", "3PM"],
    ["steals", "STL"],
    ["blocks", "BLK"]
  ];

  function escapeHTML(value) {
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
    let row = [];
    let cell = "";
    let quoted = false;

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
        if (row.some(Boolean)) rows.push(row);
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

  async function load(file) {
    const response = await fetch(
      BASE + file + "?v=" + Date.now(),
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw Error(file + " not published yet");
    }

    return parseCSV(await response.text());
  }

  const root = document.createElement("section");
  root.id = "cs-accuracy";
  root.className = "section panel";

  root.innerHTML = `
    <h2>Prediction Accuracy & History</h2>
    <p class="small">Loading accuracy data...</p>
  `;

  const anchor = document.querySelector("#cs-schedule");

  if (anchor) {
    anchor.after(root);
  } else {
    (document.querySelector(".wrap") || document.body)
      .appendChild(root);
  }

  try {
    const [history, results] = await Promise.all([
      load("nba_prediction_history.csv"),
      load("nba_prediction_results.csv")
    ]);

    const count = results.length;

    let html = `
      <h2>Prediction Accuracy & History</h2>

      <p class="small">
        Pregame estimates are saved once and never overwritten.
        Only completed player games with matching ESPN logs
        are scored. Lower MAE is better. Current-season model;
        not a validated forecast.
      </p>
    `;

    if (!history.length) {
      html += `
        <p class="small">
          No snapshots yet. The updater saves them before
          upcoming games, then scores them after ESPN
          publishes results.
        </p>
      `;
    }

    if (count > 0) {
      html += `
        <h3>
          Mean absolute error (MAE) · ${count} player-games
        </h3>

        <div class="tablewrap" style="overflow-x:auto">
          <table>
            <thead>
              <tr>
                <th>Stat</th>
                <th>Courtside MAE</th>
                <th>Season-average MAE</th>
                <th>Difference</th>
              </tr>
            </thead>
            <tbody>
      `;

      for (const [key, label] of stats) {
        const model = results.reduce((sum, row) =>
          sum + Math.abs(
            Number(row["pred_" + key]) -
            Number(row["actual_" + key])
          ), 0) / count;

        const baseline = results.reduce((sum, row) =>
          sum + Math.abs(
            Number(row["baseline_" + key]) -
            Number(row["actual_" + key])
          ), 0) / count;

        const difference = model - baseline;

        html += `
          <tr>
            <td>${escapeHTML(label)}</td>
            <td>${model.toFixed(2)}</td>
            <td>${baseline.toFixed(2)}</td>
            <td>${difference.toFixed(2)}</td>
          </tr>
        `;
      }

      html += `
            </tbody>
          </table>
        </div>

        <p class="small">
          Negative difference means the Courtside model
          had lower error than the season-average baseline.
          These results cover only players with a completed
          game log, not players who did not play.
        </p>
      `;
    } else {
      html += `
        <p class="small">
          No scored results yet. Scores appear after saved
          pregame estimates can be matched to completed
          ESPN player logs.
        </p>
      `;
    }

    root.innerHTML = html;

  } catch (error) {
    root.innerHTML = `
      <h2>Prediction Accuracy & History</h2>
      <p class="small">
        ${escapeHTML(error.message)}.
        Run the updated GitHub Actions workflow to
        create the required CSV files.
      </p>
    `;
  }
})();
