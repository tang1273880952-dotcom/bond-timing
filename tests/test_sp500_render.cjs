/* A US monthly chart must have its own horizon, five reference levels and health state. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
assert.ok(html.indexOf('id="sp500-panel"')>html.indexOf('id="bse-panel"'));
assert.ok(html.indexOf('id="sp500-panel"')<html.indexOf('id="gold-panel"'));
const nodes={};
function node(){return {innerHTML:'',textContent:'',className:'',disabled:false,
  classList:{toggle(){}},setAttribute(){},querySelectorAll(){return []},
  addEventListener(k,fn){this['on_'+k]=fn},getBoundingClientRect(){return {width:860,left:0}}};}
const document={getElementById(id){return nodes[id]||(nodes[id]=node())}};
const window={dataHealth(){return {ok:true,label:''}}};
const ctx={document,window,console};
vm.runInNewContext(fs.readFileSync('sp500.js','utf8'),ctx);
const source=JSON.parse(fs.readFileSync('data/us_latest.json','utf8'));
const payload=JSON.parse(JSON.stringify(source.history));
assert.ok(payload?.valid,'real verified US history is required');
// Fixed percentiles avoid a test depending on tomorrow's market movement.
payload.periods['10'].percentile=12;
payload.periods['3'].percentile=88;
ctx.window.renderSP500(payload,{success:true});
let svg=nodes['sp500-chart'].innerHTML;
assert.ok(svg.includes('id="sp500-svg"'));
assert.ok(svg.includes('真实ERP月线'));
assert.ok(!svg.includes('id="history-'),'US SVG IDs must not collide with CSI500');
const refs=[...svg.matchAll(/<line[^>]+y1="([^"]+)" y2="([^"]+)"[^>]+stroke-dasharray="6 4"/g)];
assert.strictEqual(refs.length,5);
assert.ok(refs.every(r=>r[1]===r[2]),'monthly percentile references must be horizontal');
assert.ok(nodes['sp500-current'].innerHTML.includes('近10年历史分位（月度）'));
assert.ok(nodes['sp500-current'].innerHTML.includes('12.0%'));
assert.ok(nodes['sp500-frequency'].textContent.includes('ERP月线'));
assert.ok(nodes['sp500-chart'].innerHTML.includes('stroke="#8450C6"'));
nodes['sp500-svg'].on_pointermove({clientX:700});
assert.ok(nodes['sp500-hover'].textContent.includes('ERP'));
assert.ok(nodes['sp500-hover'].textContent.includes('当前水平参考线'));
const tenLegend=nodes['sp500-legend'].innerHTML;
nodes['sp500-panel'].on_click({target:{closest(s){return s==='[data-sp500-years]'?{dataset:{sp500Years:'3'}}:null}}});
assert.ok(nodes['sp500-current'].innerHTML.includes('近3年历史分位（月度）'));
assert.ok(nodes['sp500-current'].innerHTML.includes('88.0%'));
assert.ok(nodes['sp500-current'].className.includes('tone-cheap'));
assert.notStrictEqual(nodes['sp500-legend'].innerHTML,tenLegend);
nodes['sp500-panel'].on_click({target:{closest(s){return s==='[data-sp500-index-toggle]'?nodes['sp500-index-toggle']:null}}});
assert.ok(!nodes['sp500-chart'].innerHTML.includes('stroke="#8450C6"'));
window.dataHealth=()=>({ok:false,label:'更新失败，沿用旧数据'});
ctx.window.renderSP500(payload,{success:false});
assert.ok(nodes['sp500-current'].innerHTML.includes('更新失败'));
ctx.window.renderSP500(null,{success:false});
assert.strictEqual(nodes['sp500-chart'].innerHTML,'');
assert.ok(nodes['sp500-current'].className.includes('tone-neutral'));
console.log('PASS: SP500 placement, monthly ERP, five horizontal bands, independent years, index toggle and stale/empty state');
