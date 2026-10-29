/* Horizontal percentile chart: five constant Y-lines, dual axis, hover, toggle. */
const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
const code=fs.readFileSync('history.js','utf8');
function node(){return {
  innerHTML:'',textContent:'',disabled:false,dataset:{},classList:{toggle(){}},
  setAttribute(){},querySelectorAll(){return []},
  addEventListener(name,fn){this['on_'+name]=fn},
  getBoundingClientRect(){return {width:860,left:0}},
};}
const dom={};
const doc={getElementById(id){return dom[id]||(dom[id]=node());}};
const ctx={document:doc,window:{},console};
vm.runInNewContext(code,ctx);
const first=Date.parse('2023-10-28T00:00:00Z'),last=Date.parse('2026-10-28T00:00:00Z');
const points=Array.from({length:180},(_,i)=>[
  new Date(first+i*(last-first)/179).toISOString().slice(0,10),2.3+Math.sin(i/20)*.5
]);
const indexClose={points:points.map((r,i)=>[r[0],4000+i*12])};
const createPeriod=(n)=>({
  referenceDate:'2026-09-30',percentile:65,p10:n+1.3,p20:n+1.7,
  p50:n+2.3,p80:n+3.3,p90:n+4.3,sampleCount:700,basis:'日度真实观测'
});
const data={frequency:'weekly',series:{csi500:{date:'2026-10-28',latest:2.7,
  points,indexClose,periods:{'10':createPeriod(0),'3':createPeriod(.2),'5':createPeriod(.1)}}}};
ctx.window.renderHistory(data);
const svg=dom['history-chart'].innerHTML;
assert.ok(svg.includes('<svg'),'SVG rendered');
assert.ok(!svg.includes('fill-opacity=".17"'),'no curving band shading');
assert.ok(!svg.includes('stroke-dasharray="6 4" stroke-linecap="round"'),'no historical quantile curves');
function yOf(color){
  const match=svg.match(new RegExp('<line x1="[\\d.]+" x2="[\\d.]+" y1="([\\d.]+)" y2="([\\d.]+)" stroke="'+color+'"'));
  assert.ok(match,'missing horizontal reference line '+color);
  assert.strictEqual(match[1],match[2], 'reference must be horizontal');
  return Number(match[1]);
}
const ys=['#147D52','#55AC81','#939BAA','#E3A364','#C66B43'].map(yOf);
assert.ok(ys.every((y,i)=>i===0||y>ys[i-1]),'high ERP percentiles on top');
assert.ok(svg.includes('stroke="#8450C6" stroke-opacity="0.35"'),'pale index overlay remains');
assert.ok(dom['history-legend'].innerHTML.includes('90% · 极低估参考（4.30%）'));
dom['history-svg'].on_pointermove({clientX:830});
assert.ok(dom['history-hover'].textContent.includes('当前水平参考线（2026-09-30）'));
assert.ok(dom['history-hover'].textContent.includes('80% 3.30%'));
assert.ok(dom['history-hover'].textContent.includes('20% 1.70%'));
dom['history-panel'].on_click({target:{closest(x){
  if(x==='[data-history-years]')return {dataset:{historyYears:'3'}};
  return null;
}}});
assert.ok(dom['history-frequency'].textContent.includes('近3年水平分位参考线'));
assert.ok(dom['history-legend'].innerHTML.includes('90% · 极低估参考（4.50%）'));
dom['history-panel'].on_click({target:{closest(x){
  if(x==='[data-index-toggle]')return dom['history-index-toggle'];
  return null;
}}});
assert.ok(!dom['history-chart'].innerHTML.includes('stroke="#8450C6" stroke-opacity="0.35"'));
console.log('PASS: horizontal quantiles, date-scoped levels, view switching, index toggle');
