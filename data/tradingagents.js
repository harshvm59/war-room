/* Text-only research rendering: model output is never interpreted as HTML. */
(function(root){
  'use strict';
  var packet=null;
  var labels={market_report:'Market analysis',fundamentals_report:'Business fundamentals',bull_case:'Bull case',bear_case:'Bear case',investment_plan:'Research synthesis',trader_investment_plan:'Proposed approach',risk_review:'Risk review',final_trade_decision:'Final assessment'};
  function node(tag,text,cls){var el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
  function date(value){var t=new Date(value);return value&&Number.isFinite(t.getTime())?t.toLocaleString():'Not yet generated';}
  function stale(item){var t=Date.parse(item.updated_at);return !Number.isFinite(t)||Date.now()-t>8*86400000||t>Date.now()+300000;}
  root.renderTradingAgents=function(data){
    packet=data;var status=document.getElementById('tradingagentsStatus'),select=document.getElementById('tradingagentsTicker');if(!status||!select)return;
    status.replaceChildren(node('div',data.status==='ready'?'Research available':'Research blocked','research-status'));
    status.append(node('p',data.error&&data.error.message||'Reports are research opinions. Retain cash / no action until you have reviewed the evidence and portfolio fit.'));
    status.append(node('p','Last attempt: '+date(data.last_attempt_at)+' · Last completed: '+date(data.updated_at),'research-note'));
    var selected=select.value;select.replaceChildren(node('option','All reviewed holdings'));select.options[0].value='';
    (data.items||[]).forEach(function(item){var option=node('option',item.ticker);option.value=item.ticker;select.append(option);});
    select.value=selected;draw();
  };
  function draw(){
    var target=document.getElementById('tradingagentsReports'),select=document.getElementById('tradingagentsTicker');if(!packet||!target)return;target.replaceChildren();
    var rows=(packet.items||[]).filter(function(item){return !select.value||item.ticker===select.value;});
    if(!rows.length){target.append(node('div','No completed TradingAgents reports yet. Once the API key and billing are configured, the next permitted run will generate a real report.','research-card'));return;}
    rows.forEach(function(item){var card=node('article',undefined,'research-card');var limited=stale(item)||packet.status!=='ready';card.append(node('h2',item.ticker+' · '+(limited?'Previous research — review required':item.rating+' · research opinion')));card.append(node('p',date(item.updated_at)+(stale(item)?' · STALE':''),'research-note'));card.append(node('p',item.limitation||'Manual review required.'));
      Object.keys(labels).forEach(function(key){var text=item.reports&&item.reports[key];if(!text)return;var detail=node('details');detail.append(node('summary',labels[key]));detail.append(node('pre',text,'research-report-text'));card.append(detail);});target.append(card);});
  }
  function projection(){
    var output=document.getElementById('wealthProjection');if(!output)return;
    var monthly=Number(document.getElementById('wealthContribution').value),rate=Number(document.getElementById('wealthReturn').value);
    if(!Number.isFinite(monthly)||monthly<0||monthly>100000||!Number.isFinite(rate)||rate<0||rate>20){output.textContent='Enter a monthly contribution from $0–$100,000 and an illustrative return from 0–20%.';return;}
    var portfolio=root.HVMRefresh&&root.HVMRefresh.packets.portfolio;
    var initial=portfolio&&portfolio.meta&&(portfolio.meta.broker_account_value_usd);
    if(!Number.isFinite(Number(initial))||!initial){output.textContent='Waiting for a published broker balance to calculate your scenario.';return;}
    var value=Number(initial),months=0,r=Math.pow(1+rate/100,1/12)-1;
    while(value<1000000&&months<1200){value=value*(1+r)+monthly;months++;}
    output.textContent=months===1200?'This scenario does not reach $1M within 100 years.':months===0?'Your starting balance already meets the $1M target.':'Illustrative time to $1M: '+Math.floor(months/12)+' years '+months%12+' months. Based on the published broker snapshot.';
  }
  var actions=document.getElementById('actionCmd');if(actions){var extra=node('details',undefined,'research-card');extra.append(node('summary','Rule-based technical signals · optional details'));actions.before(extra);extra.append(actions);}
  var select=document.getElementById('tradingagentsTicker');if(select)select.addEventListener('change',draw);
  ['wealthContribution','wealthReturn'].forEach(function(id){var el=document.getElementById(id);if(el)el.addEventListener('input',projection);});
  document.addEventListener('hvm:market-prices-updated',projection);setInterval(projection,10000);projection();
})(window);
