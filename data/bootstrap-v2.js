// HVM War Room - bootstrap v2: rebuilds action cards + timestamp from data/actions.json + 7Q framework badges
(function(){
  function bust(u){ return u + '?t=' + Date.now(); }
  function getJSON(p){ return fetch(bust(p), {cache:'no-store'}).then(function(r){return r.ok?r.json():null;}).catch(function(){return null;}); }
  function colorByUrgency(u){ return ({critical:'#e05252',high:'#c9a84c',medium:'#4a9eff',low:'#2dd4bf'})[u] || '#c9a84c'; }
  function actionPillColor(a){ a=(a||'').toUpperCase(); if(a.indexOf('ADD')>=0)return '#3ddc84'; if(a.indexOf('TRIM')>=0||a.indexOf('SELL')>=0)return '#e05252'; if(a.indexOf('WATCH')>=0)return '#b388ff'; return '#c9a84c'; }
  function esc(s){ return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function card(it){
    var c = it.color || colorByUrgency(it.urgency);
    var ap = actionPillColor(it.action);
    var line = '';
    if (it.entry || it.stop || it.target) line = '<div style="font-family:DM Mono,monospace;font-size:10px;color:#7a7672;margin-top:.5rem;">' + (it.entry?'<span style="color:#3ddc84;">📍 Entry: '+esc(it.entry)+'</span>  ':'') + (it.stop?'<span style="color:#e05252;">| Stop: '+esc(it.stop)+'</span>  ':'') + (it.target?'<span style="color:#c9a84c;">| Target: '+esc(it.target)+'</span>':'') + '</div>';
    var siz = it.sizing ? '<div style="font-family:DM Mono,monospace;font-size:10px;color:#7a7672;margin-top:.25rem;">📏 '+esc(it.sizing)+'</div>' : '';
    return '<div style="background:'+c+'15;border:1px solid '+c+'44;border-left:4px solid '+c+';border-radius:6px;padding:1rem 1.25rem;margin-bottom:.75rem;"><div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:.5rem;"><div style="display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;"><span style="font-family:Bebas Neue,sans-serif;font-size:1.6rem;letter-spacing:.06em;color:'+c+';">'+esc(it.ticker)+'</span><span style="font-family:DM Mono,monospace;font-size:9px;color:#7a7672;">'+esc(it.price)+'</span><span style="font-family:DM Mono,monospace;font-size:9px;padding:2px 8px;border-radius:2px;background:'+c+'22;color:'+c+';border:1px solid '+c+'44;">'+esc(it.urgency)+'</span></div><span style="font-family:Bebas Neue,sans-serif;font-size:.95rem;letter-spacing:.08em;color:'+ap+';background:'+ap+'15;padding:4px 12px;border-radius:3px;">'+esc(it.action)+'</span></div><div style="font-size:12px;color:#ede9e0;line-height:1.55;">'+esc(it.signal)+'</div>'+line+siz+(it.action_text?'<div style="font-family:DM Mono,monospace;font-size:10px;color:'+ap+';margin-top:.5rem;letter-spacing:.05em;">→ '+esc(it.action_text)+'</div>':'')+'</div>';
  }
  function applyActions(items, meta){
    var grid = document.getElementById('actionItemsGrid');
    if (grid && items.length) grid.innerHTML = items.map(card).join('');
    var ts = document.getElementById('actionTimestamp');
    if (ts) {
      var dt = meta && meta.updated_at ? new Date(meta.updated_at) : new Date();
      var snap = meta && meta.portfolio_snapshot ? ' · Portfolio $'+(meta.portfolio_snapshot.total_value||0).toLocaleString()+' ('+(meta.portfolio_snapshot.pnl_pct>=0?'+':'')+(meta.portfolio_snapshot.pnl_pct||0).toFixed(1)+'%)' : '';
      ts.textContent = 'Updated: '+dt.toLocaleTimeString()+' · '+dt.toDateString()+' · '+items.length+' live signals · auto-refresh 60s'+snap;
    }
    document.querySelectorAll('.live-txt').forEach(function(el){ el.textContent = 'Live · '+new Date().toDateString(); });
  }

  // 7Q framework — render compact badge per stock in My Portfolio section
  function verdictColor(v){ return ({PASS:'#3ddc84',CAUTION:'#c9a84c',FAIL:'#e05252'})[v] || '#7a7672'; }
  function overallColor(o){ return ({BUY:'#3ddc84',HOLD:'#c9a84c',AVOID:'#e05252'})[o] || '#7a7672'; }
  function frameworkBadge(item){
    var oc = item.overall_color || overallColor(item.overall);
    var qs = item.questions || {};
    var qKeys = ['growing','moat','management','margins','cash','risk','timing'];
    var qIcons = {growing:'📈',moat:'🛡️',management:'👤',margins:'💰',cash:'💵',risk:'⚠️',timing:'⏱️'};
    var dots = qKeys.map(function(k){
      var q = qs[k] || {};
      var v = q.verdict || 'FAIL';
      var col = verdictColor(v);
      var sym = v==='PASS'?'✓':(v==='CAUTION'?'~':'✗');
      return '<span title="'+qIcons[k]+' '+k+': '+v+' — '+esc(q.note||'')+'" style="display:inline-block;width:14px;height:14px;border-radius:50%;background:'+col+';color:#080808;font-size:9px;text-align:center;line-height:14px;margin-right:2px;font-weight:600;">'+sym+'</span>';
    }).join('');
    return '<div style="margin-top:.5rem;padding:.5rem .75rem;background:'+oc+'12;border-left:3px solid '+oc+';border-radius:4px;">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;">' +
        '<span style="font-family:DM Mono,monospace;font-size:9px;color:#7a7672;letter-spacing:.08em;">TOM 7Q FRAMEWORK</span>' +
        '<span style="font-family:Bebas Neue,sans-serif;font-size:.95rem;letter-spacing:.08em;color:'+oc+';">' + (item.overall||'?') + ' · ' + (item.score||0) + '/7</span>' +
      '</div>' +
      '<div style="margin-top:.4rem;font-size:11px;color:#ede9e0;">' + dots + '</div>' +
      (item.summary ? '<div style="font-size:11px;color:#7a7672;margin-top:.35rem;font-style:italic;">' + esc(item.summary) + '</div>' : '') +
    '</div>';
  }

  function applyFramework(items){
    if (!items || !items.length) return;
    // Index by ticker for fast lookup
    var byTicker = {};
    items.forEach(function(i){ if (i.ticker) byTicker[i.ticker] = i; });
    // Find all .tkr elements in portfolio section + inject badge after their container row
    var portfolio = document.getElementById('portfolio');
    if (!portfolio) return;
    var rows = portfolio.querySelectorAll('tr');
    rows.forEach(function(tr){
      var tkEl = tr.querySelector('.tkr');
      if (!tkEl) return;
      var t = tkEl.textContent.trim();
      var fw = byTicker[t];
      if (!fw) return;
      // Avoid duplicate insertion
      if (tr.dataset.fwInjected === '1') return;
      tr.dataset.fwInjected = '1';
      // Build badge row below this row
      var newTr = document.createElement('tr');
      var td = document.createElement('td');
      td.colSpan = tr.cells.length;
      td.style.padding = '0 14px 0 14px';
      td.style.borderBottom = '1px solid var(--border)';
      td.innerHTML = frameworkBadge(fw);
      newTr.appendChild(td);
      tr.parentNode.insertBefore(newTr, tr.nextSibling);
    });
  }

  function loadAll(){
    getJSON('data/actions.json').then(function(a){
      if (a && Array.isArray(a.items) && a.items.length) applyActions(a.items, a);
    });
    getJSON('data/framework.json').then(function(f){
      if (f && Array.isArray(f.items) && f.items.length) applyFramework(f.items);
    });
  }

  loadAll();
  setInterval(loadAll, 60000);
})();
