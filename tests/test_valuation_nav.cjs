/* Floating valuation navigator: automatic chart-in-view highlighting. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
const css=fs.readFileSync('styles.css','utf8');
const source=fs.readFileSync('valuation-nav.js','utf8');
const pairs=[
 ['csi500','history-panel'],['star100','star-panel'],['bse50','bse-panel'],
 ['399975','industry-399975'],['399989','industry-399989'],
 ['399971','industry-399971'],['399998','industry-399998'],
 ['000807','industry-000807'],['399997','industry-399997'],
 ['399986','industry-399986']
];
assert.ok(html.includes('aria-label="固定历史估值快捷导航"'));
assert.ok(html.includes('class="valuation-jump-track"'));
assert.ok(!html.includes('valuation-jump-toggle'));
assert.ok(!html.includes('valuation-jump-panel'));
assert.ok(css.includes('position:fixed;top:0;left:50%'));
assert.ok(css.includes('overflow-x:auto'));
assert.ok(css.includes('flex-direction:column'));
assert.ok(css.includes('scroll-margin-top:calc(var(--valuation-nav-height) + 14px)'));
assert.ok(css.includes('.valuation-jump-link.is-current{'),'active background class');
assert.ok(css.includes('inset 0 -3px 0'),'active bottom border');
assert.strictEqual((html.match(/class="valuation-jump-link"/g)||[]).length,10);
for(const [key,id] of pairs){
 assert.ok(html.includes('id="'+id+'"'),'target '+id);
 assert.ok(html.includes('href="#'+id+'"'),'jump '+id);
 assert.ok(html.includes('data-valuation-status="'+key+'"'),'status '+key);
}
const chips=Object.fromEntries(pairs.map(([key])=>[key,{dataset:{tone:'unknown'},textContent:'暂无',title:''}]));
const years={'history-panel':10,'star-panel':3,'bse-panel':3};
for(const [,id] of pairs.slice(3)) years[id]=3;
const winListeners={},docListeners={};
let y=0;
const navLinks=Object.fromEntries(pairs.map(([key,id])=>[id,{
 id,attrs:{href:'#'+id},flags:{},
 classList:{toggle(name,value){this.owner.flags[name]=value}},
 setAttribute(name,value){this.attrs[name]=value},
 removeAttribute(name){delete this.attrs[name]},
 getAttribute(name){return this.attrs[name]}
}]));
for(const link of Object.values(navLinks))link.classList.owner=link;
const sections=Object.fromEntries(pairs.map(([,id],i)=>[id,{
 getBoundingClientRect(){
   const top=650+i*690-y;
   return {top,bottom:top+610};
 }
}]));
const nav={
 getBoundingClientRect(){return {bottom:66}},
 querySelector(sel){
   const m=sel.match(/a\[href="#([^"]+)"\]/);
   return m?navLinks[m[1]]:null;
 },
 addEventListener(name,cb){this['on'+name]=cb}
};
const document={
 getElementById(id){return id==='valuation-jump'?nav:sections[id]||null},
 addEventListener(name,cb){docListeners[name]=cb},
 querySelector(sel){
   const chip=sel.match(/data-valuation-status="([^"]+)"/);
   if(chip)return chips[chip[1]]||null;
   const m=sel.match(/^#([\w-]+) \[(data-[\w-]+)\]\[aria-pressed="true"\]$/);
   if(m)return {getAttribute(name){return name===m[2]?String(years[m[1]]):null}};
   return null;
 }
};
const window={
 innerHeight:900,
 addEventListener(name,cb){winListeners[name]=cb},
 requestAnimationFrame(fn){fn()}
};
const ctx={document,window,console,Date};
vm.runInNewContext(source,ctx);
function currentTargets(){return pairs.filter(([,id])=>navLinks[id].flags['is-current']).map(x=>x[1]);}
function visibleAt(scrollY){
 y=scrollY;
 winListeners.scroll();
}
assert.deepStrictEqual(currentTargets(),[],'no highlight above first chart');
visibleAt(550);
assert.deepStrictEqual(currentTargets(),['history-panel'],'scroll to first chart');
assert.strictEqual(navLinks['history-panel'].attrs['aria-current'],'location');
visibleAt(1290);
assert.deepStrictEqual(currentTargets(),['star-panel'],'switch when scrolling to next');
assert.strictEqual(navLinks['history-panel'].attrs['aria-current'],undefined);
visibleAt(2050);
assert.deepStrictEqual(currentTargets(),['bse-panel'],'third chart gets highlight');
visibleAt(550+690*8);
assert.deepStrictEqual(currentTargets(),['industry-399997'],'near bottom gets white spirits');
winListeners.resize();
assert.deepStrictEqual(currentTargets(),['industry-399997'],'resize preserves selected');
visibleAt(0);
nav.onclick({target:{closest(){return navLinks['industry-399986']}}});
assert.deepStrictEqual(currentTargets(),['industry-399986'],'click highlights target even before anchor scroll');
visibleAt(690*9+550);
assert.deepStrictEqual(currentTargets(),['industry-399986'],'scrolling to anchor keeps selected');
visibleAt(0);
assert.deepStrictEqual(currentTargets(),[],'no highlight when chart out of view');
// Stable fixtures: real market percentiles can cross these zones on any day.
// Such a market move must never fail the scheduled data-update workflow.
const market={mode:'live',history:{series:{csi500:{date:'2026-10-29',
  periods:{'10':{percentile:75},'3':{percentile:50}}}}},
  star100:{valid:true,date:'2026-10-29',periods:{'3':{percentile:85}}},
  bse50:{valid:true,date:'2026-10-29',periods:{'3':{percentile:50}}}};
const industry={items:pairs.slice(3).map(([code])=>({code,valid:true,
  date:'2026-10-29',metric:'PE-TTM',periods:{'3':{percentile:65},
  '10':{percentile:30}}}))};
for(const [code,rank] of [['399975',1.2],['399998',97.9],['399986',63.1]]){
  const item=industry.items.find(x=>x.code===code);
  item.metric='PB';item.pointMetric='PB_10Y_PERCENTILE';item.value=code==='399986'?.75:1.5;
  item.periods=Object.fromEntries(['3','5','10'].map(y=>[y,{percentile:rank,rankYears:10}]));
}
ctx.window.updateValuationJump(market,industry);
assert.strictEqual(chips.csi500.dataset.tone,'watch','ERP 10-year mid-high cheaper');
assert.strictEqual(chips.star100.dataset.tone,'cheap');
assert.strictEqual(chips.bse50.dataset.tone,'neutral');
assert.strictEqual(chips['399975'].dataset.tone,'cheap');
assert.strictEqual(chips['399986'].dataset.tone,'caution');
assert.strictEqual(chips['399997'].dataset.tone,'caution');
assert.ok(chips['399986'].textContent.includes('63%'));
assert.ok(chips['399986'].title.includes('PB近10年分位'));
assert.strictEqual(chips['399998'].dataset.tone,'rich');
years['industry-399997']=10;
docListeners.click({target:{closest(q){return q.includes('data-industry-years')?{}:null}}});
assert.strictEqual(chips['399997'].dataset.tone,'watch');
assert.ok(chips['399997'].title.includes('近10年'));
const invalid=JSON.parse(JSON.stringify(industry));
for(const item of invalid.items){
  if(['399975','399998','399986'].includes(item.code)){
    item.metric='PE-TTM';delete item.pointMetric;
  }
}
ctx.window.updateValuationJump(market,invalid);
for(const code of ['399975','399998','399986']){
  assert.strictEqual(chips[code].textContent,'暂无','old PE data must not populate PB navigation');
}
ctx.window.updateValuationJump({mode:'error'},null);
for(const [key] of pairs){
 assert.strictEqual(chips[key].textContent,'暂无','missing estimate '+key);
 assert.strictEqual(chips[key].dataset.tone,'unknown');
}
ctx.window.dataHealth=()=>({ok:false,label:'多日未更新，暂作历史参考'});
ctx.window.updateValuationJump(market,industry,{market:{success:true},industry:{success:true}});
for(const [key] of pairs){
 assert.strictEqual(chips[key].textContent,'待更新','stale valuation must not look current '+key);
 assert.strictEqual(chips[key].dataset.tone,'unknown');
}
console.log('PASS: active chart highlights on scrolling and navigation clicks; badges still reflect valuations');
