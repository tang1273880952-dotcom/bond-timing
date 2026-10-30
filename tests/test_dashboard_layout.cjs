/* Dashboard layout, live data wiring, and expandable asset cards. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
const css=fs.readFileSync('styles.css','utf8');
const ids=['cards','us-section','gold-section','history-panel','star-panel','bse-panel','gold-panel'];
const offsets=ids.map(id=>html.indexOf('id="'+id+'"'));
assert.ok(offsets.every(x=>x>=0),'required live chart containers');
assert.ok(offsets.every((x,i)=>i===0||x>offsets[i-1]),'four-asset overview before three specified charts');
assert.ok(html.includes('新增资金观察方向'));
assert.ok(html.includes('历史估值图'));
assert.ok(!html.includes('a-share/'),'dashboard must not link to removed stock screener');
assert.ok(!html.includes('id="allocTitle"'),'remove duplicate allocation panel');
assert.ok(html.includes('data-industry-code="399986"'),'seven modules follow BSE50');
assert.ok(css.includes('.tone-cheap')&&css.includes('.tone-rich'),'readable low/high valuation colors');
const nodes={};
function node(){return {
  innerHTML:'',textContent:'',className:'',dataset:{},
  classList:{toggle(){}},setAttribute(){},
  addEventListener(k,fn){this['on_'+k]=fn},
  querySelector(){return null},querySelectorAll(){return []},focus(){}
};}
const document={getElementById(id){return nodes[id]||(nodes[id]=node());}};
const ctx={document,window:{},Date,console,localStorage:{getItem(){return null},setItem(){}},
  fetch:async url=>({ok:true,json:async()=>JSON.parse(
    fs.readFileSync(String(url).replace(/\?.*$/,''),'utf8'))})};
vm.runInNewContext(fs.readFileSync('app.js','utf8'),ctx);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  const cards=nodes.cards.innerHTML;
  const order=['中证500','10年国债ETF','30年国债ETF'].map(s=>cards.indexOf(s));
  assert.ok(order.every((v,i)=>v>=0&&(i===0||v>order[i-1])),'fixed asset order');
  assert.ok(cards.includes('valuation-status'),'valuation label');
  assert.ok(cards.includes('国债收益率代理'),'distinguish ETF price from yield proxy');
  assert.ok(nodes['us-card'].innerHTML.includes('valuation-status'),'US matching valuation card');
  assert.ok(nodes.pick.textContent&&!nodes.pick.textContent.includes('等待'),'dynamic capital watch signal');
  assert.ok(nodes['us-section'].className.includes('tone-'),'US card color status');
  nodes.cards.on_click({target:{closest(sel){
    if(sel==='[data-expand]')return {dataset:{expand:'csi500'}};
    if(sel==='[data-card]')return {dataset:{card:'csi500'}};
    return null;
  }}});
  assert.ok(nodes.cards.innerHTML.includes('PE-TTM'),'expanded card contains verified full data');
  console.log('PASS: simple dashboard layout, valuation colors, capital guidance, expandable details');
})().catch(err=>{console.error(err);process.exitCode=1});
