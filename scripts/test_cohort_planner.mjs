import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const themes = JSON.parse(fs.readFileSync('data/themes.json', 'utf8')).items;
const portfolio = JSON.parse(fs.readFileSync('data/portfolio.json', 'utf8')).holdings;
const prices = JSON.parse(fs.readFileSync('data/prices.json', 'utf8')).prices;
const host = {innerHTML: ''};
const storage = new Map();

const context = {
  console,
  Intl,
  JSON,
  Math,
  Number,
  String,
  Array,
  Date,
  setTimeout(fn){ fn(); return 1; },
  localStorage: {
    getItem(key){ return storage.has(key) ? storage.get(key) : null; },
    setItem(key, value){ storage.set(key, String(value)); },
  },
  document: {
    readyState: 'complete',
    getElementById(id){
      if(id === 'cohortAllocator') return host;
      if(id === 'deploy') return {querySelector(){ return {}; }, insertBefore(){}, appendChild(){}};
      return null;
    },
    createElement(){ return host; },
  },
};
context.window = context;
context.PORT = portfolio.map(row => ({
  t: row.ticker,
  units: row.units,
  val: Number(row.units || 0) * Number(prices[row.ticker]?.price || row.avg_cost || 0),
}));
context.THEMES_LIVE = themes;

vm.createContext(context);
vm.runInContext(fs.readFileSync('data/cohort-planner.js', 'utf8'), context);

assert.match(host.innerHTML, /NEXT-CAPITAL COHORT ENGINE/);
assert.match(host.innerHTML, /\$20,000/);
assert.match(host.innerHTML, /NEW BUY/);
assert.match(host.innerHTML, /Allocated \$20,000 across 3 cohorts/);
assert.equal((host.innerHTML.match(/class="cohort-chip /g) || []).length, 8);

context.setHvmCohortBudget(30000);
context.setHvmCohortMode('p0');
context.setHvmCohortPreset('p0');
assert.match(host.innerHTML, /\$30,000/);
assert.match(host.innerHTML, /Allocated \$30,000 across 2 cohorts/);
assert.match(host.innerHTML, /P0-FIRST/);
assert.match(host.innerHTML, /Energy &amp; Nuclear Power/);
assert.match(host.innerHTML, /Defense &amp; National Security/);

console.log('cohort planner PASS: 8 selectable themes, exact budget allocation, P0 preset, and new-buy candidates');
