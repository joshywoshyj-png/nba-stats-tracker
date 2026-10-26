/* Courtside schedule + opponent defense + injury-aware stat estimates */
(async function () {
 const BASE='https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/';
 const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function csv(s){const rows=[];let row=[],v='',q=false;for(let i=0;i<s.length;i++){let c=s[i];if(c==='"'){if(q&&s[i+1]==='"'){v+='"';i++}else q=!q;}else if(c===','&&!q){row.push(v);v='';}else if((c==='\n'||c==='\r')&&!q){if(c==='\r'&&s[i+1]==='\n')i++;row.push(v);if(row.some(x=>x))rows.push(row);row=[];v='';}else v+=c;}if(row.length||v){row.push(v);rows.push(row);}let h=rows.shift()||[];return rows.map(r=>Object.fromEntries(h.map((k,i)=>[k,r[i]||''])));}
 async function load(name){const r=await fetch(BASE+name+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(name+' HTTP '+r.status);return csv(await r.text());}
 const n=x=>Number(x)||0, group=p=>['PG','SG','G'].includes(p)?'G':['SF','PF','F'].includes(p)?'F':p==='C'?'C':'';
 const normalize=s=>String(s||'').toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z]/g,'');
 const styles=document.createElement('style');styles.textContent=`#cs-schedule{font:14px system-ui,sans-serif;background:#14171f;color:#f5f6fa;border:1px solid #353944;border-radius:18px;padding:22px;margin:24px auto;max-width:1200px}#cs-schedule h2{margin:0 0 8px;font-size:25px}#cs-schedule select{background:#202530;color:white;border:1px solid #555;border-radius:8px;padding:10px;max-width:100%;width:100%;margin:12px 0}#cs-schedule table{border-collapse:collapse;width:100%;min-width:1000px}#cs-schedule td,#cs-schedule th{text-align:left;border-bottom:1px solid #343844;padding:10px}#cs-schedule th{color:#d5d7df}#cs-schedule .scroll{overflow-x:auto}#cs-schedule .muted{color:#b3b9c6}#cs-schedule .tag{color:#ff6868}#cs-schedule .inj{color:#ffb0b0}`;document.head.appendChild(styles);
 const root=document.createElement('section');root.id='cs-schedule';root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p>Loading schedule, player stats and injuries…</p>'; (document.querySelector('main')||document.body).appendChild(root);
 try{
  const [schedule,players,defense,logs,injuriesResult]=await Promise.all([load('nba_schedule.csv'),load('nba_stats.csv'),load('nba_opponent_defense.csv'),load('nba_game_logs.csv'),load('nba_injuries.csv').then(x=>({ok:true,rows:x})).catch(()=>({ok:false,rows:[]}))]);
  const injuries=injuriesResult.rows, now=Date.now();
  const upcoming=schedule.filter(g=>new Date(g.date_utc).getTime()>now-3*3600000).sort((a,b)=>new Date(a.date_utc)-new Date(b.date_utc));
  if(!upcoming.length){root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p>No upcoming games in the published schedule. Run your GitHub updater.</p>';return;}
  root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p class="muted">ESPN schedule · Current-season stats · Position-specific defense · ESPN injury reports. Estimates are illustrative; player availability and starting lineups are not confirmed.</p><label for="cs-game">Upcoming game</label><select id="cs-game"></select><div id="cs-game-details"></div>';
  const sel=root.querySelector('select');upcoming.forEach((g,i)=>{let o=document.createElement('option');o.value=i;o.textContent=`${g.away} @ ${g.home} · ${new Date(g.date_utc).toLocaleString(undefined,{month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})}`;sel.appendChild(o)});
  function statusFor(p){return injuries.find(i=>(i.player_id&&p.player_id&&String(i.player_id)===String(p.player_id))||(i.team===p.team&&normalize(i.player_name)===normalize(p.player_name)));}
  function isOut(i){return i&&/^(out|inactive|injured reserve|suspended|not with team)$/i.test(String(i.status).trim());}
  function render(){const g=upcoming[Number(sel.value)||0],out=root.querySelector('#cs-game-details'),rows=[];
   for(const [team,opp] of [[g.away,g.home],[g.home,g.away]]){
    const teamPlayers=players.filter(p=>p.team===team&&n(p.games_played)>0);
    const absent=teamPlayers.filter(p=>isOut(statusFor(p)));
    // Capped opportunity adjustment: only known OUT teammates count. It is not a replacement for rotations/minutes data.
    const absentMinutes=absent.reduce((s,p)=>s+n(p.minutes_pg),0);
    const availableCount=teamPlayers.filter(p=>!isOut(statusFor(p))).length;
    const teammateBoost=Math.min(.08,absentMinutes/240*.22)*(availableCount?1:0);
    for(const p of teamPlayers){
     const injury=statusFor(p),outStatus=isOut(injury);
     const recent=logs.filter(l=>String(l.player_id)===String(p.player_id)).sort((a,b)=>String(b.date).localeCompare(String(a.date))).slice(0,5);
     const pos=recent.find(l=>l.position)?.position||'';
     let d=defense.find(x=>x.opponent===opp&&x.position===pos&&x.position_type==='position');
     if(!d){const grp=group(pos);d=defense.find(x=>x.opponent===opp&&x.position===grp&&x.position_type==='position_group');}
     const metrics=['points','rebounds','assists','three_pointers','steals','blocks'];
     const values=metrics.map(k=>{
      if(outStatus)return '—';
      const season=n(p[k+'_pg']),last=recent.length?recent.reduce((s,l)=>s+n(l[k]),0)/recent.length:season;
      let est=.8*season+.2*last;
      if(d&&n(d.player_games)>0){
       const comps=defense.filter(x=>x.position===d.position&&x.position_type===d.position_type&&n(x.player_games)>0);
       const league=comps.reduce((s,x)=>s+n(x[k+'_allowed_pg']),0)/(comps.length||1);
       if(league>0){const ratio=n(d[k+'_allowed_pg'])/league;est*=Math.max(.85,Math.min(1.15,1+.35*(ratio-1)));}
      }
      est*=1+teammateBoost;
      return est.toFixed(1);
     });
     const stat=injury?injury.status||'Reported':'Not listed';
     rows.push(`<tr><td>${esc(p.player_name)}</td><td>${esc(team)}</td><td>${esc(opp)}</td><td>${esc(pos||'—')}</td><td class="${injury?'inj':''}">${esc(stat)}</td><td>${d?esc(d.player_games):'—'}</td>${values.map(x=>`<td>${x}</td>`).join('')}</tr>`);
    }
   }
   const updated=injuries[0]?.last_updated_utc||'unknown';
   out.innerHTML=`<p class="muted">${esc(g.away)} @ ${esc(g.home)} · ${esc(new Date(g.date_utc).toLocaleString())} · ${esc(g.status_detail||g.status)} · Schedule updated ${esc(g.last_updated_utc||'unknown')}</p><p class="muted">Injury report updated: ${esc(updated)}. ${injuriesResult.ok?'Players not listed are NOT guaranteed healthy.':'Injury CSV unavailable: estimates do not include injury adjustments.'} Confirmed OUT players show no game estimate. Questionable/Doubtful/Probable remain unadjusted unless officially OUT. Available teammates receive at most an 8% adjustment based on reported OUT teammates’ minutes; this is a rough assumption, not a verified rotation projection. Defensive sample is opposing player-games at that position.</p><div class="scroll"><table><thead><tr><th>Player</th><th>Team</th><th>Opponent</th><th>Pos</th><th>Injury status</th><th>Defense sample</th><th>PTS</th><th>REB</th><th>AST</th><th>3PM</th><th>STL</th><th>BLK</th></tr></thead><tbody>${rows.join('')||'<tr><td colspan="12">No matching player statistics</td></tr>'}</tbody></table></div>`;
  }
  sel.addEventListener('change',render);render();
 }catch(e){root.innerHTML='<h2>NBA Schedule & Matchup Stats</h2><p class="tag">Could not load schedule or statistics: '+esc(e.message)+'</p>';}
})();
