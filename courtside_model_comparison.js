/* Courtside: model-version accuracy comparison. No odds or betting functionality. */
(async function () {
  'use strict';
  // Clean slate: retain old CSV records, but only show new forecasts from Oct 28, 2026 (Chicago time).
  const CS_RESET_UTC = Date.parse("2026-10-28T05:00:00Z");
  function csFresh(r) {
    const gameDate = String(r.game_date || "").slice(0, 10);
    if (gameDate && gameDate < "2026-10-28") return false;
    const saved = Date.parse(r.saved_utc || "");
    if (Number.isFinite(saved)) return saved >= CS_RESET_UTC;
    // Rows lacking a saved timestamp cannot be proven to be new.
    return false;
  }

  const root = document.getElementById('cs-model-comparison');
  if (!root) return;
  const url = 'https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/nba_prediction_results.csv?t=' + Date.now();
  const stats = [['points','PTS'],['rebounds','REB'],['assists','AST'],['three_pointers','3PM'],['steals','STL'],['blocks','BLK']];
  const escape = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function csv(text) {
    const rows=[]; let row=[], field='', quote=false;
    for(let i=0;i<text.length;i++){
      const c=text[i];
      if(c==='"') {if(quote&&text[i+1]==='"'){field+='"';i++;}else quote=!quote;}
      else if(c===','&&!quote){row.push(field);field='';}
      else if((c==='\n'||c==='\r')&&!quote){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);if(row.some(x=>x!==''))rows.push(row);row=[];field='';}
      else field+=c;
    }
    if(field||row.length){row.push(field);rows.push(row);}
    const heads=(rows.shift()||[]).map(x=>x.replace(/^\uFEFF/,''));
    return rows.map(r=>Object.fromEntries(heads.map((h,i)=>[h,r[i]??''])));
  }
  function val(x){if(x==null||String(x).trim()==='')return null;const n=Number(x);return Number.isFinite(n)?n:null;}
  function mae(rows, predicted, actual){const errors=rows.map(r=>[val(r[predicted]),val(r[actual])]).filter(([p,a])=>p!==null&&a!==null).map(([p,a])=>Math.abs(p-a));return errors.length?{value:errors.reduce((a,b)=>a+b,0)/errors.length,n:errors.length}:null;}
  function table(rows,label){
    return `<h4 style="margin:18px 0 8px">${escape(label)} <small>(${rows.length} scored player-games)</small></h4><div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse"><thead><tr><th>Stat</th><th>Courtside MAE</th><th>Season MAE</th><th>Difference</th><th>Sample</th></tr></thead><tbody>${stats.map(([key,short])=>{
      const a=mae(rows,'pred_'+key,'actual_'+key),b=mae(rows,'baseline_'+key,'actual_'+key);
      if(!a||!b)return `<tr><td>${short}</td><td colspan="4">Not enough data</td></tr>`;
      const delta=a.value-b.value;
      return `<tr><td>${short}</td><td>${a.value.toFixed(2)}</td><td>${b.value.toFixed(2)}</td><td>${delta>0?'+':''}${delta.toFixed(2)}</td><td>${Math.min(a.n,b.n)}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }
  root.innerHTML='<p>Loading model comparison…</p>';
  try{
    const response=await fetch(url,{cache:'no-store'});
    if(!response.ok)throw Error('Results file unavailable');
    const rows=csv(await response.text()).filter(csFresh);
    const versions=new Map();
    for(const r of rows){const version=(r.model_version||'legacy').trim()||'legacy';if(!versions.has(version))versions.set(version,[]);versions.get(version).push(r);}
    const blocks=[...versions.entries()].sort((a,b)=>a[0].localeCompare(b[0])).map(([name,items])=>table(items,name));
    root.innerHTML='<h3>Model Version Comparison</h3><p style="opacity:.8">Lower MAE is better. Each version is compared with the season-average prediction saved for the same player-games. Old predictions without a version are labeled legacy. This is historical tracking, not proof of future accuracy.</p>'+ (blocks.join('')||'<p>No scored results yet.</p>');
  }catch(e){root.textContent='Model comparison unavailable: '+e.message;}
})();
