/* Regression: higher ERP percentile curves must appear above lower ones. */
const fs=require('fs');
const vm=require('vm');
const assert=require('assert');
const code=fs.readFileSync('history.js','utf8');
function node(){return {
  innerHTML:'',textContent:'',dataset:{},classList:{toggle(){}},
  setAttribute(){},querySelectorAll(){return []},
  addEventListener(name,fn){this['on_'+name]=fn},
  getBoundingClientRect(){return {width:860,left:0}},
};}
const dom={};
const doc={getElementById(id){return dom[id]||(dom[id]=node());}};
const ctx={document:doc,window:{},console};
vm.runInNewContext(code,ctx);
const bands=Array.from({length:37},(_,i)=>{
  const date=new Date(Date.UTC(2023,9+i,28)).toISOString().slice(0,10);
  return [date,1.3,1.7,2.3,3.3,4.3];
});
const p={percentile:72.5,p10:1.3,p20:1.7,p50:2.3,p80:3.3,p90:4.3,sampleCount:700,bands};
const first=Date.parse('2023-10-28T00:00:00Z'),last=Date.parse('2026-10-28T00:00:00Z');
const points=Array.from({length:180},(_,i)=>[
  new Date(first+i*(last-first)/179).toISOString().slice(0,10),2.3+Math.sin(i/20)*.5
]);
ctx.window.renderHistory({frequency:'weekly',series:{csi500:{
  date:'2026-10-28',latest:2.7,points,periods:{'10':p,'3':p,'5':p}
}}});
const svg=dom['history-chart'].innerHTML;
assert.ok(svg.includes('<svg'),'SVG rendered');
function firstY(color){
  const re=new RegExp('<path d="M([\\d.]+) ([\\d.]+)[^"]*" fill="none" stroke="'+color+'"');
  const match=svg.match(re);
  assert.ok(match,'Missing percentile line '+color);
  return Number(match[2]);
}
const y90=firstY('#147D52'),y80=firstY('#55AC81'),y50=firstY('#939BAA'),
  y20=firstY('#E3A364'),y10=firstY('#C66B43');
assert.ok(y90<y80&&y80<y50&&y50<y20&&y20<y10,
  '90th-percentile green MUST be above 10th-percentile orange');
assert.ok(dom['history-legend'].innerHTML.includes('90% · 极低估参考（目前4.30%）'));
assert.ok(dom['history-legend'].innerHTML.includes('10% · 高估参考（目前1.30%）'));
dom['history-svg'].on_pointermove({clientX:830});
assert.ok(dom['history-hover'].textContent.includes('80% 3.30%'));
assert.ok(dom['history-hover'].textContent.includes('20% 1.70%'));
console.log('PASS percentile color direction, band values and hover references');
