
/* COURTSIDE — NBA Matchup Predictor
   Upgraded: Points, Rebounds, Assists
   Shows today's games, including games in progress.
*/
(async function () {
  "use strict";

  const BASE =
    "https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/";

  const STATS = [
    "points", "rebounds", "assists",
    "three_pointers", "steals", "blocks"
  ];
  const LABELS = ["PTS", "REB", "AST", "3PM", "STL", "BLK"];

  const n = x => {
    const v = Number(x);
    return Number.isFinite(v) ? v : 0;
  };
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const norm = x => String(x || "").trim().toUpperCase();
  const normName = x => String(x || "").toLowerCase()
    .normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z]/g, "");
  const esc = x => String(x ?? "").replace(
    /[&<>"']/g,
    c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;",
      '"': "&quot;", "'": "&#39;"
    })[c]
  );
  const group = p => {
    p = norm(p);
    if (["PG", "SG", "G"].includes(p)) return "G";
    if (["SF", "PF", "F"].includes(p)) return "F";
    if (p === "C") return "C";
    return "";
  };

  function csv(text) {
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
        if (row.some(x => x !== "")) rows.push(row);
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

    const headers = rows.shift() || [];
    return rows.map(r => Object.fromEntries(
      headers.map((h, i) => [h, r[i] ?? ""])
    ));
  }

  async function load(name) {
    const response = await fetch(
      BASE + name + "?t=" + Date.now(),
      { cache: "no-store" }
    );
    if (!response.ok) {
      throw Error(name + " HTTP " + response.status);
    }
    return csv(await response.text());
  }

  const style = document.createElement("style");
  style.textContent = `
    #cs-schedule {
      font:14px system-ui,sans-serif;
      background:#14171f;color:#f5f6fa;
      border:1px solid #353944;border-radius:18px;
      padding:22px;margin:24px auto;max-width:1200px
    }
    #cs-schedule h2 {margin:0 0 8px;font-size:25px}
    #cs-schedule select {
      background:#202530;color:white;
      border:1px solid #555;border-radius:8px;
      padding:10px;width:100%;margin:12px 0
    }
    #cs-schedule table {
      border-collapse:collapse;width:100%;min-width:1000px
    }
    #cs-schedule td,#cs-schedule th {
      text-align:left;border-bottom:1px solid #343844;
      padding:10px
    }
    #cs-schedule th {color:#d5d7df}
    #cs-schedule .scroll {overflow-x:auto}
    #cs-schedule .muted {color:#b3b9c6;line-height:1.5}
    #cs-schedule .inj {color:#ffb0b0}
    #cs-schedule .error {color:#ff6868}
  `;
  document.head.appendChild(style);

  let root = document.getElementById("cs-schedule");
  if (!root) {
    root = document.createElement("section");
    root.id = "cs-schedule";
    (document.querySelector("main") || document.body)
      .appendChild(root);
  }

  root.innerHTML = `
    <h2>NBA Schedule & Matchup Stats</h2>
    <p class="muted">Loading games and player statistics...</p>
  `;

  try {
    const [
      schedule, players, defense, logs,
      paceRows, injuryRows
    ] = await Promise.all([
      load("nba_schedule.csv"),
      load("nba_stats.csv"),
      load("nba_opponent_defense.csv"),
      load("nba_game_logs.csv"),
      load("nba_team_pace.csv"),
      load("nba_injuries.csv").catch(() => [])
    ]);

    const paceByTeam = new Map(
      paceRows.map(p => [norm(p.team), p])
    );

    const logsByPlayer = new Map();
    for (const log of logs) {
      const id = String(log.player_id || "");
      if (!logsByPlayer.has(id)) logsByPlayer.set(id, []);
      logsByPlayer.get(id).push(log);
    }
    for (const entries of logsByPlayer.values()) {
      entries.sort((a, b) =>
        String(b.date).localeCompare(String(a.date))
      );
    }

    function localDateKey(value) {
      const d = new Date(value);
      if (!Number.isFinite(d.getTime())) return "";
      return [
        d.getFullYear(),
        String(d.getMonth() + 1).padStart(2, "0"),
        String(d.getDate()).padStart(2, "0")
      ].join("-");
    }

    // Keep all of today's games, even after tipoff.
    const today = localDateKey(new Date());
    const upcoming = schedule.filter(g => {
      const date = localDateKey(g.date_utc);
      return date && date >= today;
    }).sort((a, b) =>
      new Date(a.date_utc) - new Date(b.date_utc)
    );

    if (!upcoming.length) {
      root.innerHTML = `
        <h2>NBA Schedule & Matchup Stats</h2>
        <p class="muted">
          No games found for today or later.
          Check nba_schedule.csv.
        </p>
      `;
      return;
    }

    const baselines = new Map();
    for (const d of defense) {
      const games = n(d.player_games);
      if (games <= 0) continue;
      for (const stat of STATS) {
        const key = [
          d.position_type, d.position, stat
        ].join("|");
        if (!baselines.has(key)) {
          baselines.set(key, { total: 0, games: 0 });
        }
        const b = baselines.get(key);
        b.total += n(d[stat + "_allowed_pg"]) * games;
        b.games += games;
      }
    }

    function paceFactor(team, opponent) {
      const a = paceByTeam.get(norm(team));
      const b = paceByTeam.get(norm(opponent));
      if (!a || !b) return 1;
      const own = n(a.adjusted_pace);
      const other = n(b.adjusted_pace);
      if (own <= 0 || other <= 0) return 1;
      return clamp(((own + other) / 2) / own, .90, 1.10);
    }

    function defensePaceCorrection(opponent) {
      const p = paceByTeam.get(norm(opponent));
      if (!p) return 1;
      const league = n(p.league_average_pace);
      const opponentPace = n(p.adjusted_pace);
      if (league <= 0 || opponentPace <= 0) return 1;
      return clamp(league / opponentPace, .85, 1.15);
    }

    function defenseFactor(d, stat, opponent) {
      if (!d) return 1;
      const key = [
        d.position_type, d.position, stat
      ].join("|");
      const b = baselines.get(key);
      if (!b || b.games <= 0) return 1;

      const average = b.total / b.games;
      if (average <= 0) return 1;

      const games = n(d.player_games);
      let raw = n(d[stat + "_allowed_pg"]) / average;

      if (["points", "rebounds", "assists"].includes(stat)) {
        raw *= defensePaceCorrection(opponent);
      }

      return clamp(
        1 + (games / (games + 20)) * .5 * (raw - 1),
        .85, 1.15
      );
    }

    function minutes(log) {
      return n(
        log.minutes ||
        log.minutes_played ||
        log.minutes_pg
      );
    }

    function sampleRate(sample, stat, fallback) {
      const valid = sample.filter(l =>
        minutes(l) > 0 &&
        String(l[stat] ?? "").trim() !== ""
      );
      const totalMinutes = valid.reduce(
        (s, l) => s + minutes(l), 0
      );
      if (!totalMinutes) return fallback;
      return valid.reduce(
        (s, l) => s + n(l[stat]), 0
      ) / totalMinutes;
    }

    function injuryFor(player) {
      return injuryRows.find(i =>
        (
          i.player_id && player.player_id &&
          String(i.player_id) === String(player.player_id)
        ) || (
          norm(i.team) === norm(player.team) &&
          normName(i.player_name) ===
            normName(player.player_name)
        )
      );
    }

    function isOut(injury) {
      return Boolean(injury && [
        "out", "inactive", "injured reserve",
        "suspended", "not with team"
      ].includes(String(injury.status || "")
        .trim().toLowerCase()));
    }

    function predict(player, recent, projectedMinutes,
                     stat, defenseRow, opponent,
                     team, injuryBoost) {
      const seasonMinutes = n(player.minutes_pg);
      const seasonRate = seasonMinutes > 0
        ? n(player[stat + "_pg"]) / seasonMinutes
        : 0;

      const last10 = sampleRate(
        recent.slice(0, 10), stat, seasonRate
      );
      const last5 = sampleRate(
        recent.slice(0, 5), stat, seasonRate
      );

      let rate;

      if (stat === "points") {
        rate = .55 * seasonRate +
               .30 * last10 +
               .15 * last5;
      } else if (stat === "rebounds") {
        rate = .50 * seasonRate +
               .30 * last10 +
               .20 * last5;
      } else if (stat === "assists") {
        rate = .45 * seasonRate +
               .35 * last10 +
               .20 * last5;
      } else {
        const valid = recent.filter(l =>
          minutes(l) > 0 &&
          String(l[stat] ?? "").trim() !== ""
        );
        const games = n(player.games_played);
        const weight = games / (games + 12);
        const stabilized =
          weight * seasonRate +
          (1 - weight) * last10;
        const recentWeight =
          valid.length / (valid.length + 10);
        rate = (1 - recentWeight) * stabilized +
               recentWeight * last10;
      }

      const defenseAdjustment =
        defenseFactor(defenseRow, stat, opponent);

      const matchupPace =
        ["points", "rebounds", "assists"].includes(stat)
          ? paceFactor(team, opponent)
          : 1;

      return Math.max(
        0,
        projectedMinutes *
        rate *
        defenseAdjustment *
        matchupPace *
        (1 + injuryBoost)
      );
    }

    root.innerHTML = `
      <h2>NBA Schedule & Matchup Stats</h2>
      <p class="muted">
        Current-season estimates using recent games,
        opponent defense, playing time and matchup pace.
        Points, rebounds and assists use upgraded formulas.
        These are experimental estimates, not live
        in-game projections.
      </p>
      <label for="cs-game">Today's and upcoming games</label>
      <select id="cs-game"></select>
      <div id="cs-game-details"></div>
    `;

    const select = root.querySelector("#cs-game");
    upcoming.forEach((g, i) => {
      const option = document.createElement("option");
      option.value = i;
      option.textContent =
        `${g.away} @ ${g.home} · ` +
        new Date(g.date_utc).toLocaleString(undefined, {
          month: "short", day: "numeric",
          hour: "numeric", minute: "2-digit"
        });
      select.appendChild(option);
    });

    function render() {
      const game = upcoming[Number(select.value) || 0];
      const rows = [];

      for (const [team, opponent] of [
        [game.away, game.home],
        [game.home, game.away]
      ]) {
        const roster = players.filter(p =>
          norm(p.team) === norm(team) &&
          n(p.games_played) > 0
        );

        const absentMinutes = roster.reduce(
          (total, p) =>
            total + (
              isOut(injuryFor(p)) ? n(p.minutes_pg) : 0
            ), 0
        );

        const available = roster.filter(
          p => !isOut(injuryFor(p))
        ).length;

        const injuryBoost = available
          ? Math.min(.08, absentMinutes / 240 * .22)
          : 0;

        for (const player of roster) {
          const injury = injuryFor(player);
          const out = isOut(injury);

          const recent = (
            logsByPlayer.get(String(player.player_id)) || []
          ).filter(l =>
            String(l.date || "").slice(0, 10) <
            localDateKey(game.date_utc)
          ).slice(0, 10);

          const position = recent.find(
            l => l.position
          )?.position || "";

          let d = defense.find(x =>
            norm(x.opponent) === norm(opponent) &&
            x.position === position &&
            x.position_type === "position"
          );

          if (!d) {
            d = defense.find(x =>
              norm(x.opponent) === norm(opponent) &&
              x.position === group(position) &&
              x.position_type === "position_group"
            );
          }

          const recentMinutes = recent
            .map(minutes).filter(x => x > 0);

          const seasonMinutes = n(player.minutes_pg);
          const recentAverage = recentMinutes.length
            ? recentMinutes.reduce((a, b) => a + b, 0) /
              recentMinutes.length
            : seasonMinutes;

          const projectedMinutes = clamp(
            .75 * seasonMinutes + .25 * recentAverage,
            0, 48
          );

          const estimates = STATS.map(stat =>
            out
              ? "—"
              : predict(
                  player, recent, projectedMinutes,
                  stat, d, opponent, team, injuryBoost
                ).toFixed(1)
          );

          rows.push(`
            <tr>
              <td>${esc(player.player_name)}</td>
              <td>${esc(team)}</td>
              <td>${esc(opponent)}</td>
              <td>${esc(position || "—")}</td>
              <td class="${injury ? "inj" : ""}">
                ${esc(injury?.status || "Not listed")}
              </td>
              <td>${d ? esc(d.player_games) : "—"}</td>
              ${estimates.map(v => `<td>${v}</td>`).join("")}
            </tr>
          `);
        }
      }

      root.querySelector("#cs-game-details").innerHTML = `
        <p class="muted">
          ${esc(game.away)} @ ${esc(game.home)} ·
          ${esc(new Date(game.date_utc).toLocaleString())} ·
          ${esc(game.status_detail || game.status || "Scheduled")}
        </p>
        <p class="muted">
          OUT players have no estimate.
          Other injury statuses are shown but do not
          guarantee availability. Defense sample refers
          to opposing player appearances at the position.
          Estimates are not updated from live box scores.
        </p>
        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th>Player</th><th>Team</th>
                <th>Opponent</th><th>Pos</th>
                <th>Injury</th><th>Defense sample</th>
                ${LABELS.map(x => `<th>${x}</th>`).join("")}
              </tr>
            </thead>
            <tbody>
              ${rows.join("") ||
                '<tr><td colspan="12">No player stats found</td></tr>'}
            </tbody>
          </table>
        </div>
      `;
    }

    select.addEventListener("change", render);
    render();

  } catch (error) {
    console.error("Courtside matchup error:", error);
    root.innerHTML = `
      <h2>NBA Schedule & Matchup Stats</h2>
      <p class="error">
        Could not load predictor: ${esc(error.message)}
      </p>
    `;
  }
})();
