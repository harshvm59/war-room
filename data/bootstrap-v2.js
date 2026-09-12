/* Published-feed refresh coordinator. No credentials or generation calls run in the browser. */
(function(root){
  'use strict';
  var FEEDS={
    prices:{label:'Market prices',file:'prices',job:'prices',hours:96},
    actions:{label:'Action signals',file:'actions',job:'prices',hours:96},
    analysis:{label:'Technical analysis',file:'analysis',job:'prices',hours:96},
    news:{label:'Daily research',file:'news',job:'news',hours:30},
    voices:{label:'Leader signals',file:'voices',job:'news',hours:30},
    themes:{label:'Theme research',file:'themes',job:'themes',hours:30},
    youtube:{label:'Videos / source items',file:'youtube',job:'news',hours:30},
    agents:{label:'Agent packets',file:'agent_ops',job:'agents',hours:30},
    framework:{label:'7-question framework',file:'framework',job:'framework',hours:192},
    portfolio:{label:'Broker holdings',file:'portfolio',job:null,hours:30}
  };
  function actionVerdict(value){return ({ADD:'add',BUY:'buy',TRIM:'trim',SELL:'trim',HOLD:'hold',WATCH:'wait',WAIT:'wait'})[String(value||'').trim().toUpperCase()]||'wait';}
  function stamp(d){return d&&(d.updated_at||(d.meta&&d.meta.broker_synced_at))||null;}
  function validate(key,d){
    if(!d||typeof d!=='object')throw new Error('Invalid published packet');
    if(key==='portfolio'){if(!Array.isArray(d.holdings)||!d.meta)throw new Error('Invalid broker packet');}
    else if(key==='prices'){if(!d.prices||typeof d.prices!=='object'||Array.isArray(d.prices))throw new Error('Invalid price packet');}
    else if(!Array.isArray(d.items))throw new Error('Invalid items packet');
    return d;
  }
  // Isolated from DOM for regression coverage of replacement, failures and concurrency.
  function createCoordinator(options){
    var state={},packets={},jobs={},jobErrors={},inflight=null,pending=new Set();
    Object.keys(FEEDS).forEach(function(key){state[key]={checkedAt:null,sourceAt:null,error:null,loaded:false};});
    async function cycle(keys){
      var jobKeys=Array.from(new Set(keys.map(function(k){return FEEDS[k].job;}).filter(Boolean)));
      options.busy(true);
      var results=await Promise.all(keys.map(async function(key){
        var st=state[key];
        try{
          var d=validate(key,await options.fetchJSON('data/'+FEEDS[key].file+'.json'));
          var changed=!!st.error||JSON.stringify(packets[key])!==JSON.stringify(d);
          packets[key]=d;st.sourceAt=stamp(d);st.loaded=true;st.error=null;
          return {key:key,data:d,changed:changed};
        }catch(e){st.error=e.message||'Fetch failed';return {key:key,error:st.error};}
        finally{st.checkedAt=options.now();}
      }).concat(jobKeys.map(async function(key){
        try{jobs[key]=await options.fetchJSON('data/refresh-status-'+key+'.json');delete jobErrors[key];}
        catch(e){jobErrors[key]='Run status unavailable';}
        return null;
      })));
      // Prices/actions/analysis render before framework so a portfolio rebuild cannot discard badges.
      var changedKeys=new Set(results.filter(function(r){return r&&r.changed;}).map(function(r){return r.key;}));
      for(var result of results.filter(Boolean)){
        if(!result.error){
          try{await options.apply(result.key,result.data,{changed:result.changed,changedKeys:changedKeys,packets:packets,state:state});}
          catch(e){state[result.key].error='Display update failed: '+(e.message||e);}
        }
      }
      options.render(state,packets,jobs,jobErrors,changedKeys);options.busy(false);
      return state;
    }
    function refresh(keys){
      (keys||Object.keys(FEEDS)).filter(function(key){return FEEDS[key];}).forEach(function(key){pending.add(key);});
      if(inflight)return inflight;
      inflight=(async function(){
        try{while(pending.size){var next=Object.keys(FEEDS).filter(function(key){return pending.has(key);});pending.clear();await cycle(next);}return state;}
        finally{inflight=null;options.busy(false);}
      })();
      return inflight;
    }
    return {refresh:refresh,state:state,packets:packets,jobs:jobs};
  }
  if(typeof module==='object'&&module.exports){module.exports={createCoordinator:createCoordinator,FEEDS:FEEDS,validate:validate,actionVerdict:actionVerdict};return;}
  if(!root.document)return;
  var document=root.document;
  function esc(v){return String(v==null?'':v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function date(value){var d=new Date(value);return value&&isFinite(d)?d.toLocaleString():'unknown';}
  function text(id,value){var el=document.getElementById(id);if(el)el.textContent=value;}
  function safeUrl(value){try{var u=new URL(value);return /^https?:$/.test(u.protocol)?u.href:'#';}catch(_){return '#';}}
  function safeCall(fn){if(typeof fn==='function')fn();}
  async function getJSON(path){
    var controller=new AbortController(),timeout=setTimeout(function(){controller.abort();},15000);
    try{var r=await fetch(path+'?t='+Date.now(),{cache:'no-store',signal:controller.signal});if(!r.ok)throw new Error('HTTP '+r.status);return await r.json();}
    finally{clearTimeout(timeout);}
  }
  function marketSessionOpen(){
    var parts=new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',weekday:'short',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date()),fields={};
    parts.forEach(function(p){fields[p.type]=p.value;});var minutes=Number(fields.hour)*60+Number(fields.minute);
    return ['Mon','Tue','Wed','Thu','Fri'].indexOf(fields.weekday)>=0&&minutes>=570&&minutes<=990;
  }
  function isStale(key,value){var time=Date.parse(value),hours=['prices','actions','analysis'].indexOf(key)>=0&&marketSessionOpen()?2:FEEDS[key].hours;return !isFinite(time)||Date.now()-time>hours*36e5;}
  function quoteDates(packet){
    var values=Object.values(packet&&packet.prices||{}),dates=values.map(function(q){return q.as_of;}).filter(Boolean).sort();
    return dates.length?'Quote as of: '+date(dates[0])+(dates.at(-1)!==dates[0]?' – '+date(dates.at(-1)):''):'Quote as-of time unavailable';
  }
  function sourceLine(key,st){return (st.error?'CHECK FAILED · '+st.error:!st.loaded?'Loading':isStale(key,st.sourceAt)?'STALE SNAPSHOT':'Published snapshot')+' · Source updated: '+date(st.sourceAt)+' · Checked: '+date(st.checkedAt);}
  function statusBlock(id,anchor){var el=document.getElementById(id);if(!el&&anchor){el=document.createElement('div');el.id=id;el.className='feed-check-status';anchor.insertAdjacentElement('beforebegin',el);}return el;}
  function renderStatus(state,packets,jobs,jobErrors,changedKeys){
    // Refresh all broker-derived strategy screens after the final action/TA
    // mutation, rather than waiting for the runtime's independent interval.
    if(changedKeys.has('actions')||changedKeys.has('analysis'))document.dispatchEvent(new CustomEvent('hvm:market-prices-updated',{detail:root.HVM_MARKET_ESTIMATE}));
    var bad=Object.keys(FEEDS).filter(function(key){var st=state[key],job=jobs[FEEDS[key].job];return st.error||(st.loaded&&isStale(key,st.sourceAt))||(job&&job.status!=='ok')||!!jobErrors[FEEDS[key].job];});
    var newestCheck=Object.values(state).map(function(st){return st.checkedAt;}).filter(Boolean).sort().pop();
    text('dashboardRefreshSummary','Checked '+date(newestCheck)+' · '+(bad.length?bad.length+' sources need attention':'All published feeds loaded'));
    document.querySelectorAll('.live-txt').forEach(function(el){el.textContent=bad.length?'Source checks · '+bad.length+' need attention':'Published feeds checked';});
    var container=document.getElementById('dashboardSources');
    if(container)container.innerHTML=Object.keys(FEEDS).map(function(key){
      var cfg=FEEDS[key],st=state[key],job=jobs[cfg.job],run=cfg.job?(job?'Cloud run: '+job.status+' · Attempt: '+date(job.last_attempt_at)+' · Last success: '+date(job.last_success_at)+(job.error?' · '+job.error.message:'')+(jobErrors[cfg.job]?' · '+jobErrors[cfg.job]:''):jobErrors[cfg.job]||'Checking cloud run status…'):'Mac-dependent broker sync · requires the local automation and broker session';
      return '<div class="refresh-source" data-state="'+(st.error?'error':isStale(key,st.sourceAt)?'stale':'ok')+'"><b>'+cfg.label+'</b><div>'+esc(sourceLine(key,st))+'<small>'+esc(run)+'</small>'+(packets[key]&&packets[key].source?'<small>Source: '+esc(packets[key].source)+'</small>':'')+(key==='prices'?'<small>'+esc(quoteDates(packets.prices))+'</small>':'')+'</div></div>';
    }).join('');
    var details=document.getElementById('dashboardSourceDetails');if(details&&bad.length&&!root.__sourceDetailsShown){details.open=true;root.__sourceDetailsShown=true;}
    text('actionTimestamp',sourceLine('actions',state.actions));
    text('liveTickerStatus',sourceLine('prices',state.prices));
    text('pivLiveStatus',(state.prices.error?'Check failed':isStale('prices',state.prices.sourceAt)?'STALE':'Published')+' · '+date(state.prices.sourceAt));
    text('pivLastUpdate',quoteDates(packets.prices)+' · Published files checked every 60s');
    var pairs=[['briefFeedStatus','briefContent','news'],['youtubeFeedStatus','ytSynthesis','youtube'],['frameworkFeedStatus','portStockPanels','framework']];
    pairs.forEach(function(row){var el=statusBlock(row[0],document.getElementById(row[1]));if(el)el.textContent=sourceLine(row[2],state[row[2]]);});
    text('themeFreshness',(isStale('themes',state.themes.sourceAt)?'STALE · ':'Published · ')+date(state.themes.sourceAt));
    var brief=document.getElementById('briefContent');if(brief&&!state.news.loaded&&state.news.error)brief.textContent='News could not be loaded. '+state.news.error+'. Refresh to retry.';
    if(root.HVMRefresh.packets.framework)applyFramework(root.HVMRefresh.packets.framework);
  }
  function busy(value){
    [['dashboardRefreshBtn','↻ Refresh dashboard'],['actionRefreshBtn','↺ Refresh Now']].forEach(function(row){var el=document.getElementById(row[0]);if(el){el.disabled=value;el.textContent=value?'↻ Checking…':row[1];}});
    document.querySelectorAll('.db-refresh,.yt-synthesize').forEach(function(el){el.disabled=value;});
  }
  function verdictColor(v){ return ({PASS:'#3ddc84',CAUTION:'#c9a84c',FAIL:'#e05252'})[v] || '#7a7672'; }
  function overallColor(o){ return ({BUY:'#3ddc84',HOLD:'#c9a84c',AVOID:'#e05252',REVIEW:'#7a7672'})[o] || '#7a7672'; }
  function frameworkBadge(item){
    var oc = overallColor(item.overall);
    var qs = item.questions || {};
    var qKeys = ['growing','moat','management','margins','cash','risk','timing'];
    var qIcons = {growing:'📈',moat:'🛡️',management:'👤',margins:'💰',cash:'💵',risk:'⚠️',timing:'⏱️'};
    var qLabels = {growing:'GROW',moat:'MOAT',management:'MGMT',margins:'MARGIN',cash:'CASH',risk:'RISK',timing:'TIME'};
    var rows = qKeys.map(function(k){
      var q = qs[k] || {};
      var v = q.verdict || 'CAUTION';
      var col = verdictColor(v);
      var sym = v==='PASS'?'✓':(v==='CAUTION'?'~':'✗');
      return '<div style="display:flex;align-items:flex-start;gap:.5rem;padding:.35rem 0;border-bottom:1px solid #20202055;"><span style="display:inline-block;min-width:22px;text-align:center;color:'+col+';font-weight:600;">'+sym+'</span><span style="font-family:DM Mono,monospace;font-size:9px;color:#7a7672;min-width:60px;">'+qIcons[k]+' '+qLabels[k]+'</span><span style="font-size:11px;color:#ede9e0;line-height:1.4;flex:1;">'+esc(q.note||'')+'</span></div>';
    }).join('');
    var sources = (Array.isArray(item.sources)?item.sources:[]).filter(function(source){try{var url=new URL(source.url);return ['https:','http:'].includes(url.protocol)&&!url.username;}catch(e){return false;}}).map(function(source){return '<a href="'+esc(source.url)+'" target="_blank" rel="noopener noreferrer">'+esc(source.title||source.reporting_period||'Source')+'</a>'+ (source.reporting_period?' · '+esc(source.reporting_period):'');}).join(' · ');
    return '<div style="margin-top:1rem;padding:1rem 1.25rem;background:'+oc+'10;border-left:4px solid '+oc+';border-radius:6px;">' +
      '<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin-bottom:.5rem;">' +
        '<span style="font-family:DM Mono,monospace;font-size:9px;color:#7a7672;letter-spacing:.1em;">📋 TOM 7-Q QUALITY FRAMEWORK</span>' +
        '<span style="font-family:Bebas Neue,sans-serif;font-size:1.3rem;letter-spacing:.06em;color:'+oc+';">' + esc(item.overall||'REVIEW') + ' · ' + esc(item.score||0) + '/7</span>' +
      '</div>' +
      rows +
      (sources ? '<div class="feed-check-status">Research sources: '+sources+'</div>' : '') +
      (item.summary ? '<div style="font-size:11px;color:#c9a84c;margin-top:.6rem;font-style:italic;padding-top:.5rem;border-top:1px solid '+oc+'33;">💡 ' + esc(item.summary) + '</div>' : '') +
    '</div>';
  }

  function applyFramework(packet){
    document.querySelectorAll('[data-framework-badge]').forEach(function(el){el.remove();});
    var byTicker={};packet.items.forEach(function(item){byTicker[item.ticker]=item;});
    document.querySelectorAll('[id^="psp-"]').forEach(function(panel){
      var first=panel.querySelector('span');if(!first)return;
      var fw=byTicker[first.textContent.trim()];if(!fw)return;
      var div=document.createElement('div');div.dataset.frameworkBadge='1';
      var stale=isStale('framework',packet.updated_at);
      var quality=packet.fundamentals_verified===false?' · Fundamentals unverified; model assessment only':'';
      div.innerHTML='<div class="feed-check-status">'+(stale?'ARCHIVED / STALE FRAMEWORK · ':'Framework source updated · ')+esc(date(packet.updated_at))+(stale?' · Not a current decision signal':'')+esc(quality)+'</div>'+frameworkBadge(fw);
      panel.appendChild(div);
    });
  }
  function applyThemesPacket(t){
    if(!t || !Array.isArray(t.items)) return;
    var count=document.getElementById('themePacketCount'),freshness=document.getElementById('themeFreshness');
    var updated=t.updated_at?new Date(t.updated_at):null,ageHours=updated?(Date.now()-updated.getTime())/36e5:Infinity;
    if(count) count.textContent=t.items.length+' themes live';
    if(freshness){
      freshness.textContent=updated?(ageHours<=12?'LIVE · ':'STALE · ')+updated.toLocaleString():'Waiting for theme packet';
      freshness.className='tag '+(ageHours<=12?'tg':'tr');
    }
    // Research content is updated from data/themes.json; the live allocation is
    // separately derived from INDmoney PORT data in the runtime renderer.
    try { window.THEMES_LIVE = t.items; window.THEMES_UPDATED_AT=t.updated_at||''; } catch(_) {}
    safeCall(function(){
      if (typeof THEMES === 'undefined') return;
      THEMES.forEach(function(local){local.liveTickers=[];local.stocks=[];local.srcs=[];local.body='No research in the current published packet.';});
      t.items.forEach(function(live){
        var key=String(live.dashboard_name||live.theme||'').toUpperCase();
        var local=THEMES.find(function(x){ return String(x.name||'').toUpperCase()===key; });
        if (!local) return;
        if (live.summary) local.body=live.summary;
        local.priority=live.priority||local.priority;
        local.targetPct=Number(live.target_pct||0);
        local.liveUpdatedAt=live.cohort_updated_at||t.updated_at;
        local.consensus=(live.research_mode||'DAILY RESEARCH')+' · ACTIVITY '+(live.rating||'UPDATED')+' · '+new Date(t.updated_at).toLocaleDateString();
        if (Array.isArray(live.tickers)) {
          local.liveTickers=live.tickers;
          local.stocks=live.tickers.slice(0,8).map(function(row){
            if(typeof row==='string') return {s:row,c:'watch',status:'WATCH'};
            var status=String(row.status||'WATCH').toUpperCase(), cls='watch';
            if(status==='ADD') cls='add';
            else if(status==='NEW BUY') cls='new-buy';
            else if(status==='OWN'||status==='HOLD') cls='own';
            else if(status==='TRIM') cls='trim';
            return {s:row.ticker,c:cls,status:status,price:row.price,reason:row.reason};
          });
          var researchKey=local.name;
          if(typeof THEME_RESEARCH!=='undefined' && THEME_RESEARCH[researchKey]){
            THEME_RESEARCH[researchKey].top5=live.tickers.slice(0,5).map(function(row){
              var status=String(row.status||'WATCH').toUpperCase(),price=Number(row.price);
              return {t:row.ticker,n:row.name||row.ticker,thesis:(row.reason||'Daily source-linked theme candidate')+' · Research status: '+status+'.',entry:isFinite(price)&&price>0?'Reference price $'+price.toFixed(2):'Reference price pending',target:'Re-score on next theme refresh',horizon:'Daily monitored cohort',sizing:row.owned?'Existing holding · CEO review':status==='NEW BUY'?'New-position candidate · CEO sizing required':'Watchlist · no allocation by default',risk:'Source and risk gates must pass before any CEO decision'};
            });
          }
        }
        local.srcs=Array.isArray(live.news)?live.news.map(function(item){return {org:item.source||'Daily research feed',title:item.title||'Market update',stat:item.date||'',u:item.url||'#'};}) : [];
      });
      if (typeof buildThemes === 'function') buildThemes();
      if (typeof buildCohortAllocator === 'function') buildCohortAllocator();
    });
  }
  function applyAnalysis(x,a){
    Object.keys(TA).forEach(function(key){delete TA[key];});
        var actionByTicker={};
        if (a && Array.isArray(a.items)) a.items.forEach(function(item){ actionByTicker[item.ticker]=item; });
        x.items.forEach(function(row){
          if (!row || !row.ticker || !row.ta || !row.holding || typeof TA==='undefined') return;
          var q=row.ta, h=row.holding, old=TA[row.ticker] || (TA[row.ticker]={});
          var price=Number(h.current_price || 0), rsi=Number(q.rsi14 || 50), ret=Number(q.ret_1d || 0);
          old.price=price.toFixed(2);
          old.chg=(ret>=0?'+':'')+ret.toFixed(2)+'% today';
          old.rsi=rsi; old.rsiLabel=rsi>=70?'Overbought':rsi<=30?'Oversold':'Neutral';
          old.macdVal=Number(q.macd || 0); old.macdSig='Signal '+Number(q.macd_signal || 0).toFixed(2);
          old.ma=[q.sma20?'SMA20 $'+Number(q.sma20).toFixed(0):'',q.sma50?'SMA50 $'+Number(q.sma50).toFixed(0):'',q.sma200?'SMA200 $'+Number(q.sma200).toFixed(0):''].filter(Boolean);
          old.support=[q.sma20?'$'+Number(q.sma20).toFixed(0):'',q.sma50?'$'+Number(q.sma50).toFixed(0):''].filter(Boolean);
          old.resist=[price?'$'+(price*1.05).toFixed(0):'',price?'$'+(price*1.10).toFixed(0):''].filter(Boolean);
          old.vol=(q.vol_ratio_20d?'Vol '+Number(q.vol_ratio_20d).toFixed(2)+'x 20D avg':'Volume n/a');
          old.pattern='Daily rule-based technical scan';
          old.patternColor=rsi>=70?'#e05252':rsi<=30?'#4a9eff':'#3ddc84';
          old.ta='Yahoo daily data: RSI '+rsi.toFixed(1)+', MACD '+Number(q.macd || 0).toFixed(2)+', '+(q.vs_sma50_pct>=0?'+':'')+Number(q.vs_sma50_pct || 0).toFixed(1)+'% vs SMA50.';
          var livePos=PORT.find(function(z){return z.t===row.ticker;});
          var liveReturn=livePos&&livePos.buy?((hvmMarkPrice(livePos)/livePos.buy-1)*100):Number(h.pnl_pct||0);
          old.fund='Live broker position: '+Number(livePos?livePos.units:h.units||0).toFixed(2)+' units · $'+Number(livePos?hvmBrokerValue(livePos):h.current_value||0).toLocaleString('en-US',{maximumFractionDigits:0})+' broker value · '+(liveReturn>=0?'+':'')+liveReturn.toFixed(1)+'% market return.';
          old.action='No current action signal. Retain cash / no action.';
          old.verdict='wait';
          var action=actionByTicker[row.ticker];
          if (action) {
            old.action=action.action_text || action.signal || old.action;
            old.verdict=actionVerdict(action.action);
            var pos=PORT.find(function(z){return z.t===row.ticker;});
            if (pos) {
              var verb=String(action.action||'').toLowerCase();
              pos.action=verb==='add'?'add':verb==='trim'?'trim':verb==='watch'?'watch':'hold';
            }
            if (pos && pos.dca) {
              var targetMatch=String(action.target||'').match(/\$([0-9,.]+)/);
              var stopMatch=String(action.stop||'').match(/\$([0-9,.]+)/);
              var target=targetMatch?Number(targetMatch[1].replace(/,/g,'')):0;
              var stop=stopMatch?Number(stopMatch[1].replace(/,/g,'')):0;
              if (target) pos.dca.aT=target;
              if (stop) pos.dca.bear=stop;
              if (target) pos.dca.bull=Math.round(target*1.15);
              pos.dca.note='Daily rule-based plan: '+(action.action_text || action.signal || 'Review latest technical signal.');
            }
          }
        });

    if(typeof buildPortTabs==='function')buildPortTabs();
    if(typeof buildPortPanels==='function')buildPortPanels();
    if(typeof buildPivot==='function')buildPivot(true);
  }
  function applyPrices(d){
    var previous=root.LIVE_PRICES||{};root.LIVE_PRICES={};
    Object.keys(d.prices).forEach(function(sym){var q=d.prices[sym];if(!q||q.price==null)return;root.LIVE_PRICES[sym]=Object.assign({},q,{prevTickPrice:previous[sym]&&previous[sym].price});if(!PRICE_HISTORY[sym])PRICE_HISTORY[sym]=[];PRICE_HISTORY[sym].push(q.price);if(PRICE_HISTORY[sym].length>30)PRICE_HISTORY[sym].shift();});
    root.LIVE_FETCH_OK=Object.keys(root.LIVE_PRICES).length>0;
    PORT.forEach(function(p){if(!root.LIVE_PRICES[p.t]){delete p.marketCur;delete p.marketVal;}});
    updatePortfolioWithLivePrices();updateTickerBar();buildPivot(true);
  }
  function applyNews(d){
    root.NEWS_LIVE=d.items;
    var brief=document.getElementById('briefContent');if(!brief)return;
    brief.innerHTML=d.items.length?d.items.slice(0,12).map(function(item){return '<div style="margin:0 0 .7rem;padding:0 0 .7rem;border-bottom:1px solid #202020"><a href="'+esc(safeUrl(item.url))+'" target="_blank" rel="noopener" style="color:var(--gold);font-weight:600;font-size:12px">'+esc(item.ticker||'MARKET')+' · '+esc(item.headline||'Update')+'</a><div style="margin-top:.25rem;font-size:11px;line-height:1.6">'+esc(item.summary||'')+'</div></div>';}).join(''):'No qualifying news in the latest published packet. No historical brief is substituted.';
  }
  async function checkPortfolio(d){
    var shown=document.querySelector('.im-meta b'),expected=d.meta.broker_synced_at_ist;
    if(!shown||!expected||shown.textContent.trim()===expected.trim())return;
    // The generated runtime contains broker cash and other-asset constants. Reload
    // the whole newly published document, never mix new units with old constants.
    var key='hvm-broker-document-reload',version=d.meta.broker_synced_at;
    try{if(sessionStorage.getItem(key)===version)throw new Error('Broker publication pending: reload document to retry');}catch(e){if(e.message.indexOf('publication pending')>=0)throw e;}
    var controller=new AbortController(),timeout=setTimeout(function(){controller.abort();},15000),latest;
    try{
      var response=await fetch('index.html?t='+Date.now(),{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw new Error('Broker document HTTP '+response.status);
      latest=new DOMParser().parseFromString(await response.text(),'text/html');
    }finally{clearTimeout(timeout);}
    var latestStamp=latest.querySelector('.im-meta b');
    if(!latestStamp||latestStamp.textContent.trim()!==expected.trim())throw new Error('Broker document publication pending; will retry next check');
    try{sessionStorage.setItem(key,version);var section=document.querySelector('.section.active');if(section)sessionStorage.setItem('hvm-refresh-section',section.id);}catch(_){}
    var url=new URL(root.location.href);url.searchParams.set('broker_snapshot',version);root.location.replace(url.href);
  }
  async function apply(key,d,ctx){
    if(key==='portfolio'){await checkPortfolio(d);return;}
    if(!ctx.changed&&!(key==='analysis'&&ctx.changedKeys.has('actions')))return;
    if(key==='prices')applyPrices(d);
    else if(key==='actions'){
      root.TODAY_ACTIONS_MAY5=d.items;root.ACTIONS_UPDATED_AT=d.updated_at||null;
      var actionMap={};d.items.forEach(function(a){actionMap[a.ticker]=a;});
      PORT.forEach(function(p){var action=actionMap[p.t],verb=String(action&&action.action||'').toLowerCase();p.action=verb==='add'?'add':verb==='trim'?'trim':verb==='hold'?'hold':'watch';if(p.dca)p.dca.note=action?'Published rule-based plan: '+(action.action_text||action.signal||'Review latest signal.'):'No current action signal. Monthly DCA is a configured assumption; retain cash / no action.';});
      renderActions(d.items);
    }
    else if(key==='analysis')applyAnalysis(d,ctx.packets.actions);
    else if(key==='news')applyNews(d);
    else if(key==='voices'){root.VOICES=d.items;root.VOICES_UPDATED_AT=d.updated_at||'';root.VOICES_MONITORED=d.monitored_leaders||30;root.VOICES_SOURCE=d.source||'';buildLeaders();}
    else if(key==='themes')applyThemesPacket(d);
    else if(key==='youtube'){root.YTVIDEOS=d.items;root.YOUTUBE_UPDATED_AT=d.updated_at||'';buildYTFilters();buildYT();generateYTSynthesis(false);text('ytVideoCount',d.items.length+' published source items');}
    else if(key==='agents'){root.AGENT_OPS_LIVE=d;buildCEOGame();}
    else if(key==='framework')applyFramework(d);
  }
  root.HVMRefresh=createCoordinator({fetchJSON:getJSON,apply:apply,render:renderStatus,busy:busy,now:function(){return new Date().toISOString();}});
  root.HVMRefresh.refreshForSection=function(id){
    var groups={portfolio:['prices','actions','analysis','framework','portfolio'],pivot:['prices','actions','analysis','portfolio'],youtube:['youtube','news'],leaders:['voices'],themes:['themes'],agents:['agents'],roadmap:['portfolio']};
    if(groups[id])return root.HVMRefresh.refresh(groups[id]);
  };
  var button=document.getElementById('dashboardRefreshBtn');if(button)button.addEventListener('click',function(){root.HVMRefresh.refresh();});
  // Existing render calls can rebuild stock panels after market updates. The
  // published framework always replaces badges on the resulting current panels.
  var buildPanels=root.buildPortPanels;
  root.buildPortPanels=function(){if(buildPanels)buildPanels.apply(this,arguments);var packet=root.HVMRefresh.packets.framework;if(packet)applyFramework(packet);};
  root.addEventListener('focus',function(){root.HVMRefresh.refresh();});
  document.addEventListener('visibilitychange',function(){if(document.visibilityState==='visible')root.HVMRefresh.refresh();});
  setInterval(function(){if(document.visibilityState!=='hidden')root.HVMRefresh.refresh();},60000);
  try{var sectionId=sessionStorage.getItem('hvm-refresh-section');if(sectionId){sessionStorage.removeItem('hvm-refresh-section');var navItem=Array.from(document.querySelectorAll('.nav-item')).find(function(el){return (el.getAttribute('onclick')||'').indexOf("'"+sectionId+"'")>=0;});if(navItem)nav(sectionId,navItem);}}catch(_){}
  root.HVMRefresh.refresh();
})(typeof window==='undefined'?globalThis:window);
