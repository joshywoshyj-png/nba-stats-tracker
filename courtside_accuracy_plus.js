/* Courtside rolling accuracy trends. No Recent Predictions vs Results table. */
(async function () {
  'use strict';
  const BASE = 'https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/';
  const STATS = [['points','PTS'],['rebounds','REB'],['assists','AST'],['three_pointers','3PM'],['steals','STL'],['blocks','BLK']];
  const esc = x => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function csv(text) {
    const rows=[]; let row=[],cell='',q=false;
    for(let i=0;i<text.length;i++) {const c=text[i];
      if(c==='"') {if(q&&text[i+1]==='"'){cell+='"';i++;}else q=!q;}
      else if(c===','&&!q){row.push(cell);cell='';}
      else if((c==='\n'||c==='\r')&&!q){if(c==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(x=>x!==''))rows.push(row);row=[];cell='';}
      else cell+=c;
    }
    if(cell||row.length){row.push(cell);rows.push(row);}
    const h=(rows.shift()||[]).map(x=>x.replace(/^\uFEFF/,''));
    return rows.map(r=>Object.fromEntries(h.map((x,i)=>[x,r[i]??''])));
  }
  let root=document.getElementById('cs-accuracy-plus');
  if(!root){root=document.createElement('section');root.id='cs-accuracy-plus';(document.querySelector('main')||document.body).appendChild(root);}
  root.classList.add('panel');
  root.innerHTML='<h2>Accuracy Trends Over Time</h2><p>Loading saved results...</p>';
  try {
    const r=await fetch(BASE+'nba_prediction_results.csv?v='+Date.now(),{cache:'no-store'});
    if(!r.ok)throw Error('Prediction results unavailable');
    const rows=csv(await r.text()).filter(x=>x.game_date).sort((a,b)=>a.game_date.localeCompare(b.game_date));
    if(!rows.length){root.innerHTML='<h2>Accuracy Trends Over Time</h2><p>No completed scored games yet.</p>';return;}
    root.innerHTML=`<h2>Accuracy Trends Over Time</h2><p class="small">Rolling 30 player-game MAE, compared with the season-average baseline. The last point includes the most recent scored game.</p><label for="csa-stat">Statistic</label> <select id="csa-stat">${STATS.map(([k,v])=>`<option value="${k}">${v}</option>`).join('')}</select><div style="height:290px;margin-top:14px"><canvas id="csa-trend"></canvas></div><p id="csa-summary" class="small"></p>`;
    const sel=root.querySelector('#csa-stat'),summary=root.querySelector('#csa-summary');let chart=null;
    function draw(){
      const k=sel.value;
      const data=rows.filter(x=>['pred_','baseline_','actual_'].every(prefix=>x[prefix+k]!==''&&Number.isFinite(Number(x[prefix+k]))));
      if(chart){chart.destroy();chart=null;}
      if(!data.length){summary.textContent='No valid scored results for this statistic.';return;}
      const windowSize=30;
      const points=data.map((r,i)=>{
        const window=data.slice(Math.max(0,i-windowSize+1),i+1);
        const mae=prefix=>window.reduce((sum,x)=>sum+Math.abs(Number(x[prefix+k])-Number(x['actual_'+k])),0)/window.length;
        return {date:r.game_date,model:mae('pred_'),baseline:mae('baseline_')};
      });
      const last=points[points.length-1];
      summary.textContent=`Latest rolling MAE: Courtside ${last.model.toFixed(2)} · Season average ${last.baseline.toFixed(2)} · ${Math.min(windowSize,data.length)} player-games. Early samples are preliminary.`;
      if(typeof Chart==='undefined'){return;}
      chart=new Chart(root.querySelector('#csa-trend'),{type:'line',data:{labels:points.map(p=>p.date),datasets:[{label:'Courtside MAE',data:points.map(p=>p.model),borderColor:'#ef4444',pointRadius:0,tension:.15},{label:'Season-average MAE',data:points.map(p=>p.baseline),borderColor:'#60a5fa',pointRadius:0,tension:.15}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:'#cbd5e1'}}},scales:{x:{ticks:{color:'#a5b3c8',maxTicksLimit:8}},y:{beginAtZero:true,ticks:{color:'#a5b3c8'}}}}});
    }
    sel.addEventListener('change',draw);draw();
  }catch(e){root.innerHTML='<h2>Accuracy Trends Over Time</h2><p>'+esc(e.message)+'</p>';}
})();
