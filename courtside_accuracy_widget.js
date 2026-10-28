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

    const scoredKeys = new Set(results.map(r =>
      String(r.game_key) + "|" + String(r.player_id)
    ));

    const pending = history.filter(r => !scoredKeys.has(
      String(r.game_key) + "|" + String(r.player_id)
    ));

    const upcoming = pending.filter(r => {
      const tip = Date.parse(r.tipoff_utc);
      return Number.isFinite(tip) && tip > Date.now();
    });

    const awaiting = pending.length - upcoming.length;
    const count = results.length;

    const adjusted = results.filter(row =>
      !["1", "yes", "true"].includes(
        String(row.injury_excluded ?? "").trim().toLowerCase()
      )
    );

    const excludedCount = count - adjusted.length;

    const mae = (rows, key, prefix) => {
      const errors = rows.map(row => {
        const predicted = Number(row[prefix + key]);
        const actual = Number(row["actual_" + key]);

        return Number.isFinite(predicted) &&
          Number.isFinite(actual)
          ? Math.abs(predicted - actual)
          : null;
      }).filter(value => value !== null);

      return errors.length
        ? (
            errors.reduce((a, b) => a + b, 0) /
            errors.length
          ).toFixed(2)
        : "—";
    };

    let html = `
      <h2>Prediction Accuracy & History</h2>

      <p class="small">
        Pregame estimates are saved once and never overwritten.
        Only completed player games with matching ESPN logs
        are scored. Lower MAE is better.
        Current-season model; not a validated forecast.
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

        <p class="small">
          Injury-adjusted sample:
          ${adjusted.length} player-games.

          In-game injury exclusions:
          ${excludedCount}.

          Exclusions include automatically detected
          recap matches and manually confirmed cases.
        </p>

        <div class="tablewrap" style="overflow-x:auto">
          <table>
            <thead>
              <tr>
                <th>Stat</th>
                <th>Overall MAE</th>
                <th>Injury-adjusted MAE</th>
                <th>Season-average MAE</th>
                <th>Adjusted season-average MAE</th>
              </tr>
            </thead>

            <tbody>
      `;

      for (const [key, label] of stats) {
        html += `
          <tr>
            <td>${escapeHTML(label)}</td>
            <td>${mae(results, key, "pred_")}</td>
            <td>${mae(adjusted, key, "pred_")}</td>
            <td>${mae(results, key, "baseline_")}</td>
            <td>${mae(adjusted, key, "baseline_")}</td>
          </tr>
        `;
      }

      html += `
            </tbody>
          </table>
        </div>

        <p class="small">
          Lower MAE is better.

          Injury-adjusted MAE excludes player-games
          marked in nba_in_game_injuries.csv.

          Both metrics use completed player logs.

          Exclusions do not change saved pregame predictions
          or historical ranges.
        </p>
      `;
    } else {
      html += `
        <p class="small">
          No scored results yet.

          Scores appear after saved pregame estimates
          can be matched to completed ESPN player logs.
        </p>
      `;
    }

    const tracker = document.getElementById("cs-prediction-tracker");

    if (tracker) {
      const latest = [...history].sort((a, b) =>
        String(b.tipoff_utc).localeCompare(String(a.tipoff_utc))
      ).slice(0, 30);

      tracker.className = "panel";

      tracker.innerHTML = `
        <h2>Prediction Tracker</h2>

        <div class="cards">
          ${[
            ["Saved", history.length],
            ["Scored", results.length],
            ["Pending", pending.length],
            ["Upcoming", upcoming.length],
            ["Awaiting box scores", awaiting],
            ["Injury exclusions", excludedCount]
          ].map(([label, value]) => `
            <div class="card">
              <div class="label">${escapeHTML(label)}</div>
              <div class="value">${escapeHTML(value)}</div>
            </div>
          `).join("")}
        </div>

        <p class="small">
          Awaiting box scores also includes unmatched or
          otherwise unscorable past predictions.
        </p>

        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Game date</th>
                <th>Opponent</th>
                <th>Predicted PTS</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              ${latest.map(r => `
                <tr>
                  <td>${escapeHTML(r.player_name)}</td>
                  <td>${escapeHTML(r.game_date)}</td>
                  <td>${escapeHTML(r.opponent)}</td>
                  <td>${escapeHTML(r.pred_points)}</td>
                  <td>
                    ${scoredKeys.has(
                      String(r.game_key) + "|" + String(r.player_id)
                    ) ? "Scored" : "Pending"}
                  </td>
                </tr>
              `).join("") ||
                '<tr><td colspan="5">No predictions saved yet.</td></tr>'}
            </tbody>
          </table>
        </div>
      `;
    }

    root.innerHTML = html;

  } catch (error) {
    root.innerHTML = `
      <h2>Prediction Accuracy & History</h2>

      <p class="small">
        ${escapeHTML(error.message)}.

        Run the updated GitHub Actions workflow
        to create the required CSV files.
      </p>
    `;
  }
})();
