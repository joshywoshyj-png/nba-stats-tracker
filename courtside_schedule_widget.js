
(async function () {
  "use strict";

  const BASE = "https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/";
  const STATS = ["points","rebounds","assists","three_pointers","steals","blocks"];
  const LABELS = ["PTS","REB","AST","3PM","STL","BLK"];
  const n = x => Number.isFinite(Number(x)) ? Number(x) : 0;
  const clamp = (x,a,b) => Math.max(a,Math.min(b,x));
  const norm = x => String(x ?? "").trim().toUpperCase();
  const cleanName = x => String(x ?? "").toLowerCase()
    .normalize("NFKD").replace(/[\u0300-\u036f]/g,"")
    .replace(/[^a-z]/g,"");
  const esc = x => String(x ?? "").replace(/[&<>"']/g,c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const group = p => ["PG","SG","G"].includes(norm(p)) ? "G"
    : ["SF","PF","F"].includes(norm(p)) ? "F"
    : norm(p) === "C" ? "C" : "";

  function csv(text) {
    let rows=[], row=[], cell="", quoted=false;
    for(let i=0;i<text.length;i++) {
      const c=text[i];
      if(c==='"') {
        if(quoted && text[i+1]==='"') {cell+='"';i++;}
        else quoted=!quoted;
      } else if(c===","&&!quoted) {
        row.push(cell);cell="";
      } else if((c==="\n"||c==="\r")&&!quoted) {
        if(c==="\r"&&text[i+1]==="\n")i++;
        row.push(cell);
        if(row.some(x=>x!==""))rows.push(row);
        row=[];cell="";
      } else cell+=c;
    }
    if(cell||row.length){row.push(cell);rows.push(row);}
    const headers=rows.shift()||[];
    return rows.map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]??""])));
  }

  async function load(file) {
    const response=await fetch(BASE+file+"?t="+Date.now(),{cache:"no-store"});
    if(!response.ok)throw Error(file+": HTTP "+response.status);
    return csv(await response.text());
  }

  function dateKey(value) {
    const d=new Date(value);
    if(!Number.isFinite(d.getTime()))return "";
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
  }

  function minutes(log) {
    return n(log.minutes ?? log.minutes_played ?? log.minutes_pg);
  }

  function rate(logs,stat,fallback) {
    const valid=logs.filter(l=>minutes(l)>0 && String(l[stat]??"").trim()!=="");
    const total=valid.reduce((s,l)=>s+minutes(l),0);
    return total>0?valid.reduce((s,l)=>s+n(l[stat]),0)/total:fallback;
  }

  // Accept several possible 3PA column names.
  const ATTEMPT_COLUMNS=[
    "three_pointers_attempted",
    "three_point_attempts",
    "three_point_attempted",
    "three_pointers_attempts",
    "three_point_attempts_pg",
    "three_pointers_attempted_pg",
    "three_pa","three_pa_pg","three_point_attempts_per_game",
    "three_pointers_attempted_per_game",
    "fg3a","fg3a_pg","3pa","3pa_pg"
  ];

  function attempts(row) {
    for(const key of ATTEMPT_COLUMNS) {
      if(row && Object.prototype.hasOwnProperty.call(row,key) &&
         String(row[key]??"").trim()!=="") {
        return n(row[key]);
      }
    }
    return null;
  }

  function threePrediction(player,recent,projectedMinutes,
                           defenseFactor,paceFactor,injuryBoost) {
    const seasonMinutes=n(player.minutes_pg);
    const seasonMakes=n(player.three_pointers_pg);
    const seasonAttempts=attempts(player);

    const fallback=()=>{
      const sr=seasonMinutes>0?seasonMakes/seasonMinutes:0;
      const l10=rate(recent.slice(0,10),"three_pointers",sr);
      const valid=recent.filter(l=>minutes(l)>0 &&
        String(l.three_pointers??"").trim()!=="");
      const games=n(player.games_played);
      const sw=games/(games+12);
      const stable=sw*sr+(1-sw)*l10;
      const rw=valid.length/(valid.length+10);
      return projectedMinutes*((1-rw)*stable+rw*l10)*
        defenseFactor*paceFactor*(1+injuryBoost);
    };

    if(seasonAttempts===null || seasonAttempts<=0 ||
       seasonMinutes<=0) return Math.max(0,fallback());

    // Season 3PA is per game; game-log 3PA is a game total.
    const seasonAttemptRate=seasonAttempts/seasonMinutes;
    const recentWithAttempts=recent.filter(l=>
      minutes(l)>0 && attempts(l)!==null);

    if(!recentWithAttempts.length)return Math.max(0,fallback());

    function attemptRate(logs,fallbackRate) {
      const valid=logs.filter(l=>minutes(l)>0&&attempts(l)!==null);
      const totalMinutes=valid.reduce((s,l)=>s+minutes(l),0);
      return totalMinutes>0
        ?valid.reduce((s,l)=>s+attempts(l),0)/totalMinutes
        :fallbackRate;
    }

    const l10=attemptRate(recent.slice(0,10),seasonAttemptRate);
    const l5=attemptRate(recent.slice(0,5),seasonAttemptRate);
    const projectedAttempts=projectedMinutes*(
      .50*seasonAttemptRate+.30*l10+.20*l5
    );

    const seasonPct=clamp(seasonMakes/seasonAttempts,0,1);
    const recentValid=recent.slice(0,10).filter(l=>
      minutes(l)>0 && attempts(l)!==null &&
      String(l.three_pointers??"").trim()!=="");
    const recentAttempts=recentValid.reduce((s,l)=>s+attempts(l),0);
    const recentMakes=recentValid.reduce((s,l)=>s+n(l.three_pointers),0);

    // 60 prior attempts stabilize small-sample shooting swings.
    const expectedPct=clamp(
      (recentMakes+60*seasonPct)/(recentAttempts+60),0,1
    );

    return Math.max(0,projectedAttempts*expectedPct*
      defenseFactor*paceFactor*(1+injuryBoost));
  }

  const style=document.createElement("style");
  style.textContent=`
    #cs-schedule{font:14px system-ui,sans-serif;background:#14171f;
      color:#f5f6fa;border:1px solid #353944;border-radius:18px;
      padding:22px;margin:24px auto;max-width:1200px}
    #cs-schedule h2{margin:0 0 8px;font-size:25px}
    #cs-schedule select{background:#202530;color:white;
      border:1px solid #555;border-radius:8px;padding:10px;
      width:100%;margin:12px 0}
    #cs-schedule table{border-collapse:collapse;width:100%;min-width:1000px}
    #cs-schedule td,#cs-schedule th{text-align:left;
      border-bottom:1px solid #343844;padding:10px}
    #cs-schedule th{color:#d5d7df}
    #cs-schedule .scroll{overflow-x:auto}
    #cs-schedule .muted{color:#b3b9c6;line-height:1.5}
    #cs-schedule .inj{color:#ffb0b0}
    #cs-schedule .error{color:#ff6868}
  `;
  document.head.appendChild(style);

  let root=document.getElementById("cs-schedule");
  if(!root) {
    root=document.createElement("section");
    root.id="cs-schedule";
    (document.querySelector("main")||document.body).appendChild(root);
  }
  root.innerHTML="<h2>NBA Schedule & Matchup Stats</h2><p>Loading...</p>";

  try {
    const [schedule,players,defense,logs,paceRows,injuries]=await Promise.all([
      load("nba_schedule.csv"),load("nba_stats.csv"),
      load("nba_opponent_defense.csv"),load("nba_game_logs.csv"),
      load("nba_team_pace.csv"),load("nba_injuries.csv").catch(()=>[])
    ]);

    const paceMap=new Map(paceRows.map(x=>[norm(x.team),x]));
    const logsMap=new Map();
    for(const log of logs) {
      const id=String(log.player_id??"");
      if(!logsMap.has(id))logsMap.set(id,[]);
      logsMap.get(id).push(log);
    }
    for(const list of logsMap.values())
      list.sort((a,b)=>String(b.date).localeCompare(String(a.date)));

    const today=dateKey(new Date());
    const games=schedule.filter(g=>{
      const d=dateKey(g.date_utc);
      return d&&d>=today;
    }).sort((a,b)=>new Date(a.date_utc)-new Date(b.date_utc));

    if(!games.length) {
      root.innerHTML="<h2>NBA Schedule & Matchup Stats</h2>"+
        "<p>No games found for today or later.</p>";
      return;
    }

    const baseline=new Map();
    for(const d of defense) {
      const count=n(d.player_games);
      if(count<=0)continue;
      for(const stat of STATS) {
        const key=[d.position_type,d.position,stat].join("|");
        if(!baseline.has(key))baseline.set(key,{total:0,count:0});
        const b=baseline.get(key);
        b.total+=n(d[stat+"_allowed_pg"])*count;
        b.count+=count;
      }
    }

    function paceFactor(team,opponent) {
      const a=paceMap.get(norm(team)),b=paceMap.get(norm(opponent));
      if(!a||!b)return 1;
      const own=n(a.adjusted_pace),other=n(b.adjusted_pace);
      return own>0&&other>0
        ?clamp(((own+other)/2)/own,.9,1.1):1;
    }

    function defensePace(opponent) {
      const p=paceMap.get(norm(opponent));
      if(!p)return 1;
      const league=n(p.league_average_pace),opp=n(p.adjusted_pace);
      return league>0&&opp>0?clamp(league/opp,.85,1.15):1;
    }

    function defenseFactor(d,stat,opponent) {
      if(!d)return 1;
      const b=baseline.get([d.position_type,d.position,stat].join("|"));
      if(!b||b.count<=0||b.total<=0)return 1;
      let raw=n(d[stat+"_allowed_pg"])/(b.total/b.count);
      if(["points","rebounds","assists"].includes(stat))
        raw*=defensePace(opponent);
      const count=n(d.player_games);
      return clamp(1+(count/(count+20))*.5*(raw-1),.85,1.15);
    }

    function injuryFor(player) {
      return injuries.find(i=>
        (i.player_id&&player.player_id&&
         String(i.player_id)===String(player.player_id))||
        (norm(i.team)===norm(player.team)&&
         cleanName(i.player_name)===cleanName(player.player_name))
      );
    }

    function isOut(i) {
      return !!i&&["OUT","INACTIVE","INJURED RESERVE",
        "SUSPENDED","NOT WITH TEAM"].includes(norm(i.status));
    }

    function predict(player,recent,mins,stat,d,opponent,team,boost) {
      const seasonMinutes=n(player.minutes_pg);
      const seasonRate=seasonMinutes>0
        ?n(player[stat+"_pg"])/seasonMinutes:0;
      const l10=rate(recent.slice(0,10),stat,seasonRate);
      const l5=rate(recent.slice(0,5),stat,seasonRate);
      const df=defenseFactor(d,stat,opponent);
      const pf=paceFactor(team,opponent);

      if(stat==="three_pointers")
        return threePrediction(player,recent,mins,df,pf,boost);

      let r;
      if(stat==="points")
        r=.55*seasonRate+.30*l10+.15*l5;
      else if(stat==="rebounds")
        r=.50*seasonRate+.30*l10+.20*l5;
      else if(stat==="assists")
        r=.45*seasonRate+.35*l10+.20*l5;
      else {
        const valid=recent.filter(l=>minutes(l)>0&&
          String(l[stat]??"").trim()!=="");
        const games=n(player.games_played);
        const w=games/(games+12);
        const stable=w*seasonRate+(1-w)*l10;
        const rw=valid.length/(valid.length+10);
        r=(1-rw)*stable+rw*l10;
      }

      const pace=["points","rebounds","assists"].includes(stat)?pf:1;
      return Math.max(0,mins*r*df*pace*(1+boost));
    }

    root.innerHTML=`
      <h2>NBA Schedule & Matchup Stats</h2>
      <p class="muted">Current-season estimates based on recent
      performance, opponent defense, minutes, injuries and pace.
      Three-pointers use attempts × estimated shooting percentage
      when attempts data is available.</p>
      <label for="cs-game">Today's and upcoming games</label>
      <select id="cs-game"></select>
      <div id="cs-game-details"></div>
    `;

    const select=root.querySelector("#cs-game");
    games.forEach((g,i)=>{
      const option=document.createElement("option");
      option.value=String(i);
      option.textContent=`${g.away} @ ${g.home} · `+
        new Date(g.date_utc).toLocaleString(undefined,{
          month:"short",day:"numeric",hour:"numeric",minute:"2-digit"
        });
      select.appendChild(option);
    });

    function render() {
      const game=games[Number(select.value)||0];
      const rows=[];
      for(const [team,opponent] of [
        [game.away,game.home],[game.home,game.away]
      ]) {
        const roster=players.filter(p=>norm(p.team)===norm(team)&&
          n(p.games_played)>0);
        const absent=roster.reduce((s,p)=>s+
          (isOut(injuryFor(p))?n(p.minutes_pg):0),0);
        const available=roster.some(p=>!isOut(injuryFor(p)));
        const boost=available?Math.min(.08,absent/240*.22):0;

        for(const p of roster) {
          const injury=injuryFor(p),out=isOut(injury);
          const recent=(logsMap.get(String(p.player_id))||[])
            .filter(l=>String(l.date??"").slice(0,10)<
              dateKey(game.date_utc)).slice(0,10);
          const position=recent.find(l=>l.position)?.position||"";
          let d=defense.find(x=>norm(x.opponent)===norm(opponent)&&
            norm(x.position)===norm(position)&&
            x.position_type==="position");
          if(!d)d=defense.find(x=>norm(x.opponent)===norm(opponent)&&
            norm(x.position)===group(position)&&
            x.position_type==="position_group");

          const minsRecent=recent.map(minutes).filter(x=>x>0);
          const seasonMins=n(p.minutes_pg);
          const average=minsRecent.length
            ?minsRecent.reduce((a,b)=>a+b,0)/minsRecent.length
            :seasonMins;
          const projected=clamp(.75*seasonMins+.25*average,0,48);
          const values=STATS.map(stat=>out?"—":
            predict(p,recent,projected,stat,d,opponent,team,boost).toFixed(1));

          rows.push(`<tr>
            <td>${esc(p.player_name)}</td><td>${esc(team)}</td>
            <td>${esc(opponent)}</td><td>${esc(position||"—")}</td>
            <td class="${injury?"inj":""}">${esc(injury?.status||"Not listed")}</td>
            <td>${d?esc(d.player_games):"—"}</td>
            ${values.map(v=>`<td>${v}</td>`).join("")}
          </tr>`);
        }
      }

      root.querySelector("#cs-game-details").innerHTML=`
        <p class="muted">${esc(game.away)} @ ${esc(game.home)} ·
        ${esc(new Date(game.date_utc).toLocaleString())} ·
        ${esc(game.status_detail||game.status||"Scheduled")}</p>
        <p class="muted">OUT players have no estimates.
        These are pregame-style projections, not live box-score updates.</p>
        <div class="scroll"><table><thead><tr>
          <th>Player</th><th>Team</th><th>Opponent</th>
          <th>Pos</th><th>Injury</th><th>Defense sample</th>
          ${LABELS.map(x=>`<th>${x}</th>`).join("")}
        </tr></thead><tbody>${rows.join("")||
          '<tr><td colspan="12">No player stats found</td></tr>'}
        </tbody></table></div>
      `;
    }

    select.addEventListener("change",render);
    render();
  } catch(error) {
    console.error("Courtside error:",error);
    root.innerHTML=`<h2>NBA Schedule & Matchup Stats</h2>
      <p class="error">Could not load predictor: ${esc(error.message)}</p>`;
  }
})();
