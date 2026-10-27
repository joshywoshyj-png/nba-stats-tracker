/* ============================================================
   COURTSIDE — NBA SCHEDULE & MATCHUP PREDICTOR
   Current-season stats, opponent defense, pace, injuries

   Shows:
   - All games scheduled for today, including live games
   - All future scheduled games
   - Player estimates for PTS, REB, AST, 3PM, STL, BLK

   Today's games remain visible until local midnight.
   ============================================================ */

(async function () {
  "use strict";

  const BASE =
    "https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/";

  const STATS = [
    "points",
    "rebounds",
    "assists",
    "three_pointers",
    "steals",
    "blocks"
  ];

  const LABELS = ["PTS", "REB", "AST", "3PM", "STL", "BLK"];

  const number = value => {
    const result = Number(value);
    return Number.isFinite(result) ? result : 0;
  };

  const clamp = (value, minimum, maximum) =>
    Math.max(minimum, Math.min(maximum, value));

  const escapeHTML = value =>
    String(value ?? "").replace(
      /[&<>"']/g,
      character => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      })[character]
    );

  const normalizeName = value =>
    String(value || "")
      .toLowerCase()
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z]/g, "");

  const positionGroup = position => {
    const p = String(position || "").toUpperCase();

    if (["PG", "SG", "G"].includes(p)) return "G";
    if (["SF", "PF", "F"].includes(p)) return "F";
    if (p === "C") return "C";
    if (["G-F", "F-G", "GF"].includes(p)) return "G-F";
    if (["F-C", "C-F", "FC"].includes(p)) return "F-C";

    return "";
  };

  // ----------------------------------------------------------
  // CSV PARSER
  // ----------------------------------------------------------

  function parseCSV(text) {
    const rows = [];
    let row = [];
    let value = "";
    let quoted = false;

    for (let i = 0; i < text.length; i++) {
      const character = text[i];

      if (character === '"') {
        if (quoted && text[i + 1] === '"') {
          value += '"';
          i++;
        } else {
          quoted = !quoted;
        }
      } else if (character === "," && !quoted) {
        row.push(value);
        value = "";
      } else if (
        (character === "\n" || character === "\r") &&
        !quoted
      ) {
        if (character === "\r" && text[i + 1] === "\n") {
          i++;
        }

        row.push(value);

        if (row.some(item => item !== "")) {
          rows.push(row);
        }

        row = [];
        value = "";
      } else {
        value += character;
      }
    }

    if (row.length || value) {
      row.push(value);
      rows.push(row);
    }

    const headers = rows.shift() || [];

    return rows.map(values =>
      Object.fromEntries(
        headers.map((header, index) => [
          header,
          values[index] ?? ""
        ])
      )
    );
  }

  async function loadCSV(filename) {
    const response = await fetch(
      BASE + filename + "?v=" + Date.now(),
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw new Error(
        filename + " could not load (HTTP " +
        response.status + ")"
      );
    }

    return parseCSV(await response.text());
  }

  // ----------------------------------------------------------
  // STYLING
  // ----------------------------------------------------------

  const style = document.createElement("style");

  style.textContent = `
    #cs-schedule {
      font: 14px system-ui, sans-serif;
      background: #14171f;
      color: #f5f6fa;
      border: 1px solid #353944;
      border-radius: 18px;
      padding: 22px;
      margin: 24px auto;
      max-width: 1200px;
    }

    #cs-schedule h2 {
      margin: 0 0 8px;
      font-size: 25px;
    }

    #cs-schedule select {
      background: #202530;
      color: white;
      border: 1px solid #555;
      border-radius: 8px;
      padding: 10px;
      width: 100%;
      max-width: 100%;
      margin: 12px 0;
    }

    #cs-schedule table {
      border-collapse: collapse;
      width: 100%;
      min-width: 1000px;
    }

    #cs-schedule td,
    #cs-schedule th {
      text-align: left;
      border-bottom: 1px solid #343844;
      padding: 10px;
    }

    #cs-schedule th {
      color: #d5d7df;
    }

    #cs-schedule .scroll {
      overflow-x: auto;
    }

    #cs-schedule .muted {
      color: #b3b9c6;
      line-height: 1.5;
    }

    #cs-schedule .inj {
      color: #ffb0b0;
    }

    #cs-schedule .error {
      color: #ff6868;
    }

    #cs-schedule .game-label {
      display: block;
      font-weight: 600;
      margin-top: 14px;
    }
  `;

  document.head.appendChild(style);

  // ----------------------------------------------------------
  // CREATE WIDGET
  // ----------------------------------------------------------

  let root = document.getElementById("cs-schedule");

  if (!root) {
    root = document.createElement("section");
    root.id = "cs-schedule";

    (document.querySelector("main") || document.body)
      .appendChild(root);
  }

  root.innerHTML = `
    <h2>NBA Schedule & Matchup Stats</h2>
    <p class="muted">
      Loading games, player stats, pace, and injuries...
    </p>
  `;

  try {
    // --------------------------------------------------------
    // LOAD DATA
    // --------------------------------------------------------

    const [
      schedule,
      players,
      defense,
      logs,
      paceRows,
      injuriesResult
    ] = await Promise.all([
      loadCSV("nba_schedule.csv"),
      loadCSV("nba_stats.csv"),
      loadCSV("nba_opponent_defense.csv"),
      loadCSV("nba_game_logs.csv"),
      loadCSV("nba_team_pace.csv"),
      loadCSV("nba_injuries.csv")
        .then(rows => ({ ok: true, rows }))
        .catch(() => ({ ok: false, rows: [] }))
    ]);

    const injuries = injuriesResult.rows;

    const paceByTeam = new Map(
      paceRows.map(row => [row.team, row])
    );

    // --------------------------------------------------------
    // FIXED SCHEDULE FILTER
    //
    // Compare local calendar dates rather than hours
    // since tipoff. This keeps all of today's games,
    // including live games and games already completed.
    // --------------------------------------------------------

    function localDateKey(value) {
      const date = new Date(value);

      if (!Number.isFinite(date.getTime())) {
        return "";
      }

      const year = date.getFullYear();
      const month = String(date.getMonth() + 1)
        .padStart(2, "0");
      const day = String(date.getDate())
        .padStart(2, "0");

      return `${year}-${month}-${day}`;
    }

    const todayKey = localDateKey(new Date());

    const upcoming = schedule
      .filter(game => {
        const gameKey = localDateKey(game.date_utc);

        return gameKey !== "" && gameKey >= todayKey;
      })
      .sort(
        (a, b) =>
          new Date(a.date_utc).getTime() -
          new Date(b.date_utc).getTime()
      );

    if (!upcoming.length) {
      root.innerHTML = `
        <h2>NBA Schedule & Matchup Stats</h2>
        <p class="muted">
          No games scheduled for today or later were found.
          Check nba_schedule.csv and run your GitHub updater.
        </p>
      `;
      return;
    }

    // --------------------------------------------------------
    // PACE ADJUSTMENT
    // --------------------------------------------------------

    function paceFactor(team, opponent) {
      const own = paceByTeam.get(team);
      const other = paceByTeam.get(opponent);

      if (!own || !other) return 1;

      const ownPace = number(own.adjusted_pace);
      const opponentPace = number(other.adjusted_pace);

      if (ownPace <= 0 || opponentPace <= 0) {
        return 1;
      }

      const expectedPace =
        (ownPace + opponentPace) / 2;

      return clamp(
        expectedPace / ownPace,
        0.90,
        1.10
      );
    }

    function defensePaceCorrection(opponent) {
      const row = paceByTeam.get(opponent);

      if (!row) return 1;

      const leaguePace = number(
        row.league_average_pace
      );

      const opponentPace = number(
        row.adjusted_pace
      );

      if (leaguePace <= 0 || opponentPace <= 0) {
        return 1;
      }

      return clamp(
        leaguePace / opponentPace,
        0.85,
        1.15
      );
    }

    // --------------------------------------------------------
    // DEFENSIVE POSITION AVERAGES
    // --------------------------------------------------------

    const defenseBaselines = {};

    for (const row of defense) {
      const games = number(row.player_games);

      if (games <= 0) continue;

      const key =
        row.position_type + "|" + row.position;

      if (!defenseBaselines[key]) {
        defenseBaselines[key] = {
          games: 0,
          totals: {}
        };
      }

      const baseline = defenseBaselines[key];

      baseline.games += games;

      for (const stat of STATS) {
        baseline.totals[stat] =
          (baseline.totals[stat] || 0) +
          number(row[stat + "_allowed_pg"]) * games;
      }
    }

    function defenseFactor(row, stat, opponent) {
      if (!row) return 1;

      const key =
        row.position_type + "|" + row.position;

      const baseline = defenseBaselines[key];

      if (!baseline || baseline.games <= 0) {
        return 1;
      }

      const leagueAverage =
        baseline.totals[stat] / baseline.games;

      if (leagueAverage <= 0) return 1;

      const games = number(row.player_games);

      let raw =
        number(row[stat + "_allowed_pg"]) /
        leagueAverage;

      if (stat === "points") {
        raw *= defensePaceCorrection(opponent);
      }

      return clamp(
        1 +
          (games / (games + 20)) *
          0.5 *
          (raw - 1),
        0.85,
        1.15
      );
    }

    // --------------------------------------------------------
    // PLAYER GAME LOGS
    // --------------------------------------------------------

    const playerLogs = new Map();

    for (const log of logs) {
      const id = String(log.player_id || "");

      if (!playerLogs.has(id)) {
        playerLogs.set(id, []);
      }

      playerLogs.get(id).push(log);
    }

    for (const entries of playerLogs.values()) {
      entries.sort(
        (a, b) =>
          String(b.date).localeCompare(String(a.date))
      );
    }

    function logMinutes(log) {
      return number(
        log.minutes ||
        log.minutes_played ||
        log.minutes_pg
      );
    }

    // --------------------------------------------------------
    // INJURIES
    // --------------------------------------------------------

    function injuryFor(player) {
      return injuries.find(
        injury =>
          (
            injury.player_id &&
            player.player_id &&
            String(injury.player_id) ===
              String(player.player_id)
          ) ||
          (
            injury.team === player.team &&
            normalizeName(injury.player_name) ===
              normalizeName(player.player_name)
          )
      );
    }

    function isOut(injury) {
      return Boolean(
        injury &&
        /^(out|inactive|injured reserve|suspended|not with team)$/i
          .test(String(injury.status || "").trim())
      );
    }

    // --------------------------------------------------------
    // POINTS FORMULA
    // --------------------------------------------------------

    function pointsRate(player, recent) {
      const seasonMinutes = number(
        player.minutes_pg
      );

      const seasonRate =
        seasonMinutes > 0
          ? number(player.points_pg) / seasonMinutes
          : 0;

      function sampleRate(sample) {
        const valid = sample.filter(
          log =>
            logMinutes(log) > 0 &&
            String(log.points ?? "").trim() !== ""
        );

        const totalMinutes = valid.reduce(
          (sum, log) => sum + logMinutes(log),
          0
        );

        if (totalMinutes <= 0) {
          return seasonRate;
        }

        const totalPoints = valid.reduce(
          (sum, log) => sum + number(log.points),
          0
        );

        return totalPoints / totalMinutes;
      }

      return (
        0.55 * seasonRate +
        0.30 * sampleRate(recent.slice(0, 10)) +
        0.15 * sampleRate(recent.slice(0, 5))
      );
    }

    // --------------------------------------------------------
    // EXISTING FORMULA FOR OTHER STATS
    // --------------------------------------------------------

    function blendedRate(
      seasonRate,
      recentRate,
      seasonGames,
      recentGames
    ) {
      const priorGames = 12;

      const weight =
        seasonGames / (seasonGames + priorGames);

      const stabilized =
        weight * seasonRate +
        (1 - weight) * recentRate;

      const recentWeight =
        recentGames / (recentGames + 10);

      return (
        (1 - recentWeight) * stabilized +
        recentWeight * recentRate
      );
    }

    // --------------------------------------------------------
    // BUILD MATCHUP SELECTOR
    // --------------------------------------------------------

    root.innerHTML = `
      <h2>NBA Schedule & Matchup Stats</h2>

      <p class="muted">
        ESPN schedule · Current-season statistics ·
        Position-specific opponent defense ·
        Matchup pace · Teammate injury adjustments.
        Points use 55% season, 30% last 10, and
        15% last 5 scoring rates.
        Estimates are experimental, not guaranteed
        outcomes.
      </p>

      <label class="game-label" for="cs-game">
        Today's and upcoming games
      </label>

      <select id="cs-game"></select>

      <div id="cs-game-details"></div>
    `;

    const select = root.querySelector("#cs-game");

    upcoming.forEach((game, index) => {
      const option = document.createElement("option");

      option.value = String(index);

      const dateText = new Date(
        game.date_utc
      ).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit"
      });

      option.textContent =
        `${game.away} @ ${game.home} · ${dateText}`;

      select.appendChild(option);
    });

    // --------------------------------------------------------
    // RENDER PLAYER ESTIMATES
    // --------------------------------------------------------

    function render() {
      const game = upcoming[
        Number(select.value) || 0
      ];

      if (!game) return;

      const rows = [];

      for (const [team, opponent] of [
        [game.away, game.home],
        [game.home, game.away]
      ]) {
        const teamPlayers = players.filter(
          player =>
            player.team === team &&
            number(player.games_played) > 0
        );

        const absentPlayers = teamPlayers.filter(
          player => isOut(injuryFor(player))
        );

        const absentMinutes = absentPlayers.reduce(
          (sum, player) =>
            sum + number(player.minutes_pg),
          0
        );

        const availableCount = teamPlayers.filter(
          player => !isOut(injuryFor(player))
        ).length;

        const teammateBoost =
          availableCount > 0
            ? Math.min(
                0.08,
                (absentMinutes / 240) * 0.22
              )
            : 0;

        for (const player of teamPlayers) {
          const injury = injuryFor(player);
          const unavailable = isOut(injury);

          const recent = (
            playerLogs.get(
              String(player.player_id)
            ) || []
          ).slice(0, 10);

          const position =
            recent.find(log => log.position)
              ?.position || "";

          let opponentDefense = defense.find(
            row =>
              row.opponent === opponent &&
              row.position === position &&
              row.position_type === "position"
          );

          if (!opponentDefense) {
            const groupedPosition =
              positionGroup(position);

            opponentDefense = defense.find(
              row =>
                row.opponent === opponent &&
                row.position === groupedPosition &&
                row.position_type ===
                  "position_group"
            );
          }

          const recentMinutes = recent
            .map(logMinutes)
            .filter(value => value > 0);

          const seasonMinutes = number(
            player.minutes_pg
          );

          const recentMinutesAverage =
            recentMinutes.length
              ? recentMinutes.reduce(
                  (sum, value) => sum + value,
                  0
                ) / recentMinutes.length
              : seasonMinutes;

          const projectedMinutes = clamp(
            0.75 * seasonMinutes +
            0.25 * recentMinutesAverage,
            0,
            48
          );

          const seasonGames = number(
            player.games_played
          );

          const estimates = STATS.map(stat => {
            if (unavailable) return "—";

            const seasonRate =
              seasonMinutes > 0
                ? number(
                    player[stat + "_pg"]
                  ) / seasonMinutes
                : 0;

            const validRecent = recent.filter(
              log =>
                logMinutes(log) > 0 &&
                String(log[stat] ?? "").trim() !== ""
            );

            const recentTotal = validRecent.reduce(
              (sum, log) =>
                sum + number(log[stat]),
              0
            );

            const recentTotalMinutes =
              validRecent.reduce(
                (sum, log) =>
                  sum + logMinutes(log),
                0
              );

            const recentRate =
              recentTotalMinutes > 0
                ? recentTotal / recentTotalMinutes
                : seasonRate;

            const rate =
              stat === "points"
                ? pointsRate(player, recent)
                : blendedRate(
                    seasonRate,
                    recentRate,
                    seasonGames,
                    validRecent.length
                  );

            const opponentFactor = defenseFactor(
              opponentDefense,
              stat,
              opponent
            );

            const matchupPace =
              stat === "points"
                ? paceFactor(team, opponent)
                : 1;

            const estimate =
              projectedMinutes *
              rate *
              opponentFactor *
              matchupPace *
              (1 + teammateBoost);

            return Math.max(
              0,
              estimate
            ).toFixed(1);
          });

          const injuryStatus = injury
            ? injury.status || "Reported"
            : "Not listed";

          rows.push(`
            <tr>
              <td>${escapeHTML(player.player_name)}</td>
              <td>${escapeHTML(team)}</td>
              <td>${escapeHTML(opponent)}</td>
              <td>${escapeHTML(position || "—")}</td>
              <td class="${injury ? "inj" : ""}">
                ${escapeHTML(injuryStatus)}
              </td>
              <td>
                ${opponentDefense
                  ? escapeHTML(opponentDefense.player_games)
                  : "—"}
              </td>
              ${estimates.map(
                value => `<td>${value}</td>`
              ).join("")}
            </tr>
          `);
        }
      }

      const dateText = new Date(
        game.date_utc
      ).toLocaleString();

      const injuryUpdated =
        injuries[0]?.last_updated_utc ||
        "Unknown";

      const statusText =
        game.status_detail ||
        game.status ||
        "Scheduled";

      const details = root.querySelector(
        "#cs-game-details"
      );

      details.innerHTML = `
        <p class="muted">
          ${escapeHTML(game.away)} @
          ${escapeHTML(game.home)}
          · ${escapeHTML(dateText)}
          · ${escapeHTML(statusText)}
        </p>

        <p class="muted">
          Injury report updated:
          ${escapeHTML(injuryUpdated)}.
          ${
            injuriesResult.ok
              ? "Players not listed are not guaranteed healthy."
              : "Injury data unavailable."
          }
          OUT players have no estimate.
          Other reported statuses remain visible.
          Teammate injury adjustments are capped at 8%.
          Points use pace-adjusted opponent defense
          and matchup pace. These are model estimates,
          not live in-game projections.
        </p>

        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Team</th>
                <th>Opponent</th>
                <th>Pos</th>
                <th>Injury status</th>
                <th>Defense sample</th>
                ${LABELS.map(
                  label => `<th>${label}</th>`
                ).join("")}
              </tr>
            </thead>

            <tbody>
              ${
                rows.length
                  ? rows.join("")
                  : `<tr>
                      <td colspan="12">
                        No matching player statistics.
                      </td>
                    </tr>`
              }
            </tbody>
          </table>
        </div>
      `;
    }

    select.addEventListener("change", render);

    render();

  } catch (error) {
    console.error(
      "Courtside matchup predictor:",
      error
    );

    root.innerHTML = `
      <h2>NBA Schedule & Matchup Stats</h2>

      <p class="error">
        Could not load matchup predictor:
        ${escapeHTML(error.message)}
      </p>
    `;
  }
})();
