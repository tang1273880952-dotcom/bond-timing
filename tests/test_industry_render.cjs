/* Seven new charts appear only after BSE50, with correct percentiles. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('index.html','utf8');
const order=['399975','399989','399971','399998','000807','399997','399986'];
let prev=html.indexOf('id="bse-panel"');
assert.ok(prev>0);
for(const code of order){
  const pos=html.indexOf('data-industry-code="'+code+'"');
  assert.ok(pos>prev,'sector section order '+code);prev=pos;
}
const script=fs.readFileSync('industry.js','utf8');
for(const p of ['p0','p10','p20','p50','p80','p90','p100']) assert.ok(script.includes("'"+p+"'"));
const panels=Object.fromEntries(order.map(code=>[code,{
  dataset:{industryCode:code,metric:['399975','399998','399986'].includes(code)?'PB':'PE-TTM'},
  querySelectorAll:()=>[],
  querySelector(selector){
    const target=this._nodes||(this._nodes={});
    return target[selector]||(target[selector]={
      innerHTML:'',textContent:'',className:'',querySelector(){return null}
    });
  }
}]));
const document={
  addEventListener(){},
  querySelector(s){const match=s.match(/industry-code="(\d+)"/);return panels[match?.[1]]||null}
};
const context={document,window:{},console,Date};
vm.runInNewContext(script,context);
const dates=[];let day=new Date('2023-01-06T00:00:00Z');
for(let i=0;i<190;i++){dates.push([day.toISOString().slice(0,10),20+i/10]);day.setUTCDate(day.getUTCDate()+7);}
const PB_CODES=new Set(['399975','399998','399986']);
const data={items:order.map(code=>{
  const isPB=PB_CODES.has(code);
  return {code,name:code,valid:true,metric:isPB?'PB':'PE-TTM',
    pointMetric:isPB?'PB_10Y_PERCENTILE':undefined,
    date:dates[dates.length-1][0],value:isPB?1.22:38.9,source:isPB?'PB public weekly rank':'CSI PE',
    points:isPB?dates.map((p,i)=>[p[0],i%100]):dates,
    periods:{'3':isPB?
      {p0:0,p10:10,p20:20,p50:50,p80:80,p90:90,p100:100,rankYears:10,
        percentile:18,referenceDate:dates.at(-1)[0],sampleCount:160}:
      {p0:18,p10:20,p20:23,p50:30,p80:35,p90:40,p100:42,percentile:77,
        referenceDate:'2026-08-31',sampleCount:760}}};
}});
context.window.renderIndustries(data);
for(const code of order){
  assert.ok(panels[code]._nodes['.industry-chart'].innerHTML.includes('<svg'),'actual plot '+code);
  assert.ok(panels[code]._nodes['.industry-chart'].innerHTML.includes('circle'),'current point '+code);
  if(PB_CODES.has(code)){
    assert.ok(panels[code]._nodes['.industry-summary'].innerHTML.includes('当前PB'));
    assert.ok(!panels[code]._nodes['.industry-summary'].innerHTML.includes('PE-TTM'));
    assert.ok(panels[code]._nodes['.industry-note'].textContent.includes('近3年走势'));
  }
  for(const p of ['0%','10%','20%','50%','80%','90%','100%'])assert.ok(panels[code]._nodes['.industry-legend'].innerHTML.includes(p));
}
context.window.renderIndustries({items:order.map(code=>PB_CODES.has(code)?
  {...data.items.find(x=>x.code===code),metric:'PE-TTM'}:data.items.find(x=>x.code===code))});
for(const code of PB_CODES){
  assert.ok(panels[code]._nodes['.industry-chart'].innerHTML.includes('暂无可核验的PB历史数据'),
    'PB-only charts must never silently substitute PE '+code);
}
console.log('PASS: three genuine PB percentile charts and four PE charts, with no substitution');
