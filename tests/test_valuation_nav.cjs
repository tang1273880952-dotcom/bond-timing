/* Always-visible horizontal navigation, true statuses, selectable horizons. */
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
assert.ok(!html.includes('valuation-jump-count'));
assert.ok(css.includes('position:fixed;top:0;left:50%'));
assert.ok(css.includes('overflow-x:auto'));
assert.ok(css.includes('flex-direction:column'));
assert.ok(css.includes('scroll-margin-top:calc(var(--valuation-nav-height) + 14px)'));
assert.strictEqual((html.match(/class="valuation-jump-link"/g)||[]).length,10);
for(const [key,id] of pairs){
  assert.ok(html.includes('id="'+id+'"'),'target '+id);
  assert.ok(html.includes('href="#'+id+'"'),'link '+id);
  assert.ok(html.includes('data-valuation-status="'+key+'"'),'status '+key);
}
const chips=Object.fromEntries(pairs.map(([key])=>[key,{dataset:{tone:'unknown'},textContent:'暂无',title:''}]));
const years={'history-panel':10,'star-panel':3,'bse-panel':3};
for(const [,id] of pairs.slice(3))years[id]=3;
const listeners={};
const document={
  getElementById(id){return id==='valuation-jump'?{}:null},
  addEventListener(n,fn){listeners[n]=fn},
  querySelector(sel){
    const chip=sel.match(/data-valuation-status="([^"]+)"/);
    if(chip)return chips[chip[1]]||null;
    const key=sel.match(/^#([\w-]+) \[(data-[\w-]+)\]\[aria-pressed="true"\]$/);
    if(key)return {getAttribute(n){return n===key[2]?String(years[key[1]]):null}};
    return null;
  }
};
const ctx={document,window:{},console,Date};
vm.runInNewContext(source,ctx);
const market=JSON.parse(fs.readFileSync('data/latest.json','utf8'));
const industry=JSON.parse(fs.readFileSync('data/industry_latest.json','utf8'));
ctx.window.updateValuationJump(market,industry);
assert.strictEqual(chips.csi500.dataset.tone,'watch');
assert.strictEqual(chips.star100.dataset.tone,'cheap');
assert.strictEqual(chips.bse50.dataset.tone,'neutral');
assert.strictEqual(chips['399975'].dataset.tone,'cheap');
assert.strictEqual(chips['399986'].dataset.tone,'rich');
assert.strictEqual(chips['399997'].dataset.tone,'caution');
assert.ok(chips['399986'].textContent.includes('99%'));
years['industry-399997']=10;
listeners.click({target:{closest(q){return q.includes('data-industry-years')?{}:null}}});
assert.strictEqual(chips['399997'].dataset.tone,'watch','new range should update');
assert.ok(chips['399997'].title.includes('近10年'));
ctx.window.updateValuationJump({mode:'error'},null);
for(const [key] of pairs){
  assert.strictEqual(chips[key].textContent,'暂无','no fabricated '+key);
  assert.strictEqual(chips[key].dataset.tone,'unknown');
}
console.log('PASS: 10 visible horizontal links, live status, time range and missing data');
