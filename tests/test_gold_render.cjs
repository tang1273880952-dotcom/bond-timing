/* Gold follows SP500, shows five dynamic cost bands and a ratio view. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
assert.ok(html.indexOf('id="gold-section"')>html.indexOf('id="us-section"'));
assert.ok(html.indexOf('id="gold-section"')<html.indexOf('id="history-panel"'));
assert.ok(html.indexOf('id="gold-panel"')>html.indexOf('id="bse-panel"'));
assert.ok(html.indexOf('id="gold-panel"')<html.indexOf('id="industry-399975"'));
const nodes={};function node(){return {innerHTML:'',textContent:'',className:'',dataset:{},
 classList:{toggle(){}},setAttribute(){},querySelectorAll(){return []},
 addEventListener(k,fn){this['on_'+k]=fn},getBoundingClientRect(){return {width:900,left:0}}};}
const document={getElementById(id){return nodes[id]||(nodes[id]=node())}};
const ctx={document,window:{dataHealth(){return {ok:true,label:''}}},console,Date};
vm.runInNewContext(fs.readFileSync('gold.js','utf8'),ctx);
const payload=JSON.parse(fs.readFileSync('data/gold_latest.json','utf8'));
ctx.window.renderGold(payload,{success:true});
assert.ok(nodes['gold-card'].innerHTML.includes('× AISC'));
assert.ok(!nodes['gold-card'].innerHTML.includes('PE-TTM'));
let svg=nodes['gold-chart'].innerHTML;
assert.strictEqual((svg.match(/class="gold-reference"/g)||[]).length,5);
assert.ok(svg.includes('class="gold-main-line"'));
assert.ok(svg.match(/class="gold-reference"[^>]+d="[^"]*V/),'price references must step when published cost changes');
assert.ok(nodes['gold-note'].textContent.includes('公布次日生效'));
nodes['gold-svg'].on_pointermove({clientX:500});
assert.ok(nodes['gold-hover'].textContent.includes('AISC'));
assert.ok(nodes['gold-hover'].textContent.includes('公布'));
nodes['gold-panel'].on_click({target:{closest(sel){return sel==='[data-gold-view]'?{dataset:{goldView:'ratio'}}:null}}});
svg=nodes['gold-chart'].innerHTML;
const refs=[...svg.matchAll(/class="gold-reference"[^>]+d="([^"]+)"/g)];
assert.strictEqual(refs.length,5);
assert.ok(refs.every(r=>r[1].includes('H')&&!r[1].includes('V')),'ratio references must remain horizontal');
nodes['gold-card'].on_click({target:{closest(){return {}}}});
assert.ok(nodes['gold-card'].innerHTML.includes('成本公布日期'));
assert.ok(nodes['gold-card'].innerHTML.includes('查看公开成本来源'));
ctx.window.renderGold({...payload,costEvents:[]},{success:true});
assert.ok(nodes['gold-chart'].innerHTML.includes('缺少可核验'));
ctx.window.renderGold(null,{success:false});
assert.strictEqual(nodes['gold-chart'].innerHTML,'');
assert.ok(nodes['gold-card'].innerHTML.includes('等待真实'));
console.log('PASS: gold card order, five publication-dated cost bands, ratio view, hover, source and safe empty state');
