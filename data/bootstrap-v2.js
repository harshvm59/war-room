// HVM War Room - bootstrap v2: actions cards + timestamp + 7Q framework badges
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

  function verdictColor(v){ return ({PASS:'#3ddc84',CAUTION:'#c9a84c',FAIL:'#e05252'})[v] || '#7a7672'; }
  function overallColor(o){ return ({BUY:'#3ddc84',HOLD:'#c9a84c',AVOID:'#e05252'})[o] || '#7a7672'; }
  function frameworkBadge(item){
    var oc = item.overall_color || overallColor(item.overall);
    var qs = item.questions || {};
    var qKeys = ['growing','moat','management','margins','cash','risk','timing'];
    var qIcons = {growing:'📈',moat:'🛡️',management:'👤',margins:'💰',cash:'💵',risk:'⚠️',timing:'⏱️'};
    var qLabels = {growing:'GROW',moat:'MOAT',management:'MGMT',margins:'MARGIN',cash:'CASH',risk:'RISK',timing:'TIME'};
    var rows = qKeys.map(function(k){
      var q = qs[k] || {};
      var v = q.verdict || 'FAIL';
      var col = verdictColor(v);
      var sym = v==='PASS'?'✓':(v==='CAUTION'?'~':'✗');
      return '<div style="display:flex;align-items:flex-start;gap:.5rem;padding:.35rem 0;border-bottom:1px solid #20202055;"><span style="display:inline-block;min-width:22px;text-align:center;color:'+col+';font-weight:600;">'+sym+'</span><span style="font-family:DM Mono,monospace;font-size:9px;color:#7a7672;min-width:60px;">'+qIcons[k]+' '+qLabels[k]+'</span><span style="font-size:11px;color:#ede9e0;line-height:1.4;flex:1;">'+esc(q.note||'')+'</span></div>';
    }).join('');
    return '<div style="margin-top:1rem;padding:1rem 1.25rem;background:'+oc+'10;border-left:4px solid '+oc+';border-radius:6px;">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:.5rem;">' +
        '<span style="font-family:DM Mono,monospace;font-size:9px;color:#7a7672;letter-spacing:.1em;">📋 TOM 7-Q QUALITY FRAMEWORK</span>' +
        '<span style="font-family:Bebas Neue,sans-serif;font-size:1.3rem;letter-spacing:.06em;color:'+oc+';">' + (item.overall||'?') + ' · ' + (item.score||0) + '/7</span>' +
      '</div>' +
      rows +
      (item.summary ? '<div style="font-size:11px;color:#c9a84c;margin-top:.6rem;font-style:italic;padding-top:.5rem;border-top:1px solid '+oc+'33;">💡 ' + esc(item.summary) + '</div>' : '') +
    '</div>';
  }

  function applyFramework(items){
    if (!items || !items.length) return;
    var byTicker = {};
    items.forEach(function(i){ if (i.ticker) byTicker[i.ticker] = i; });
    var panels = document.querySelectorAll('[id^="psp-"]');
    panels.forEach(function(panel){
      var firstSpan = panel.querySelector('span');
      if (!firstSpan) return;
      var t = firstSpan.textContent.trim();
      var fw = byTicker[t];
      if (!fw) return;
      if (panel.dataset.fwInjected === '1') return;
      panel.dataset.fwInjected = '1';
      var div = document.createElement('div');
      div.innerHTML = frameworkBadge(fw);
      panel.appendChild(div);
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
