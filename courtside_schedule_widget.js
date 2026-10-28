
(async function () {
  "use strict";

  const BASE = "https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/";
  const STATS = ["points", "rebounds", "assists", "three_pointers", "steals", "blocks"];
  const LABELS = ["PTS", "REB", "AST", "3PM", "STL", "BLK"];
  const ATTEMPT_KEYS = [
    "three_pointers_attempted", "three_point_attempts",
    "three_point_attempted", "three_pointers_attempts",
    "three_point_attempts_pg", "three_pointers_attempted_pg",
    "three_pa", "three_pa_pg", "three_point_attempts_per_game",
    "three_pointers_attempted_per_game", "fg3a", "fg3a_pg",
    "3pa", "3pa_pg"
  ];

  const n = x => {
    if (x === null || x === undefined || String(x).trim() === "") return 0;
    const v = Number(x);
    return Number.isFinite(v) ? v : 0;
  };

  const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
  const norm = x => String(x ?? "").trim().toUpperCase();
  const nameKey = x => String(x ?? "").toLowerCase()
    .normalize("NFKD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z]/g, "");
  const esc = x => String(x ?? "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

  const group = p =>
    ["PG","SG","G"].includes(norm(p)) ? "G" :
    ["SF","PF","F"].includes(norm(p)) ? "F" :
    norm(p) === "C" ? "C" : "";

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

    const headers = (rows.shift() || [])
      .map(h => h.replace(/^\uFEFF/, ""));

    return rows.map(r => Object.fromEntries(
      headers.map((h, i) => [h, r[i] ?? ""])
    ));
  }

  async function load(file) {
    const response = await fetch(
      BASE + file + "?v=" + Date.now(),
      { cache: "no-store" }
    );

    if (!response.ok) {
      throw Error(file + ": HTTP " + response.status);
    }

    return parseCSV(await response.text());
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

  function minutes(row) {
    return n(row.minutes ?? row.minutes_played ?? row.minutes_pg);
  }

  function attemptValue(row) {
    for (const key of ATTEMPT_KEYS) {
      if (
        Object.prototype.hasOwnProperty.call(row, key) &&
        String(row[key] ?? "").trim() !== ""
      ) {
        return n(row[key]);
      }
    }
    return null;
  }

  function perMinute(logs, stat, fallback) {
    const valid = logs.filter(l =>
      minutes(l) > 0 &&
      String(l[stat] ?? "").trim() !== ""
    );

    const totalMinutes = valid.reduce(
      (s, l) => s + minutes(l), 0
    );

    return totalMinutes
      ? valid.reduce((s, l) => s + n(l[stat]), 0) / totalMinutes
      : fallback;
  }

  function attemptRate(logs, fallback) {
    const valid = logs.filter(l =>
      minutes(l) > 0 && attemptValue(l) !== null
    );

    const totalMinutes = valid.reduce(
      (s, l) => s + minutes(l), 0
    );

    return totalMinutes
      ? valid.reduce((s, l) => s + attemptValue(l), 0) / totalMinutes
      : fallback;
  }

  function predictThree(player, recent, projected, df, pf, boost) {
    const seasonMinutes = n(player.minutes_pg);
    const seasonMakes = n(player.three_pointers_pg);
    const seasonAttempts = attemptValue(player);

    function fallback() {
      const sr = seasonMinutes
        ? seasonMakes / seasonMinutes : 0;

      const last10 = perMinute(
        recent.slice(0, 10), "three_pointers", sr
      );

      const valid = recent.filter(l =>
        minutes(l) > 0 &&
        String(l.three_pointers ?? "").trim() !== ""
      );

      const games = n(player.games_played);
      const sw = games / (games + 12);
      const stable = sw * sr + (1 - sw) * last10;
      const rw = valid.length / (valid.length + 10);

      return projected *
        ((1 - rw) * stable + rw * last10) *
        df * pf * (1 + boost);
    }

    if (
      seasonAttempts === null ||
      seasonAttempts <= 0 ||
      seasonMinutes <= 0
    ) {
      return Math.max(0, fallback());
    }

    const hasRecentAttempts = recent.some(l =>
      minutes(l) > 0 && attemptValue(l) !== null
    );

    if (!hasRecentAttempts) {
      return Math.max(0, fallback());
    }

    const seasonAttemptRate = seasonAttempts / seasonMinutes;

    const last10 = attemptRate(
      recent.slice(0, 10), seasonAttemptRate
    );

    const last5 = attemptRate(
      recent.slice(0, 5), seasonAttemptRate
    );

    const projectedAttempts = projected * (
      .50 * seasonAttemptRate +
      .30 * last10 +
      .20 * last5
    );

    const seasonPct = clamp(
      seasonMakes / seasonAttempts, 0, 1
    );

    const valid = recent.slice(0, 10).filter(l =>
      minutes(l) > 0 &&
      attemptValue(l) !== null &&
      String(l.three_pointers ?? "").trim() !== ""
    );

    const attempts = valid.reduce(
      (s, l) => s + attemptValue(l), 0
    );

    const makes = valid.reduce(
      (s, l) => s + n(l.three_pointers), 0
    );

    const expectedPct = clamp(
      (makes + 60 * seasonPct) / (attempts + 60),
      0, 1
    );

    return Math.max(
      0,
      projectedAttempts * expectedPct * df * pf * (1 + boost)
    );
  }

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
  `;

  document.head.appendChild(style);

  let root = document.getElementById("cs-schedule");

  if (!root) {
    root = document.createElement("section");
    root.id = "cs-schedule";

    (document.querySelector("main") || document.body)
      .appendChild(root);
  }

  root.innerHTML =
    "<h2>NBA Schedule & Matchup Stats</h2><p>Loading...</p>";

  try {
    const [
      schedule,
      players,
      defense,
      logs,
      paceRows,
      injuries,
      scored
    ] = await Promise.all([
      load("nba_schedule.csv"),
      load("nba_stats.csv"),
      load("nba_opponent_defense.csv"),
      load("nba_game_logs.csv"),
      load("nba_team_pace.csv"),
      load("nba_injuries.csv").catch(() => []),
      load("nba_prediction_results.csv").catch(() => [])
    ]);

    // Use only historical results that existed before the matchup.
    const pastResults = scored.filter(r =>
      Number.isFinite(
        Date.parse(r.tipoff_utc || r.game_date)
      )
    ).sort((a, b) =>
      Date.parse(a.tipoff_utc || a.game_date) -
      Date.parse(b.tipoff_utc || b.game_date)
    );

    function quantile(values, q) {
      const sorted = values
        .filter(Number.isFinite)
        .sort((a, b) => a - b);

      if (!sorted.length) return null;

      const index = Math.min(
        sorted.length - 1,
        Math.max(
          0,
          Math.ceil((sorted.length + 1) * q) - 1
        )
      );

      return sorted[index];
    }

    // Estimate how much each player's results fluctuate.
    function variability(stat, recent, prediction, projected) {
      const observations = recent.slice(0, 20)
        .filter(log =>
          minutes(log) >= 8 &&
          String(log[stat] ?? "").trim() !== ""
        )
        .map((log, i) => ({
          value: n(log[stat]) * clamp(
            projected / minutes(log),
            .65,
            1.45
          ),
          weight: Math.exp(-i / 7)
        }));

      const totalWeight = observations.reduce(
        (sum, x) => sum + x.weight, 0
      );

      const mean = totalWeight
        ? observations.reduce(
            (sum, x) => sum + x.weight * x.value, 0
          ) / totalWeight
        : prediction;

      const observedVariance =
        totalWeight && observations.length >= 3
          ? observations.reduce(
              (sum, x) =>
                sum + x.weight * (x.value - mean) ** 2,
              0
            ) / totalWeight
          : 0;

      const floors = {
        points: 2.5,
        rebounds: 1.25,
        assists: 1,
        three_pointers: .7,
        steals: .55,
        blocks: .5
      };

      const priorSD = Math.max(
        floors[stat] || .5,
        Math.sqrt(Math.max(.3, prediction))
      );

      const effectiveN = totalWeight;

      const variance = (
        effectiveN * observedVariance +
        6 * priorSD ** 2
      ) / (effectiveN + 6);

      return Math.sqrt(
        Math.max(
          (floors[stat] || .5) ** 2,
          variance
        )
      );
    }

    // NARROWER PLAYER-SPECIFIC PREDICTION RANGES
    function rangeText(
      stat,
      prediction,
      player,
      recent,
      projected,
      gameDate
    ) {
      const playerSD = variability(
        stat,
        recent,
        prediction,
        projected
      );

      const priorSD = Math.max(
        .5,
        Math.sqrt(Math.max(.3, prediction))
      );

      const consistencyScale = clamp(
        playerSD / priorSD,
        .82,
        1.25
      );

      const gameTime = Date.parse(gameDate);

      const eligible = pastResults.filter(r =>
        Date.parse(r.tipoff_utc || r.game_date) < gameTime &&
        String(r["error_" + stat] ?? "").trim() !== "" &&
        Number.isFinite(Number(r["error_" + stat]))
      );

      const provisional = eligible.length < 30;
      let halfWidth;

      if (provisional) {
        // Narrower provisional estimate.
        // Not guaranteed to achieve 80% coverage.
        halfWidth = 1.15 * playerSD;
      } else {
        const pooled = eligible.map(r =>
          Math.abs(Number(r["error_" + stat]))
        );

        const individual = eligible
          .filter(r =>
            String(r.player_id) === String(player.player_id)
          )
          .map(r =>
            Math.abs(Number(r["error_" + stat]))
          );

        const pooledQ = quantile(pooled, .8);

        const individualQ = individual.length >= 12
          ? quantile(individual, .8)
          : pooledQ;

        const playerWeight = individual.length >= 12
          ? Math.min(
              .5,
              individual.length / (individual.length + 30)
            )
          : 0;

        halfWidth = (
          (1 - playerWeight) * pooledQ +
          playerWeight * individualQ
        ) * consistencyScale;
      }

      const floor = {
        points: 1,
        rebounds: .5,
        assists: .5,
        three_pointers: .4,
        steals: .35,
        blocks: .35
      }[stat] || .35;

      halfWidth = Math.min(5, Math.max(floor, halfWidth));

      const low = Math.max(
        0,
        prediction - halfWidth
      );

      const high = prediction + halfWidth;

      return (
        low.toFixed(1) +
        "–" +
        high.toFixed(1) +
        (provisional ? "*" : "")
      );
    }

    function projectedMinutes(
      player,
      recent,
      absent,
      healthyMinutes
    ) {
      const season = n(player.minutes_pg);

      const last10 = recent.slice(0, 10)
        .map(minutes)
        .filter(x => x > 0);

      const last5 = last10.slice(0, 5);

      const mean = xs => xs.length
        ? xs.reduce((a, b) => a + b, 0) / xs.length
        : season;

      const base =
        .45 * season +
        .35 * mean(last10) +
        .20 * mean(last5);

      const trend = clamp(
        mean(last5) - mean(last10),
        -3,
        3
      ) * .25;

      const share = healthyMinutes > 0
        ? season / healthyMinutes
        : 0;

      const extra = Math.min(
        base * .12,
        absent * share * .35
      );

      return clamp(base + trend + extra, 0, 48);
    }

    const paceMap = new Map(
      paceRows.map(x => [norm(x.team), x])
    );

    const logsMap = new Map();

    for (const log of logs) {
      const id = String(log.player_id ?? "");

      if (!logsMap.has(id)) {
        logsMap.set(id, []);
      }

      logsMap.get(id).push(log);
    }

    for (const entries of logsMap.values()) {
      entries.sort(
        (a, b) =>
          String(b.date).localeCompare(String(a.date))
      );
    }

    const today = localDateKey(new Date());

    const games = schedule.filter(g => {
      const date = localDateKey(g.date_utc);
      return date && date >= today;
    }).sort(
      (a, b) =>
        new Date(a.date_utc) - new Date(b.date_utc)
    );

    if (!games.length) {
      root.innerHTML =
        "<h2>NBA Schedule & Matchup Stats</h2>" +
        "<p>No games found for today or later.</p>";
      return;
    }

    const baseline = new Map();

    for (const d of defense) {
      const count = n(d.player_games);
      if (count <= 0) continue;

      for (const stat of STATS) {
        const key = [
          d.position_type,
          d.position,
          stat
        ].join("|");

        if (!baseline.has(key)) {
          baseline.set(key, {
            total: 0,
            count: 0
          });
        }

        const b = baseline.get(key);

        b.total += n(d[stat + "_allowed_pg"]) * count;
        b.count += count;
      }
    }

    function paceFactor(team, opponent) {
      const a = paceMap.get(norm(team));
      const b = paceMap.get(norm(opponent));

      if (!a || !b) return 1;

      const own = n(a.adjusted_pace);
      const other = n(b.adjusted_pace);

      return own > 0 && other > 0
        ? clamp(
            ((own + other) / 2) / own,
            .90,
            1.10
          )
        : 1;
    }

    function defensePace(opponent) {
      const p = paceMap.get(norm(opponent));

      if (!p) return 1;

      const league = n(p.league_average_pace);
      const opp = n(p.adjusted_pace);

      return league > 0 && opp > 0
        ? clamp(league / opp, .85, 1.15)
        : 1;
    }

    function defenseFactor(
      d,
      stat,
      opponent,
      gameDate
    ) {
      if (!d) return 1;

      const b = baseline.get([
        d.position_type,
        d.position,
        stat
      ].join("|"));

      if (!b || b.count <= 0 || b.total <= 0) {
        return 1;
      }

      const seasonAllowed = n(
        d[stat + "_allowed_pg"]
      );

      const samples = logs.filter(l =>
        norm(l.opponent) === norm(opponent) &&
        String(l.date ?? "").slice(0, 10) < gameDate &&
        (
          d.position_type === "position"
            ? norm(l.position) === norm(d.position)
            : group(l.position) === norm(d.position)
        ) &&
        minutes(l) > 0 &&
        String(l[stat] ?? "").trim() !== ""
      ).sort(
        (a, b) =>
          String(b.date).localeCompare(String(a.date))
      ).slice(0, 25);

      const recentAllowed = samples.length
        ? samples.reduce(
            (sum, l) => sum + n(l[stat]),
            0
          ) / samples.length
        : seasonAllowed;

      const recentWeight = Math.min(
        .25,
        samples.length / 100
      );

      const blendedAllowed =
        seasonAllowed * (1 - recentWeight) +
        recentAllowed * recentWeight;

      let raw = blendedAllowed / (b.total / b.count);

      raw *= defensePace(opponent);

      const count = n(d.player_games);

      return clamp(
        1 + (count / (count + 20)) * .5 * (raw - 1),
        .85,
        1.15
      );
    }

    function injuryFor(player) {
      return injuries.find(i =>
        (
          i.player_id &&
          player.player_id &&
          String(i.player_id) === String(player.player_id)
        ) ||
        (
          norm(i.team) === norm(player.team) &&
          nameKey(i.player_name) === nameKey(player.player_name)
        )
      );
    }

    function isOut(injury) {
      return Boolean(
        injury &&
        [
          "OUT",
          "INACTIVE",
          "INJURED RESERVE",
          "SUSPENDED",
          "NOT WITH TEAM"
        ].includes(norm(injury.status))
      );
    }

    function predict(
      player,
      recent,
      projected,
      stat,
      d,
      opponent,
      team,
      boost,
      gameDate
    ) {
      const seasonMinutes = n(player.minutes_pg);

      const sr = seasonMinutes
        ? n(player[stat + "_pg"]) / seasonMinutes
        : 0;

      const l10 = perMinute(
        recent.slice(0, 10),
        stat,
        sr
      );

      const l5 = perMinute(
        recent.slice(0, 5),
        stat,
        sr
      );

      const df = defenseFactor(
        d,
        stat,
        opponent,
        gameDate
      );

      const pf = paceFactor(team, opponent);

      if (stat === "three_pointers") {
        return predictThree(
          player,
          recent,
          projected,
          df,
          pf,
          boost
        );
      }

      let weightedRate;

      if (stat === "points") {
        weightedRate =
          .55 * sr +
          .30 * l10 +
          .15 * l5;
      } else if (stat === "rebounds") {
        weightedRate =
          .50 * sr +
          .30 * l10 +
          .20 * l5;
      } else if (stat === "assists") {
        weightedRate =
          .45 * sr +
          .35 * l10 +
          .20 * l5;
      } else if (
        stat === "steals" ||
        stat === "blocks"
      ) {
        weightedRate =
          .60 * sr +
          .25 * l10 +
          .15 * l5;
      } else {
        weightedRate = sr;
      }

      return Math.max(
        0,
        projected *
        weightedRate *
        df *
        pf *
        (1 + boost)
      );
    }

    root.innerHTML = `
      <h2>NBA Schedule & Matchup Stats</h2>

      <p class="muted">
        Current-season estimates based on recent performance,
        opponent positional defense, projected minutes,
        injuries, and matchup pace.
      </p>

      <label for="cs-game">
        Today's and upcoming games
      </label>

      <select id="cs-game"></select>

      <div id="cs-game-details"></div>
    `;

    const select = root.querySelector("#cs-game");

    games.forEach((g, i) => {
      const option = document.createElement("option");

      option.value = String(i);

      option.textContent =
        `${g.away} @ ${g.home} · ` +
        new Date(g.date_utc).toLocaleString(
          undefined,
          {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit"
          }
        );

      select.appendChild(option);
    });

    function render() {
      const game = games[Number(select.value) || 0];
      const rows = [];

      for (const [team, opponent] of [
        [game.away, game.home],
        [game.home, game.away]
      ]) {
        const roster = players.filter(p =>
          norm(p.team) === norm(team) &&
          n(p.games_played) > 0
        );

        const absent = roster.reduce(
          (sum, p) =>
            sum + (
              isOut(injuryFor(p))
                ? n(p.minutes_pg)
                : 0
            ),
          0
        );

        const healthyMinutes = roster.reduce(
          (sum, p) =>
            sum + (
              !isOut(injuryFor(p))
                ? n(p.minutes_pg)
                : 0
            ),
          0
        );

        for (const player of roster) {
          const injury = injuryFor(player);
          const out = isOut(injury);

          const recent = (
            logsMap.get(String(player.player_id)) || []
          ).filter(l =>
            String(l.date ?? "").slice(0, 10) <
            localDateKey(game.date_utc)
          ).slice(0, 20);

          const position =
            recent.find(l => l.position)?.position || "";

          let d = defense.find(x =>
            norm(x.opponent) === norm(opponent) &&
            norm(x.position) === norm(position) &&
            x.position_type === "position"
          );

          if (!d) {
            d = defense.find(x =>
              norm(x.opponent) === norm(opponent) &&
              norm(x.position) === group(position) &&
              x.position_type === "position_group"
            );
          }

          const seasonMinutes = n(player.minutes_pg);

          const projected = projectedMinutes(
            player,
            recent,
            absent,
            healthyMinutes
          );

          const boost =
            absent > 0 && healthyMinutes > 0
              ? Math.min(
                  .04,
                  (absent / 240) * .10 *
                  (
                    seasonMinutes /
                    Math.max(
                      1,
                      healthyMinutes /
                      Math.max(1, roster.length)
                    )
                  )
                )
              : 0;

          const predictions = STATS.map(stat =>
            out
              ? null
              : predict(
                  player,
                  recent,
                  projected,
                  stat,
                  d,
                  opponent,
                  team,
                  boost,
                  localDateKey(game.date_utc)
                )
          );

          const values = predictions.map(v =>
            v === null ? "—" : v.toFixed(1)
          );

          const ranges = predictions.map((v, i) =>
            v === null
              ? "—"
              : rangeText(
                  STATS[i],
                  v,
                  player,
                  recent,
                  projected,
                  game.date_utc
                )
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

              <td>
                ${out ? "—" : projected.toFixed(1)}
              </td>

              ${values.map((v, i) => `
                <td>
                  ${v}
                  <div class="muted" style="font-size:11px">
                    ${ranges[i] === "—"
                      ? ""
                      : "Range: " + ranges[i]}
                  </div>
                </td>
              `).join("")}
            </tr>
          `);
        }
      }

      root.querySelector("#cs-game-details").innerHTML = `
        <p class="muted">
          ${esc(game.away)} @ ${esc(game.home)} ·
          ${esc(new Date(game.date_utc).toLocaleString())} ·
          ${esc(
            game.status_detail ||
            game.status ||
            "Scheduled"
          )}
        </p>

        <p class="muted">
          OUT players have no estimates.
          Predictions are pregame-style, not live box-score updates.
          Ranges use recent player consistency and previous
          scored predictions to target approximately 80% coverage.
          Actual coverage may differ.
          An asterisk (*) means the range is provisional
          because fewer than 30 earlier scored results
          are available.
        </p>

        <div class="scroll">
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Team</th>
                <th>Opponent</th>
                <th>Pos</th>
                <th>Injury</th>
                <th>Defense sample</th>
                <th>Est. MIN</th>

                ${LABELS.map(x =>
                  `<th>${x}</th>`
                ).join("")}
              </tr>
            </thead>

            <tbody>
              ${rows.join("") ||
                '<tr><td colspan="13">No player stats found</td></tr>'}
            </tbody>
          </table>
        </div>
      `;
    }

    select.addEventListener("change", render);
    render();

  } catch (error) {
    console.error("Courtside predictor:", error);

    root.innerHTML = `
      <h2>NBA Schedule & Matchup Stats</h2>
      <p class="error">
        Could not load predictor: ${esc(error.message)}
      </p>
    `;
  }
})();
