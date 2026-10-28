
/* Courtside — NBA news and automatically refreshed injuries */
(function () {
  "use strict";

  const BASE =
    "https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/";

  const REFRESH_MS = 5 * 60 * 1000;

  const esc = value =>
    String(value ?? "").replace(/[&<>"']/g, c => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;"
    })[c]);

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
      } else if (
        (c === "\n" || c === "\r") && !quoted
      ) {
        if (c === "\r" && text[i + 1] === "\n") i++;

        row.push(cell);
        if (row.some(Boolean)) rows.push(row);

        row = [];
        cell = "";
      } else {
        cell += c;
      }
    }

    if (row.length || cell) {
      row.push(cell);
      rows.push(row);
    }

    const headers = (rows.shift() || [])
      .map(x => x.replace(/^\uFEFF/, ""));

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
      throw Error(file + " HTTP " + response.status);
    }

    return parseCSV(await response.text());
  }

  function safeUrl(value) {
    try {
      const url = new URL(value);

      if (
        url.protocol === "https:" &&
        /(^|\.)espn\.com$/.test(url.hostname)
      ) {
        return url.href;
      }
    } catch (_) {}

    return "";
  }

  const style = document.createElement("style");

  style.textContent = `
    #cs-news {
      background: #16191f;
      color: #f7f7fa;
      border: 1px solid #363b46;
      border-radius: 16px;
      padding: 16px;
      margin: 18px auto;
      max-width: 1200px;
      font: 14px system-ui, sans-serif;
    }

    #cs-news h2 {
      font-size: 22px;
      margin: 0 0 10px;
    }

    #cs-news .muted {
      color: #b9bdc7;
      font-size: 12px;
      line-height: 1.6;
    }

    #cs-news .lane {
      overflow: hidden;
      white-space: nowrap;
      border-top: 1px solid #303540;
      padding: 12px 0;
    }

    #cs-news .track {
      display: inline-block;
      animation: cs-move 48s linear infinite;
    }

    #cs-news .lane:hover .track {
      animation-play-state: paused;
    }

    #cs-news a {
      color: #fff;
      text-decoration: none;
      margin-right: 48px;
    }

    #cs-news .inj {
      color: #ffb0b0;
      margin-right: 40px;
    }

    #cs-news .injury-list {
      max-height: 260px;
      overflow-y: auto;
      border-top: 1px solid #303540;
      margin-top: 10px;
    }

    #cs-news .injury-row {
      padding: 9px 4px;
      border-bottom: 1px solid #303540;
      line-height: 1.5;
    }

    #cs-news .injury-row strong {
      color: #f7f7fa;
    }

    #cs-news .injury-row .status {
      color: #ffb0b0;
    }

    @keyframes cs-move {
      from { transform: translateX(20%); }
      to { transform: translateX(-100%); }
    }

    @media (prefers-reduced-motion: reduce) {
      #cs-news .track {
        animation: none;
        white-space: normal;
      }
    }
  `;

  document.head.appendChild(style);

  let root = document.getElementById("cs-news");

  if (!root) {
    root = document.createElement("section");
    root.id = "cs-news";

    const anchor =
      document.querySelector("main") || document.body;

    anchor.prepend(root);
  }

  root.innerHTML = `
    <h2>NBA News & Injury Updates</h2>
    <p class="muted">Loading ESPN reports...</p>
  `;

  let stories = [];
  let reports = [];
  let lastError = "";
  let refreshing = false;

  function formatTime(value) {
    if (!value) return "Unknown";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return String(value);
    }

    return date.toLocaleString();
  }

  function render() {
    const headlines = stories.slice(0, 18)
      .map(story => {
        const url = safeUrl(story.url);
        const title = esc(story.headline);

        return url
          ? `<a href="${esc(url)}"
                target="_blank"
                rel="noopener noreferrer">${title}</a>`
          : `<span>${title}</span>`;
      }).join("");

    const sorted = [...reports].sort((a, b) => {
      const priority = status => {
        const s = String(status || "").toUpperCase();

        if (s.includes("OUT")) return 0;
        if (s.includes("DOUBTFUL")) return 1;
        if (s.includes("QUESTIONABLE")) return 2;
        return 3;
      };

      return priority(a.status) - priority(b.status);
    });

    const injuryTicker = sorted
      .map(item => `
        <span class="inj">
          ${esc(item.team)} ·
          ${esc(item.player_name)} —
          ${esc(item.status || "Status not specified")}
        </span>
      `).join("");

    const injuryList = sorted.map(item => `
      <div class="injury-row">
        <strong>
          ${esc(item.team)} · ${esc(item.player_name)}
        </strong>
        <span class="status">
          — ${esc(item.status || "Status not specified")}
        </span>
        ${item.detail
          ? `<div class="muted">${esc(item.detail)}</div>`
          : ""}
      </div>
    `).join("");

    const last =
      reports[0]?.last_updated_utc ||
      stories[0]?.last_updated_utc ||
      "";

    root.innerHTML = `
      <h2>NBA News & Injury Updates</h2>

      <p class="muted">
        ESPN injury data · Last CSV update:
        ${esc(formatTime(last))}
        · Website checks every 5 minutes
      </p>

      ${lastError
        ? `<p class="muted">
             Latest refresh failed. Showing previously
             loaded information.
           </p>`
        : ""}

      <div class="lane">
        <div class="track">
          ${headlines || "News unavailable."}
        </div>
      </div>

      <div class="lane">
        <div class="track">
          ${injuryTicker || "No injury reports available."}
        </div>
      </div>

      <h3>All Reported Injuries (${sorted.length})</h3>

      <div class="injury-list">
        ${injuryList ||
          '<p class="muted">No ESPN injury records available.</p>'}
      </div>

      <p class="muted">
        Injury status is sourced from ESPN and may lag
        behind breaking news or official team announcements.
      </p>
    `;
  }

  async function refresh() {
    if (refreshing) return;
    refreshing = true;

    try {
      const [newsResult, injuryResult] =
        await Promise.allSettled([
          load("nba_news.csv"),
          load("nba_injuries.csv")
        ]);

      lastError = "";

      if (newsResult.status === "fulfilled") {
        stories = newsResult.value;
      } else {
        lastError = "news";
      }

      if (injuryResult.status === "fulfilled") {
        reports = injuryResult.value;

        window.CourtsideInjuries = reports;

        window.dispatchEvent(
          new Event("courtside-injuries-ready")
        );
      } else {
        lastError = "injuries";
      }

      render();
    } catch (error) {
      console.error("Courtside injury refresh:", error);
      lastError = error.message;
      render();
    } finally {
      refreshing = false;
    }
  }

  refresh();

  setInterval(refresh, REFRESH_MS);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
})();
