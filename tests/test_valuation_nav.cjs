/* Floating jump menu targets, status direction, selected horizon, refresh and accessibility. */
const assert=require('assert'),fs=require('fs'),vm=require('vm');
const html=fs.readFileSync('index.html','utf8');
const code=fs.readFileSync('valuation-nav.js','utf8');
const targetKeys=[
 ['csi500','history-panel'],['star100','star-panel'],['bse50','bse-panel'],
 ['399975','industry-399975'],['399989','industry-399989'],
 ['399971','industry-399971'],['399998','industry-399998'],
 ['000807','industry-000807'],['399997','industry-399997'],
 ['399986','industry-399986']
];
for(const [key,id] of targetKeys){
  assert.ok(html.includes('id="'+id+'"'),'missing target '+id);
  assert.ok(html.includes('href="#'+id+'"'),'missing jump link '+id);
  assert.ok(html.includes('data-valuation-status="'+key+'"'),'missing status '+key);
}
assert.strictEqual((html.match(/class="valuation-jump-link"/g)||[]).length,10);
assert.ok(html.includes('aria-controls="valuation-jump-panel"'));
assert.ok(html.includes('aria-expanded="false"'));
assert.ok(html.includes('id="valuation-jump-panel"')&&html.includes('hidden'));

const statusNodes=Object.fromEntries(targetKeys.map(([key])=>[key,{
  dataset:{tone:'unknown'},textContent:'暂无',title:''
}]));
const yearStates={'history-panel':10,'star-panel':3,'bse-panel':3};
for(const [key,id] of targetKeys.slice(3))yearStates[id]=3;
const listeners={};
const button={
  attrs:{},events:{},focused:false,
  addEventListener(n,fn){this.events[n]=fn},
  setAttribute(n,value){this.attrs[n]=value},
  focus(){this.focused=true}
};
const panel={hidden:true,events:{},addEventListener(n,fn){this.events[n]=fn}};
const wrap={classList:{toggle(){}},contains(t){return t===button||t===panel}};
const count={textContent:'10张图'};
const document={
  getElementById(id){return ({
    'valuation-jump':wrap,'valuation-jump-toggle':button,
    'valuation-jump-panel':panel,'valuation-jump-count':count
  })[id]||null},
  querySelector(selector){
    const status=selector.match(/data-valuation-status="([^"]+)"/);
    if(status)return statusNodes[status[1]]||null;
    const id=selector.match(/^#([\w-]+) \[(data-[\w-]+)\]\[aria-pressed="true"\]$/);
    if(id){
      const value=yearStates[id[1]];
      return value?{getAttribute(name){return name===id[2]?String(value):null}}:null;
    }
    return null;
  },
  addEventListener(n,fn){listeners[n]=fn}
};
const context={window:{},document,console,Date};
vm.runInNewContext(code,context);
const market=JSON.parse(fs.readFileSync('data/latest.json','utf8'));
const industry=JSON.parse(fs.readFileSync('data/industry_latest.json','utf8'));
context.window.updateValuationJump(market,industry);
assert.strictEqual(statusNodes.csi500.dataset.tone,'watch','ERP 10-year ~79% should be relatively cheap');
assert.strictEqual(statusNodes.star100.dataset.tone,'cheap','higher ERP percentile means cheap');
assert.strictEqual(statusNodes.bse50.dataset.tone,'neutral','middle ERP is neutral');
assert.strictEqual(statusNodes['399975'].dataset.tone,'cheap','low PE percentile means cheap');
assert.strictEqual(statusNodes['399986'].dataset.tone,'rich','high PE percentile means expensive');
assert.strictEqual(statusNodes['399997'].dataset.tone,'caution','3-year white spirits PE is expensive');
assert.ok(statusNodes['399986'].textContent.includes('99%'));
assert.ok(statusNodes['399989'].title.includes('近3年历史分位'));
yearStates['industry-399997']=10;
listeners.click({target:{closest(sel){return sel.includes('data-industry-years')?{}:null}}});
assert.strictEqual(statusNodes['399997'].dataset.tone,'watch','10-year PE band should differ from 3-year');
assert.ok(statusNodes['399997'].title.includes('近10年历史分位'));
button.events.click();
assert.strictEqual(panel.hidden,false);
assert.strictEqual(button.attrs['aria-expanded'],'true');
panel.events.click({target:{closest(){return {href:'#history-panel'}}}});
assert.strictEqual(panel.hidden,true);
button.events.click();
listeners.keydown({key:'Escape'});
assert.strictEqual(panel.hidden,true);
assert.ok(button.focused);
context.window.updateValuationJump({mode:'error'},null);
for(const [key] of targetKeys){
  assert.strictEqual(statusNodes[key].textContent,'暂无','should not fabricate unavailable '+key);
  assert.strictEqual(statusNodes[key].dataset.tone,'unknown');
}
console.log('PASS: floating navigation targets, data-driven colors, horizons, refresh, close and missing data');
