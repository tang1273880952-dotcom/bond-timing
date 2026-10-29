const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync('star100.js','utf8');
const dom={};
function node(){return {innerHTML:'',textContent:'',classList:{toggle(){}},
setAttribute(){},addEventListener(n,fn){this['on_'+n]=fn},
querySelectorAll(){return []},getBoundingClientRect(){return {width:860,left:0}}};}
const doc={getElementById(id){return dom[id]||(dom[id]=node());}};
const ctx={document:doc,window:{},console};
vm.runInNewContext(code,ctx);
const start=Date.parse('2023-10-28T00:00:00Z'),end=Date.parse('2026-10-28T00:00:00Z');
const points=Array.from({length:150},(_,i)=>[
  new Date(start+(end-start)*i/149).toISOString().slice(0,10),2+Math.sin(i/30)
]);
const p={referenceDate:'2026-09-30',sampleCount:700,percentile:70,
p10:-1,p20:0,p50:1,p80:3,p90:4};
const data={valid:true,date:'2026-10-28',valuationDate:'2026-10-28',
erp:2.5,pe:45,yield10:1.7,indexLatest:1100,
points,indexPoints:points.map((r,i)=>[r[0],1000+i]),periods:{'1':p,'3':p}};
ctx.window.renderSTAR100(data);
const svg=dom['star-chart'].innerHTML;
assert.ok(svg.includes('stroke="#3769D2"'),'true ERP must render');
assert.ok(svg.includes('stroke="#8450C6"'),'true index overlay must render');
for(const c of ['#147D52','#55AC81','#939BAA','#E3A364','#C66B43'])assert.ok(svg.includes('stroke="'+c+'"'));
assert.ok(dom['star-summary'].innerHTML.includes('近3年分位'));
dom['star-panel'].on_click({target:{closest(sel){return sel==='[data-star-years]'?{dataset:{starYears:'1'}}:null}}});
assert.ok(dom['star-summary'].innerHTML.includes('近1年分位'));
ctx.window.renderSTAR100({valid:false,reason:'真实PE未核验',date:'2026-10-28',
indexLatest:1030,indexPoints:data.indexPoints});
assert.ok(!dom['star-chart'].innerHTML.includes('stroke="#3769D2"'),
  'must not invent ERP if source PE is missing');
console.log('PASS STAR100 independent chart, year controls and safe PE fallback');
