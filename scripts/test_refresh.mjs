import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {createCoordinator,FEEDS}=require('../data/bootstrap-v2.js');
const sourceDate='2026-09-12T04:00:00Z';
let clock='2026-09-12T05:00:00Z',docs={},requests=[],applied=[],failed=new Set();
for(const [key,feed] of Object.entries(FEEDS))docs['data/'+feed.file+'.json']=key==='prices'?{updated_at:sourceDate,prices:{NVDA:{price:100}}}:key==='portfolio'?{holdings:[],meta:{broker_synced_at:sourceDate}}:{updated_at:sourceDate,items:[{ticker:key}]};
const coordinator=createCoordinator({
  async fetchJSON(path){requests.push(path);if(failed.has(path))throw Error('HTTP 503');return structuredClone(docs[path]||{status:'ok'});},
  apply(key,d,ctx){applied.push([key,structuredClone(d),ctx.changed]);},
  render(){},busy(){},now(){return clock;}
});
await coordinator.refresh();
assert.equal(applied.length,10,'every feed loads on a full refresh');
assert.equal(coordinator.state.news.sourceAt,sourceDate);
assert.equal(coordinator.state.news.checkedAt,clock);
requests=[];clock='2026-09-12T06:00:00Z';
docs['data/news.json']={updated_at:sourceDate,items:[]};
await coordinator.refresh(['news']);
assert.deepEqual(coordinator.packets.news.items,[],'empty successful feed replaces historical items');
assert.equal(coordinator.state.news.checkedAt,clock);
assert.equal(coordinator.state.news.sourceAt,sourceDate,'checking does not fake source freshness');
assert.deepEqual(requests,['data/news.json','data/refresh-status-news.json']);
failed.add('data/news.json');clock='2026-09-12T07:00:00Z';
await coordinator.refresh(['news']);
assert.equal(coordinator.state.news.error,'HTTP 503');
assert.equal(coordinator.state.news.sourceAt,sourceDate,'failed fetch preserves last valid source date');
assert.equal(coordinator.state.news.checkedAt,clock,'failed fetch still records check date');
failed.clear();await coordinator.refresh(['news']);
assert.equal(coordinator.state.news.error,null);
assert.equal(applied.at(-1)[2],true,'retry must reapply after a failed render/fetch');
// An in-flight full refresh must serialize a later manual refresh, preventing
// a slow older response from overwriting the newer manually requested packet.
let release;const gate=new Promise(resolve=>{release=resolve;});let count=0;
const queued=createCoordinator({fetchJSON:async path=>{if(path==='data/news.json'&&++count===1)await gate;return {updated_at:sourceDate,items:[{version:count}]};},apply(){},render(){},busy(){},now(){return clock;}});
const first=queued.refresh(['news']);const second=queued.refresh(['news','youtube']);release();await Promise.all([first,second]);
assert.equal(count,2,'a request during a running check is queued');
assert.equal(queued.packets.news.items[0].version,2);
// Actual page functions: Refresh Brief cannot touch cached HTML or a model API.
const html=fs.readFileSync('index.html','utf8');
for(const [i,m] of [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].entries())assert.doesNotThrow(()=>new Function(m[1]),`inline script ${i}`);
const brief=html.slice(html.indexOf('function refreshBrief(force){'),html.indexOf('// Conviction grid'));
const calls=[];
const ctx={window:{HVMRefresh:{refresh(keys,reason){calls.push([keys,reason]);return Promise.resolve();}}}};
vm.createContext(ctx);vm.runInContext(brief,ctx);await ctx.refreshBrief(true);
assert.equal(JSON.stringify(calls),JSON.stringify([[['news'],'manual']]));
assert.doesNotMatch(html,/api\.anthropic\.com|wr_brief_|wr_yt_synth_|throw new Error\('in-browser AI disabled'\)/);
assert.equal((html.match(/src="data\/bootstrap-v2.js/g)||[]).length,1,'one loader owns all feed timers');
assert.match(html,/YTVIDEOS=\[\];/,'legacy videos start empty');
assert.match(html,/TODAY_ACTIONS_MAY5=\[\];/,'legacy actions start empty');
const bootstrap=fs.readFileSync('data/bootstrap-v2.js','utf8');
assert.doesNotMatch(bootstrap,/\.concat\(window\.YTVIDEOS|fwInjected/);
assert.match(bootstrap,/setInterval\([\s\S]*60000\)/);
assert.match(bootstrap,/addEventListener\('focus'/);
assert.match(bootstrap,/addEventListener\('visibilitychange'/);
assert.match(bootstrap,/ARCHIVED \/ STALE FRAMEWORK/);
console.log('Refresh regression tests passed: ten feeds, empty replacement, checked/source dates, failure recovery, concurrent checks, manual brief routing and single scheduler.');
// Every successful empty collection clears its corresponding previous packet.
for(const [key,feed] of Object.entries(FEEDS))docs['data/'+feed.file+'.json']=key==='prices'?{updated_at:sourceDate,prices:{}}:key==='portfolio'?{holdings:[],meta:{broker_synced_at:sourceDate}}:{updated_at:sourceDate,items:[]};
await coordinator.refresh();
for(const key of Object.keys(FEEDS)){
  if(key==='prices')assert.equal(Object.keys(coordinator.packets[key].prices).length,0);
  else if(key==='portfolio')assert.equal(coordinator.packets[key].holdings.length,0);
  else assert.equal(coordinator.packets[key].items.length,0,`${key} clears old items`);
}
let applyAttempts=0;
const displayRetry=createCoordinator({fetchJSON:async()=>({updated_at:sourceDate,items:[]}),apply(key,d,ctx){if(key==='news'&&ctx.changed&&++applyAttempts===1)throw Error('render failed');},render(){},busy(){},now(){return clock;}});
await displayRetry.refresh(['news']);assert.match(displayRetry.state.news.error,/Display update failed/);
await displayRetry.refresh(['news']);assert.equal(applyAttempts,2,'identical response retries its failed display update');assert.equal(displayRetry.state.news.error,null);
const contexts=[];
let actionVersion=1;
const dependencies=createCoordinator({fetchJSON:async path=>({updated_at:sourceDate,items:[{version:path==='data/actions.json'?actionVersion:1}]}),apply(key,d,ctx){contexts.push([key,ctx.changed,[...ctx.changedKeys]]);},render(){},busy(){},now(){return clock;}});
await dependencies.refresh(['actions','analysis']);actionVersion++;await dependencies.refresh(['actions','analysis']);
assert.deepEqual(contexts.at(-1),['analysis',false,['actions']],'unchanged analysis receives changed action dependency');
assert.match(bootstrap,/key==='analysis'&&ctx.changedKeys.has\('actions'\)/,'analysis renderer observes the action dependency');
console.log('Display retry, every-feed empty replacement and action/analysis dependency tests passed.');
const {actionVerdict}=require('../data/bootstrap-v2.js');
for(const [action,expected] of [['ADD','add'],['TRIM','trim'],['HOLD','hold'],['WATCH','wait'],['','wait']])assert.equal(actionVerdict(action),expected);
assert.match(bootstrap,/old\.verdict=actionVerdict\(action\.action\)/,'stock detail badge uses the published action');
const renderOrder=[];
const finalRender=createCoordinator({fetchJSON:async()=>({updated_at:sourceDate,items:[]}),apply(key){renderOrder.push(key);},render(state,packets,jobs,errors,changed){assert.deepEqual(renderOrder,['actions','analysis']);assert.ok(changed.has('actions')&&changed.has('analysis'));renderOrder.push('derived-screens');},busy(){},now(){return clock;}});
await finalRender.refresh(['actions','analysis']);
assert.deepEqual(renderOrder,['actions','analysis','derived-screens'],'derived screens render after both published signal mutations');
assert.match(bootstrap,/changedKeys\.has\('actions'\)\|\|changedKeys\.has\('analysis'\)\)document\.dispatchEvent\(new CustomEvent\('hvm:market-prices-updated'/);
assert.doesNotMatch(html,/videos curated/,'RSS items must not be mislabeled videos after consensus rebuild');
console.log('Published action badges, immediate derived-screen rendering and source-item labels passed.');
// Provider-supplied framework citations must be useful links, never executable URLs/markup.
const badgeContext={URL,esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))};
vm.createContext(badgeContext);
vm.runInContext(bootstrap.slice(bootstrap.indexOf('function verdictColor'),bootstrap.indexOf('function applyFramework')),badgeContext);
const badge=badgeContext.frameworkBadge({overall:'REVIEW',overall_color:'red;position:fixed',score:0,questions:{},sources:[{url:'https://example.com/filing',title:'Q2 <report>',reporting_period:'FY2026 Q2'},{url:'javascript:alert(1)',title:'bad'}]});
assert.match(badge,/href="https:\/\/example.com\/filing"/);
assert.match(badge,/FY2026 Q2/);
assert.match(badge,/Q2 &lt;report&gt;/);
assert.doesNotMatch(badge,/javascript:|position:fixed|<report>/);
assert.match(badge,/REVIEW/);
console.log('Framework citations render safely with reporting periods and neutral review status.');
