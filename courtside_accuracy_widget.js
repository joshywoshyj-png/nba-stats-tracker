/* Courtside accuracy dashboard: reads frozen pregame snapshots and actual results. */
(async function () {
 const BASE='https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/';
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const stats=[['points','PTS'],['rebounds','REB'],['assists','AST'],['three_pointers','3PM'],['steals','STL'],['blocks','BLK']];
 const parse=s=>{let rows=[],r=[],v='',q=false;for(let i=0;i<s.length;i++){const c=s[i];if(c==='"'){if(q&&s[i+1]==='"'){v+='"';i++;}else q=!q;}else if(c===','&&!q){r.push(v);v='';}else if((c==='\r'||c==='\n')&&!q){if(c==='\r'&&s[i+1]==='\n')i++;r.push(v);if(r.some(Boolean))rows.push(r);r=[];v='';}else v+=c;}if(v||r.length){r.push(v);rows.push(r);}const h=(rows.shift()||[]).map(x=>x.replace(/^\uFEFF/,''));return rows.map(row=>Object.fromEntries(h.map((k,i)=>[k,row[i]??''])))};
 const load=async file=>{const r=await fetch(BASE+file+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(`${file} not published yet`);return parse(await r.text());};
 const root=document.createElement('section');root.id='cs-accuracy';root.className='section panel';root.innerHTML='<h2>Prediction Accuracy & History</h2><p class="small">Loading saved estimates and completed games…</p>';
 const anchor=document.querySelector('#cs-schedule');if(anchor)anchor.after(root);else (document.querySelector('.wrap')||document.body).appendChild(root);
 try {
  const [history,results]=await Promise.all([load('nba_prediction_history.csv'),load('nba_prediction_results.csv')]);
  const count=results.length;
  let html='<h2>Prediction Accuracy & History</h2><p class="small">Pregame estimates are saved once and never overwritten. Only completed player games with matching ESPN logs are scored. Lower MAE is better. Current-season model; not a validated forecast.</p>';
  if(!history.length)html+='<p class="small">No snapshots yet. The updater saves them before upcoming games, then scores them after ESPN publishes results.</p>';
  if(count){
   html+='<h3>Mean absolute error (MAE) · '+count+' player-games</h3><div class="tablewrap"><table><thead><tr><th>Stat</th><th>Courtside MAE</th><th>Season-average MAE</th><th>Difference</th></tr></thead><tbody>';
   for(const [key,label] of stats){const model=results.reduce((s,r)=>s+Math.abs(Number(r['pred_'+key])-Number(r['actual_'+key])),0)/count;const baseline=results.reduce((s,r)=>s+Math.abs(Number(r['baseline_'+key])-Number(r['actual_'+key])),0)/count;html+=`<tr><td>${label}</td><td>${model.toFixed(2)}</td><td>${baseline.toFixed(2)}</td><td>${(model-baseline).toFixed(2)}</td></tr>`;}
   html+='</tbody></table></div><p class="small">Negative difference means the Courtside model had lower error than the season-average baseline. These results cover only players with a completed game log, not players who did not play.</p>';
  }else html+='<p class="small">No scored results yet. Scores appear after saved pregame estimates can be matched to completed ESPN player logs.</p>';
  const latest=[...results].sort((a,b)=>String(b.game_date).localeCompare(String(a.game_date))).slice(0,25);
  if(latest.length){html+='<h3>Recent predictions vs. results</h3><div class="tablewrap"><table><thead><tr><th>Date</th><th>Player</th><th>Matchup</th><th>Stat</th><th>Predicted</th><th>Actual</th><th>Absolute error</th></tr></thead><tbody>';
   for(const r of latest)for(const [key,label] of stats.slice(0,3))html+=`<tr><td>${escape(r.game_date)}</td><td>${escape(r.player_name)}</td><td>${escape(r.team)} vs ${escape(r.opponent)}</td><td>${label}</td><td>${Number(r['pred_'+key]).toFixed(1)}</td><td>${escape(r['actual_'+key])}</td><td>${Number(r['error_'+key]).toFixed(1)}</td></tr>`;
   html+='</tbody></table></div>';
  }
  const pending=history.filter(r=>!results.some(x=>x.game_key===r.game_key&&x.player_id===r.player_id));
  html+=`<p class="small">Saved predictions: ${history.length} · Scored player-games: ${results.length} · Awaiting matching results: ${pending.length}</p>`;
  root.innerHTML=html;
 }catch(e){root.innerHTML='<h2>Prediction Accuracy & History</h2><p class="small">'+escape(e.message)+'. Run the updated GitHub Actions workflow to create the new CSV files.</p>';}
})();
