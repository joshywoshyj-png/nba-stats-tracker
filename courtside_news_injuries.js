/* Courtside ESPN news and injury ticker. Loads GitHub-generated CSVs. */
(async function () {
  const BASE = 'https://raw.githubusercontent.com/joshywoshyj-png/nba-stats-tracker/main/';
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function csv(s) { const rows=[];let row=[],v='',q=false;for(let i=0;i<s.length;i++){let c=s[i];if(c==='"'){if(q&&s[i+1]==='"'){v+='"';i++}else q=!q;}else if(c===','&&!q){row.push(v);v='';}else if((c==='\n'||c==='\r')&&!q){if(c==='\r'&&s[i+1]==='\n')i++;row.push(v);if(row.some(x=>x))rows.push(row);row=[];v='';}else v+=c;}if(row.length||v){row.push(v);rows.push(row);}let head=rows.shift()||[];return rows.map(r=>Object.fromEntries(head.map((h,i)=>[h,r[i]||''])));}
  async function load(name) {const r=await fetch(BASE+name+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(name+' HTTP '+r.status);return csv(await r.text());}
  const style=document.createElement('style');style.textContent=`#cs-news{background:#16191f;color:#f7f7fa;border:1px solid #363b46;border-radius:16px;padding:16px;margin:18px auto;max-width:1200px;font:14px system-ui,sans-serif}#cs-news h2{font-size:22px;margin:0 0 10px}#cs-news .muted{color:#b9bdc7;font-size:12px}#cs-news .lane{overflow:hidden;white-space:nowrap;border-top:1px solid #303540;padding:12px 0}#cs-news .track{display:inline-block;animation:cs-move 48s linear infinite}#cs-news .lane:hover .track{animation-play-state:paused}#cs-news a{color:#fff;text-decoration:none;margin-right:48px}#cs-news .inj{color:#ffb0b0;margin-right:40px}@keyframes cs-move{from{transform:translateX(20%)}to{transform:translateX(-100%)}}@media(prefers-reduced-motion:reduce){#cs-news .track{animation:none;white-space:normal}}`;
  document.head.appendChild(style);
  const root=document.createElement('section');root.id='cs-news';root.innerHTML='<h2>NBA News & Injury Updates</h2><p class="muted">Loading ESPN reports saved by GitHub Actions…</p>';
  const anchor=document.querySelector('main')||document.body;anchor.prepend(root);
  const [news,injuries]=await Promise.allSettled([load('nba_news.csv'),load('nba_injuries.csv')]);
  const stories=news.status==='fulfilled'?news.value:[];
  const reports=injuries.status==='fulfilled'?injuries.value:[];
  const validUrl=s=>{try{let u=new URL(s);return u.protocol==='https:'&&(/(^|\.)espn\.com$/).test(u.hostname)?u.href:''}catch{return ''}};
  const headlines=stories.slice(0,18).map(x=>{const url=validUrl(x.url);return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(x.headline)}</a>`:`<span>${esc(x.headline)}</span>`}).join('');
  const injuriesText=reports.slice(0,35).map(x=>`<span class="inj">${esc(x.team)} · ${esc(x.player_name)} — ${esc(x.status||'Status not specified')}</span>`).join('');
  const last=stories[0]?.last_updated_utc||reports[0]?.last_updated_utc||'';
  root.innerHTML=`<h2>NBA News & Injury Updates</h2><div class="muted">ESPN-sourced reports · Last data refresh: ${esc(last||'Unknown')} · Scroll pauses on hover</div><div class="lane"><div class="track">${headlines||'News feed unavailable. Check GitHub Actions and nba_news.csv.'}</div></div><div class="lane"><div class="track">${injuriesText||'No injury reports available. This does not mean every player is healthy.'}</div></div>`;
  window.CourtsideInjuries=reports;
  window.dispatchEvent(new Event('courtside-injuries-ready'));
})();
