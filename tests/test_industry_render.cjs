/* Ten-year real rank-only PB cannot impersonate 3/5-year PB multiples. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
const order=['399975','399989','399971','399998','000807','399997','399986'];
const PB=new Set(['399975','399998','399986']);
let prev=html.indexOf('id="bse-panel"');
for(const code of order){
 const pos=html.indexOf('data-industry-code="'+code+'"');
 assert.ok(pos>prev,'sector section order '+code);
 prev=pos;
}
const script=fs.readFileSync('industry.js','utf8');
for(const p of ['p0','p10','p20','p50','p80','p90','p100'])assert.ok(script.includes("'"+p+"'"));
const events={};
const panels=Object.fromEntries(order.map(code=>{
 const node={dataset:{industryCode:code,metric:PB.has(code)?'PB':'PE-TTM'},_buttons:[]};
 for(const y of [3,5,10])node._buttons.push({
  dataset:{industryYears:String(y)},disabled:false,title:'',
  closest(sel){return sel==='[data-industry-code]'?node:null},
  classList:{toggle(){}},
  setAttribute(){},removeAttribute(attr){if(attr==='title')this.title='';}
 });
 node.querySelectorAll=()=>node._buttons;
 node.querySelector=function(selector){
  const target=this._nodes||(this._nodes={});
  return target[selector]||(target[selector]={
    innerHTML:'',textContent:'',className:'',querySelector(){return null}
  });
 };
 return [code,node];
}));
const document={
 addEventListener(k,fn){events[k]=fn},
 querySelector(sel){const match=sel.match(/industry-code="(\d+)"/);return panels[match?.[1]]||null}
};
const context={document,window:{},console,Date};
vm.runInNewContext(script,context);
const dates=[];let start=new Date('2014-01-03T00:00:00Z');
for(let i=0;i<670;i++){
 dates.push(new Date(start.getTime()+7*864e5*i).toISOString().slice(0,10));
}
const end=dates.at(-1);
const thresholds=(isRank,offset=0)=>Object.fromEntries(
 [0,10,20,50,80,90,100].map((n,i)=>['p'+n,isRank?n:(1.01+i*.20+offset)]));
const entries=order.map(code=>{
 const isPB=PB.has(code),actual=code==='399975',rankOnly=isPB&&!actual;
 const metric=isPB?'PB':'PE-TTM';
 const date=end;
 const points=dates.map((d,i)=>[d,rankOnly?i%100:actual?
  Number((1.2+i*.0007+Math.sin(i/30)*.3).toFixed(4)):
  Number((18+i*.019+Math.sin(i/29)*2.1).toFixed(4))]);
 const periods={};
 for(const yr of (rankOnly?[10]:[3,5,10])){
  periods[String(yr)]={
   ...thresholds(rankOnly,rankOnly?0:metric==='PE-TTM'?20:0),
   percentile:rankOnly?(code==='399998'?97.9:63.1):
     actual?(yr===3?15:yr===5?43:78):yr===3?55:yr===5?40:85,
   rankYears:rankOnly?10:yr,referenceDate:'2026-09-30',
   sampleCount:yr*50
  };
 }
 if(rankOnly)points[points.length-1][1]=periods['10'].percentile;
 return {code,name:code,valid:true,metric,
  pointMetric:actual?'PB_MULTIPLE':rankOnly?'PB_10Y_PERCENTILE':undefined,
  date,value:actual?1.62:rankOnly?(code==='399998'?1.85:.75):24.3,
  points,periods,source:rankOnly?'Verified 10y PB rank':actual?'Verified historical PB multiple':'CSI PE'};
});
context.window.renderIndustries({items:entries});
for(const code of order){
 const chart=panels[code]._nodes['.industry-chart'].innerHTML;
 assert.ok(chart.includes('<svg'),'chart '+code);
 assert.ok(chart.includes('<circle'),'current marker '+code);
 for(const p of ['0%','10%','20%','50%','80%','90%','100%']){
  assert.ok(panels[code]._nodes['.industry-legend'].innerHTML.includes(p),'reference '+p+' '+code);
 }
 if(code==='399975'){
  assert.ok(panels[code]._nodes['.industry-summary'].innerHTML.includes('近10年分位'));
  assert.ok(panels[code]._nodes['.industry-legend'].innerHTML.includes('倍'),
    'real PB multiple reference lines must show PB values');
  assert.ok(panels[code]._nodes['.industry-chart'].innerHTML.includes('90% · '),
    'right axis contains PB percentile and numeric reference value');
  assert.ok(panels[code]._buttons.every(b=>!b.disabled),'3/5/10 supported with raw PB');
 }else if(PB.has(code)){
  assert.ok(panels[code]._nodes['.industry-summary'].innerHTML.includes('PB近10年分位'));
  assert.ok(panels[code]._buttons[0].disabled&&panels[code]._buttons[1].disabled,
    'bank and coal must disable unsupported 3/5-year controls');
  assert.ok(!panels[code]._buttons[2].disabled);
  assert.ok(!panels[code]._nodes['.industry-legend'].innerHTML.includes('倍'),
    'rank-only reference lines must not be presented as PB multiples');
 }else{
  assert.ok(panels[code]._nodes['.industry-summary'].innerHTML.includes('PE-TTM'));
 }
}
const broker=panels['399975'];
function changeYear(code,n){
 const panel=panels[code],button=panel._buttons.find(b=>Number(b.dataset.industryYears)===n);
 events.click({target:{closest(selector){
  if(selector==='[data-industry-years]')return button;
  if(selector==='[data-industry-code]')return panel;
  return null;
 }}});
}
const before=broker._nodes['.industry-summary'].innerHTML;
changeYear('399975',3);
assert.ok(broker._nodes['.industry-summary'].innerHTML.includes('近3年分位'));
assert.ok(!broker._buttons[0].disabled);
changeYear('399975',5);
assert.ok(broker._nodes['.industry-summary'].innerHTML.includes('近5年分位'));
assert.notStrictEqual(broker._nodes['.industry-summary'].innerHTML,before);
changeYear('399975',10);
assert.ok(broker._nodes['.industry-summary'].innerHTML.includes('近10年分位'));
changeYear('399998',3);
assert.ok(panels['399998']._nodes['.industry-summary'].innerHTML.includes('PB近10年分位'),
 'unsupported coal 3-year selection must be ignored');
const invalid={items:entries.map(e=>PB.has(e.code)?{...e,metric:'PE-TTM'}:e)};
context.window.renderIndustries(invalid);
for(const code of PB){
 assert.ok(panels[code]._nodes['.industry-chart'].innerHTML.includes('暂无可核验的PB历史数据'),
  'old PE must not fill PB chart '+code);
}
console.log('PASS: all 7 charts; broker PB 3/5/10 dynamic; coal/bank unsupported-year controls disabled; no PB/PE substitution');
