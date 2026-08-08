/* HVM cohort allocator — research planning only; never sends a broker order. */
(function(){
  var KEY='hvm_cohort_allocator_v1';
  var DEFAULTS={
    budget:20000,
    mode:'gap',
    selected:['Energy & Nuclear Power','Defense & National Security','Agentic AI & Enterprise SaaS']
  };

  function esc(value){return String(value==null?'':value).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
  function money(value,decimals){return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',minimumFractionDigits:decimals||0,maximumFractionDigits:decimals||0}).format(Number(value)||0);}
  function load(){
    try{
      var saved=JSON.parse(localStorage.getItem(KEY)||'{}');
      return {budget:Math.max(100,Number(saved.budget)||DEFAULTS.budget),mode:['gap','p0','equal'].indexOf(saved.mode)>=0?saved.mode:DEFAULTS.mode,selected:Array.isArray(saved.selected)&&saved.selected.length?saved.selected:DEFAULTS.selected.slice()};
    }catch(_){return {budget:DEFAULTS.budget,mode:DEFAULTS.mode,selected:DEFAULTS.selected.slice()};}
  }
  function save(state){try{localStorage.setItem(KEY,JSON.stringify(state));}catch(_){}}
  function priorityWeight(priority){return ({P0:4,P1:2.5,P2:1.5,P3:.8})[priority]||1;}
  function statusWeight(status){return ({ADD:6,'NEW BUY':5,OWN:3,HOLD:2.5,WATCH:1,TRIM:0})[String(status||'').toUpperCase()]||1;}
  function actionClass(status){status=String(status||'').toLowerCase();return status==='new buy'?'new-buy':status==='watch'?'watch':status==='trim'?'trim':'';}
  function portfolioRows(){
    /* PORT is declared with top-level `const` in index.html, so browsers do not
       expose it as window.PORT.  Read the lexical binding first and retain the
       window fallback for the unit-test harness and future module migrations. */
    try{if(typeof PORT!=='undefined'&&Array.isArray(PORT))return PORT;}catch(_){}
    return Array.isArray(window.PORT)?window.PORT:[];
  }
  function portfolioMap(){var map={};portfolioRows().forEach(function(row){map[row.t]=row;});return map;}
  function totalPortfolio(){return portfolioRows().reduce(function(sum,row){return sum+Number(row.val||0);},0);}
  function themes(){return Array.isArray(window.THEMES_LIVE)?window.THEMES_LIVE:[];}
  function currentExposure(theme,port){
    var seen={},total=0;
    (theme.tickers||[]).forEach(function(row){
      var ticker=typeof row==='string'?row:row.ticker;if(!ticker||seen[ticker])return;seen[ticker]=1;
      var holding=port[ticker];
      if(holding)total+=Number(holding.val||row.current_value||0);
    });
    return total;
  }
  function allocate(total,rows,scoreFn){
    if(!rows.length)return [];
    total=Math.max(0,Math.round(Number(total)||0));
    var scores=rows.map(function(row){return Math.max(.0001,Number(scoreFn(row))||0);});
    var denominator=scores.reduce(function(a,b){return a+b;},0);
    var parts=rows.map(function(row,index){
      var exact=total*scores[index]/denominator,amount=Math.floor(exact);
      return {item:row,amount:amount,remainder:exact-amount,index:index};
    });
    var left=total-parts.reduce(function(sum,row){return sum+row.amount;},0);
    parts.slice().sort(function(a,b){return b.remainder-a.remainder||a.index-b.index;}).slice(0,left).forEach(function(row){row.amount+=1;});
    return parts.map(function(row){return {item:row.item,amount:row.amount};});
  }
  function selectStocks(theme){
    var rows=(theme.tickers||[]).filter(function(row){return String(row.status||'WATCH').toUpperCase()!=='TRIM';}).slice();
    rows.sort(function(a,b){return statusWeight(b.status)-statusWeight(a.status)||(Number(b.source_hits)||0)-(Number(a.source_hits)||0);});
    var chosen=rows.slice(0,3),fresh=rows.find(function(row){return !row.owned&&(row.status==='NEW BUY'||row.status==='WATCH');});
    if(fresh&&!chosen.some(function(row){return row.ticker===fresh.ticker;})){
      if(chosen.length>=3)chosen[chosen.length-1]=fresh;else chosen.push(fresh);
    }
    return chosen;
  }
  function buildPlan(state,docs){
    var port=portfolioMap(),portfolioTotal=totalPortfolio(),selected=docs.filter(function(theme){return state.selected.indexOf(theme.theme)>=0;});
    selected.forEach(function(theme){
      theme._current=currentExposure(theme,port);
      theme._target=(portfolioTotal+state.budget)*(Number(theme.target_pct||0)/100);
      theme._gap=Math.max(0,theme._target-theme._current);
    });
    var cohortAlloc=allocate(state.budget,selected,function(theme){
      if(state.mode==='equal')return 1;
      if(state.mode==='p0')return priorityWeight(theme.priority)*(theme._gap>0?2:.5);
      return Math.max(theme._gap,portfolioTotal*.01)*Math.sqrt(priorityWeight(theme.priority));
    });
    var plan=[];
    cohortAlloc.forEach(function(cohort){
      var picks=selectStocks(cohort.item);
      allocate(cohort.amount,picks,function(row){return statusWeight(row.status);}).forEach(function(part){
        plan.push({theme:cohort.item,stock:part.item,amount:part.amount,cohortAmount:cohort.amount});
      });
    });
    return {portfolioTotal:portfolioTotal,cohorts:cohortAlloc,rows:plan};
  }
  function ensureHost(){
    var section=document.getElementById('deploy');if(!section)return null;
    var host=document.getElementById('cohortAllocator');
    if(!host){host=document.createElement('div');host.id='cohortAllocator';host.className='cohort-planner';var table=section.querySelector('.tw');if(table)section.insertBefore(host,table);else section.appendChild(host);}
    return host;
  }
  function modeLabel(mode){return mode==='p0'?'P0-FIRST':mode==='equal'?'EQUAL COHORTS':'TARGET-GAP WEIGHTED';}

  window.buildCohortAllocator=function(){
    var host=ensureHost();if(!host)return;
    var docs=themes(),state=load();
    if(!docs.length){host.innerHTML='<div class="cohort-planner-head"><div><div class="cohort-kicker">NEXT-CAPITAL COHORT ENGINE</div><div class="cohort-title">WAITING FOR TODAY\'S THEME PACKETS</div><div class="cohort-sub">The planner will appear when data/themes.json finishes loading.</div></div></div>';return;}
    state.selected=state.selected.filter(function(name){return docs.some(function(theme){return theme.theme===name;});});
    if(!state.selected.length)state.selected=docs.filter(function(theme){return theme.priority==='P0';}).map(function(theme){return theme.theme;});
    save(state);
    var result=buildPlan(state,docs),allocated=result.rows.reduce(function(sum,row){return sum+row.amount;},0),newBuys=result.rows.filter(function(row){return !row.stock.owned;}).length;
    var chips=docs.map(function(theme){var on=state.selected.indexOf(theme.theme)>=0;return '<button class="cohort-chip '+(on?'on':'')+'" onclick="toggleHvmCohort(\''+esc(theme.theme).replace(/&#39;/g,"\\'")+'\')"><em>'+esc(theme.priority)+' · '+Number(theme.target_pct||0)+'%</em><b>'+esc(theme.theme)+'</b><span>'+Number(theme.owned_count||0)+' owned · '+Number(theme.candidate_count||0)+' candidates · '+esc(theme.research_mode||'daily research')+'</span></button>';}).join('');
    var rows=result.rows.map(function(row,index){
      var stock=row.stock,price=Number(stock.price),units=price>0?row.amount/price:0,status=String(stock.status||'WATCH').toUpperCase();
      return '<tr><td>'+(index+1)+'</td><td><b>'+esc(row.theme.theme)+'</b><br><span style="color:#758b80">'+esc(row.theme.priority)+' · '+money(row.theme._current)+' now → '+money(row.theme._target)+' target</span></td><td><span class="cohort-ticker">'+esc(stock.ticker)+'</span><br><span style="color:#758b80">'+esc(stock.name||'')+'</span></td><td><span class="cohort-action '+actionClass(status)+'">'+esc(status)+'</span></td><td>'+money(price,2)+(Number(stock.change_pct)||0?' · '+(Number(stock.change_pct)>=0?'+':'')+Number(stock.change_pct).toFixed(2)+'%':'')+'</td><td style="color:#e6c868">'+money(row.amount)+'</td><td>'+(units?units.toFixed(units<1?3:2):'price pending')+'</td><td>'+esc(stock.reason||'Daily cohort research candidate')+'</td></tr>';
    }).join('')||'<tr><td colspan="8">No eligible stocks are available for the selected cohorts.</td></tr>';
    host.innerHTML='<div class="cohort-planner-head"><div><div class="cohort-kicker">HVM · NEXT-CAPITAL COHORT ENGINE</div><div class="cohort-title">TELL THE FIRM WHERE THE NEXT '+money(state.budget)+' CAN GO</div><div class="cohort-sub">Select only the cohorts you want funded. The engine recalculates theme gaps, current holdings, P-levels, new-buy candidates and estimated units from today\'s theme packets.</div></div><div class="cohort-controls"><div class="cohort-field"><label>NEW CAPITAL</label><input type="number" min="100" step="100" value="'+state.budget+'" onchange="setHvmCohortBudget(this.value)"></div><div class="cohort-field"><label>ALLOCATION MODE</label><select onchange="setHvmCohortMode(this.value)"><option value="gap" '+(state.mode==='gap'?'selected':'')+'>Target-gap weighted</option><option value="p0" '+(state.mode==='p0'?'selected':'')+'>P0 first</option><option value="equal" '+(state.mode==='equal'?'selected':'')+'>Equal cohorts</option></select></div><button class="cohort-preset" onclick="setHvmCohortPreset(\'p0\')">P0 ONLY</button><button class="cohort-preset" onclick="setHvmCohortPreset(\'all\')">ALL THEMES</button></div></div><div class="cohort-selector">'+chips+'</div><div class="cohort-summary"><div class="cohort-summary-cell"><div class="cohort-summary-v">'+money(state.budget)+'</div><div class="cohort-summary-l">CEO capital instruction</div></div><div class="cohort-summary-cell"><div class="cohort-summary-v">'+state.selected.length+'</div><div class="cohort-summary-l">selected cohorts</div></div><div class="cohort-summary-cell"><div class="cohort-summary-v">'+newBuys+'</div><div class="cohort-summary-l">new-position research candidates</div></div><div class="cohort-summary-cell"><div class="cohort-summary-v">'+modeLabel(state.mode)+'</div><div class="cohort-summary-l">allocation rule</div></div></div><div class="cohort-table-wrap"><table class="cohort-table"><thead><tr><th>#</th><th>COHORT / GAP</th><th>STOCK</th><th>RESEARCH STATUS</th><th>REFERENCE PRICE</th><th>DRAFT CAPITAL</th><th>EST. UNITS</th><th>WHY IN COHORT</th></tr></thead><tbody>'+rows+'</tbody></table></div><div class="cohort-footer"><span>Allocated '+money(allocated)+' across '+result.cohorts.length+' cohorts · selection is stored on this browser.</span><span class="cohort-warning">CEO PLANNING DRAFT · RESEARCH CANDIDATES ARE NOT ORDERS · EXECUTION DISABLED</span></div>';
  };
  window.toggleHvmCohort=function(name){var state=load(),index=state.selected.indexOf(name);if(index>=0&&state.selected.length>1)state.selected.splice(index,1);else if(index<0)state.selected.push(name);save(state);window.buildCohortAllocator();};
  window.setHvmCohortBudget=function(value){var state=load();state.budget=Math.max(100,Math.min(10000000,Number(value)||20000));save(state);window.buildCohortAllocator();};
  window.setHvmCohortMode=function(value){var state=load();state.mode=value;save(state);window.buildCohortAllocator();};
  window.setHvmCohortPreset=function(preset){var state=load(),docs=themes();state.selected=docs.filter(function(theme){return preset==='all'||theme.priority==='P0';}).map(function(theme){return theme.theme;});save(state);window.buildCohortAllocator();};
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',function(){setTimeout(window.buildCohortAllocator,1000);});else setTimeout(window.buildCohortAllocator,1000);
})();
