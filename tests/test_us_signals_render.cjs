/* S&P 500 new score appears before its historical ERP, no invented breadth. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
const pos=html.indexOf('id="sp500-signals-panel"');
assert.ok(pos>html.indexOf('id="bse-panel"'),'new module follows BSE50');
assert.ok(pos<html.indexOf('id="sp500-panel"'),'signals directly precede SP500 ERP');
assert.ok(!html.slice(pos,html.indexOf('id="sp500-panel"')).includes('id="gold-panel"'));
assert.ok(html.includes('us-signals.js'));
const nodes={};
const node=()=>({innerHTML:'',textContent:'',dataset:{},
  addEventListener(){},querySelector(){return null}});
const doc={getElementById(id){return nodes[id]||(nodes[id]=node())}};
const ctx={document:doc,window:{},console,Date};
vm.runInNewContext(fs.readFileSync('us-signals.js','utf8'),ctx);
assert.strictEqual(typeof ctx.window.renderUSSignals,'function');
const file=JSON.parse(fs.readFileSync('data/us_signals.json','utf8'));
ctx.window.renderUSSignals(file,{success:false});
assert.ok(nodes['signal-summary'].innerHTML.includes('指标'));
assert.ok(nodes['signal-status'].textContent.includes('不显示模拟买卖点'));
const dates=[];let start=Date.parse('2026-02-01T00:00:00Z');
for(let i=0;i<220;i++)dates.push([new Date(start+i*86400000).toISOString().slice(0,10),6200+i*3]);
const items={};for(const key of ['erp','vix','rsi','breadth','credit','trend']){
 items[key]={value:25,score:7,weight:key==='erp'?30:key==='trend'?10:15,
  date:'2026-10-30',unit:'',source:'test fixture'};
}
items.breadth.value=null;items.breadth.score=null;
const data={valid:true,mode:'sp500-signals-v1',asof:new Date().toISOString().slice(0,10),
 score:76,coveredWeight:85,confirmed:1,riskVeto:false,tone:'watch',
 action:'等待 / 持有观察',
 indicators:items,confirmations:[{name:'RSI回升',met:true},{name:'短线趋势确认',met:false},
 {name:'信用利差收窄',met:false}],priceHistory:dates};
ctx.window.renderUSSignals(data,{success:true});
assert.ok(nodes['signal-summary'].innerHTML.includes('76'),'value from real payload');
assert.ok(nodes['signal-summary'].innerHTML.includes('85'),'actual coverage');
assert.ok(nodes['signal-items'].innerHTML.includes('待接入'),'no made-up breadth');
assert.ok(nodes['signal-chart'].innerHTML.includes('<svg'),'real close line');
assert.ok(nodes['signal-confirm'].innerHTML.includes('RSI回升'));
ctx.window.renderUSSignals(data,{success:false});
assert.ok(nodes['signal-summary'].innerHTML.includes('停止输出新买卖信号'));
ctx.window.renderUSSignals(null,{success:false});
assert.ok(!nodes['signal-chart'].innerHTML.includes('<svg'));
console.log('PASS: new score directly before historical ERP; 85% coverage, no missing-data fabrication and safe stale state');
