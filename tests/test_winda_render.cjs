/* Wind A must be inserted before CSI500 and never display fabricated figures. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
const order=['winda-panel','history-panel','star-panel','bse-panel'];
const pos=order.map(id=>html.indexOf('id="'+id+'"'));
assert.ok(pos.every((x,i)=>x>=0&&(i===0||x>pos[i-1])),'correct chart order');
assert.ok(html.indexOf('id="winda-section"')<html.indexOf('id="cards"'),'card first');
assert.ok(html.indexOf('data-valuation-status="winda"')<html.indexOf('data-valuation-status="csi500"'));
const nodes={};
function node(){return {
  className:'',innerHTML:'',textContent:'',dataset:{},events:{},
  classList:{toggle(){}},setAttribute(){},
  querySelectorAll(){return []},querySelector(){return null},
  addEventListener(name,fn){this.events[name]=fn}
};}
const document={getElementById(id){return nodes[id]||(nodes[id]=node())}};
const ctx={window:{},document,console,Date};
vm.runInNewContext(fs.readFileSync('winda.js','utf8'),ctx);
ctx.window.renderWindAllA({valid:false,code:'881001.WI',reason:'source unavailable'});
assert.ok(nodes['winda-card'].innerHTML.includes('—'),'never guess a score');
assert.ok(nodes['winda-chart'].innerHTML.includes('缺少可核验历史数据'));
const points=[];let date=new Date('2016-09-30T00:00:00Z');
for(let i=0;i<530;i++){points.push([date.toISOString().slice(0,10),2+(i%30)*.08]);date.setUTCDate(date.getUTCDate()+7);}
const range={
 p10:1.5,p20:1.9,p50:2.6,p80:3.5,p90:4.1,
 percentile:62,sampleCount:2400,referenceDate:'2026-09-30'
};
ctx.window.renderWindAllA({
 valid:true,code:'881001.WI',date:points.at(-1)[0],
 pe:21,yield10:2,erp:2.7619,
 periods:{'10':range,'5':range,'3':range},points
});
assert.ok(nodes['winda-card'].innerHTML.includes('62.00'),'live score uses verified ERP percentile');
assert.ok(nodes['winda-card'].innerHTML.includes('2.76%'));
assert.ok(nodes['winda-chart'].innerHTML.includes('<svg'),'renders real ERP');
assert.ok(nodes['winda-chart'].innerHTML.includes('circle'),'current marker');
console.log('PASS: Wind All-A card, chart, unavailable states and ordering');
