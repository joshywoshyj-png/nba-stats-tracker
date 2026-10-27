/* Courtside enhanced prediction-vs-actual dashboard. */
(async function () {
  'use strict';
  const BASE='https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/';
  const STATS=[['points','PTS'],['rebounds','REB'],['assists','AST'],['three_pointers','3PM'],['steals','STL'],['blocks','BLK']];
  const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num=x=>Number.isFinite(Number(x))?Number(x):0;
  function csv(text){const rows=[];let row=[],cell='',q=false;for(let i=0;i<text.length;i++){let c=text[i];if(c==='"'){if(q&&text[i+1]==='"'){cell+='"';i++;}else q=!q;}else if(c===','&&!q){row.push(cell);cell='';}else if((c==='\n'||c==='\r')&&!q){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(x=>x!==''))rows.push(row);row=[];cell='';}else cell+=c;}if(cell||row.length){row.push(cell);rows.push(row);}const headers=rows.shift()||[];return rows.map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i]??''])));}
  let root=document.getElementById('cs-accuracy-plus');
  if(!root){root=document.createElement('section');root.id='cs-accuracy-plus';(document.querySelector('main')||document.body).appendChild(root);}
  root.style.cssText='max-width:1200px;margin:24px auto;padding:22px;border:1px solid #353944;border-radius:18px;background:#14171f;color:#f5f6fa;font:14px system-ui,sans-serif';
  root.innerHTML='<h2>Prediction Accuracy — Detailed</h2><p>Loading completed-game results...</p>';
  try{
    const res=await fetch(BASE+'nba_prediction_results.csv?v='+Date.now(),{cache:'no-store'});
    if(!res.ok)throw Error('Results CSV unavailable (HTTP '+res.status+')');
    const rows=csv(await res.text()).filter(r=>r.player_id&&r.actual_points!==undefined&&r.pred_points!==undefined);
    if(!rows.length){root.innerHTML='<h2>Prediction Accuracy — Detailed</h2><p>No scored pregame predictions yet. The tracker will populate after completed games with saved pregame snapshots.</p>';return;}
    const options=[...new Set(rows.map(r=>r.player_name).filter(Boolean))].sort();
    root.innerHTML=`<h2>Prediction Accuracy — Detailed</h2><p>${rows.length} scored player-games · lower MAE means smaller average prediction error.</p><label>Player <select id="csa-player" style="background:#202530;color:white;padding:9px;border-radius:8px"><option value="">All players</option>${options.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('')}</select></label><div id="csa-data"></div>`;
    const selector=root.querySelector('#csa-player'),out=root.querySelector('#csa-data');
    function render(){const data=selector.value?rows.filter(r=>r.player_name===selector.value):rows;const summary=STATS.map(([key,label])=>{const valid=data.filter(r=>r['pred_'+key]!==''&&r['actual_'+key]!=='');const mae=valid.length?valid.reduce((sum,r)=>sum+Math.abs(num(r['pred_'+key])-num(r['actual_'+key])),0)/valid.length:null;return `<tr><td>${label}</td><td>${mae===null?'—':mae.toFixed(2)}</td><td>${valid.length}</td></tr>`;}).join('');const detail=data.slice().sort((a,b)=>String(b.game_date).localeCompare(String(a.game_date))).slice(0,100).map(r=>`<tr><td>${esc(r.game_date)}</td><td>${esc(r.player_name)}</td><td>${esc(r.opponent)}</td>${STATS.map(([key])=>`<td>${num(r['pred_'+key]).toFixed(1)} / ${num(r['actual_'+key]).toFixed(0)}</td>`).join('')}</tr>`).join('');out.innerHTML=`<div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse"><thead><tr><th style="text-align:left">Stat</th><th>Mean absolute error</th><th>Games</th></tr></thead><tbody>${summary}</tbody></table><h3>Predicted / Actual</h3><p>Showing up to 100 most recent player-games.</p><table style="min-width:850px;width:100%;border-collapse:collapse"><thead><tr><th>Date</th><th>Player</th><th>Opponent</th>${STATS.map(([,label])=>`<th>${label}</th>`).join('')}</tr></thead><tbody>${detail}</tbody></table></div>`;out.querySelectorAll('th,td').forEach(x=>x.style.cssText='padding:9px;border-bottom:1px solid #343844;text-align:left');}
    selector.addEventListener('change',render);render();
  }catch(err){root.innerHTML='<h2>Prediction Accuracy — Detailed</h2><p>'+esc(err.message)+'</p>';}
})();
