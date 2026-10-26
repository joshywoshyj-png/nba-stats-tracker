/* Courtside schedule + position-defense-adjusted stat estimates.
   Add <script src="courtside_schedule_widget.js" defer></script> before </body>.
*/
(async function () {
  const BASE='https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/';
  const css=document.createElement('style');
  css.textContent=`#cs-schedule{font:14px system-ui,sans-serif;background:#14171f;color:#f5f6fa;border:1px solid #353944;border-radius:18px;padding:22px;margin:24px auto;max-width:1200px}#cs-schedule h2{margin:0 0 8px;font-size:25px}#cs-schedule select{background:#202530;color:white;border:1px solid #555;border-radius:8px;padding:10px;max-width:100%;width:100%;margin:12px 0}#cs-schedule table{border-collapse:collapse;width:100%;min-width:760px}#cs-schedule td,#cs-schedule th{text-align:left;border-bottom:1px solid #343844;padding:10px}#cs-schedule th{color:#d5d7df}#cs-schedule .scroll{overflow-x:auto}#cs-schedule .muted{color:#b3b9c6}#cs-schedule .tag{color:#ff6868}`;
  document.head.appendChild(css);
  const root=document.createElement('section');root.id='cs-schedule';root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p class="muted">Loading the published NBA schedule and season statistics…</p>';
  const anchor=document.querySelector('main') || document.body;
  anchor.appendChild(root);
  const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function csv(txt){const rows=[];let row=[],cell='',quoted=false;for(let i=0;i<txt.length;i++){const c=txt[i];if(c==='"'){if(quoted&&txt[i+1]==='"'){cell+='"';i++}else quoted=!quoted}else if(c===','&&!quoted){row.push(cell);cell=''}else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&txt[i+1]==='\n')i++;row.push(cell);if(row.some(x=>x!==''))rows.push(row);row=[];cell=''}else cell+=c;}if(cell||row.length){row.push(cell);rows.push(row)}const headers=rows.shift()||[];return rows.map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]||''])))}
  async function load(name){const r=await fetch(BASE+name+'?t='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(name+' HTTP '+r.status);return csv(await r.text())}
  const n=x=>Number(x)||0;
  const group=p=>['PG','SG','G'].includes(p)?'G':['SF','PF','F'].includes(p)?'F':p==='C'?'C':'';
  try{
    const [schedule,players,defense,logs]=await Promise.all([load('nba_schedule.csv'),load('nba_stats.csv'),load('nba_opponent_defense.csv'),load('nba_game_logs.csv')]);
    const now=Date.now();const upcoming=schedule.filter(g=>new Date(g.date_utc).getTime()>now-3*3600000).sort((a,b)=>new Date(a.date_utc)-new Date(b.date_utc));
    if(!upcoming.length){root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p>No upcoming games found in the published schedule. Check when the updater last ran.</p>';return}
    root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p class="muted">ESPN schedule saved by GitHub Actions. Estimates are illustrative season-based statistics, not confirmed lineups.</p><label for="cs-game">Select upcoming game</label><select id="cs-game"></select><div id="cs-game-details"></div>';
    const select=root.querySelector('select');
    upcoming.forEach((g,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${g.away} @ ${g.home} · ${new Date(g.date_utc).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}`;select.appendChild(o)});
    function render(){const g=upcoming[Number(select.value)||0],out=root.querySelector('#cs-game-details');const rows=[];
      for(const [team,opp] of [[g.away,g.home],[g.home,g.away]]){
        for(const p of players.filter(x=>x.team===team&&n(x.games_played)>0)){
          const recent=logs.filter(l=>l.player_id===p.player_id).sort((a,b)=>b.date.localeCompare(a.date)).slice(0,5);
          const pos=recent.find(l=>l.position)?.position||'';
          let d=defense.find(x=>x.opponent===opp&&x.position===pos&&x.position_type==='position');
          if(!d){const grp=group(pos);d=defense.find(x=>x.opponent===opp&&x.position===grp&&x.position_type==='position_group')}
          const metrics=[['points','PTS'],['rebounds','REB'],['assists','AST'],['three_pointers','3PM'],['steals','STL'],['blocks','BLK']];
          const est=metrics.map(([k])=>{const base=n(p[k+'_pg']);const last=recent.length?recent.reduce((sum,l)=>sum+n(l[k]),0)/recent.length:base;const baseline=base*.8+last*.2;
            if(!d||n(d.player_games)<1)return baseline.toFixed(1);
            // Adjust modestly relative to all other defenses' allowed average at same position.
            const comps=defense.filter(x=>x.position===d.position&&x.position_type===d.position_type&&n(x.player_games)>0);
            const league=comps.reduce((sum,x)=>sum+n(x[k+'_allowed_pg']),0)/(comps.length||1);
            const ratio=league>0?n(d[k+'_allowed_pg'])/league:1;
            return (baseline*Math.max(.85,Math.min(1.15,1+.35*(ratio-1)))).toFixed(1);
          });
          rows.push(`<tr><td>${esc(p.player_name)}</td><td>${esc(team)}</td><td>${esc(opp)}</td><td>${esc(pos||'—')}</td><td>${d?esc(d.player_games):'—'}</td>${est.map(v=>`<td>${v}</td>`).join('')}</tr>`);
        }
      }
      out.innerHTML=`<p class="muted">${esc(g.away)} at ${esc(g.home)} · ${esc(new Date(g.date_utc).toLocaleString())} · ${esc(g.status_detail||g.status)} · Schedule updated ${esc(g.last_updated_utc||'unknown')}</p><p class="muted">Defense sample = opposing player-games at that position. If no matching defense data exists, estimates use season and recent averages only. This list does not confirm who will play.</p><div class="scroll"><table><thead><tr><th>Player</th><th>Team</th><th>Opponent</th><th>Position</th><th>Defense sample</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th><th>STL</th><th>BLK</th></tr></thead><tbody>${rows.join('')||'<tr><td colspan="11">No matching player statistics</td></tr>'}</tbody></table></div>`;
    }
    select.addEventListener('change',render);render();
  }catch(err){root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p class="tag">Could not load schedule or statistics: '+esc(err.message)+'</p><p class="muted">Run GitHub Actions after uploading the updater and check that nba_schedule.csv exists.</p>';}
})();
