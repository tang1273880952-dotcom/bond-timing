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
for(const p of ['p10','p20','p50','p80','p90']) assert.ok(script.includes("'"+p+"'"));
const panels=Object.fromEntries(order.map(code=>[code,{
  dataset:{industryCode:code,metric:'PE-TTM'},
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
const data={items:order.map(code=>({code,name:code,valid:true,metric:'PE-TTM',
  date:dates[dates.length-1][0],value:38.9,source:'CSI',points:dates,
  periods:{'3':{p10:20,p20:23,p50:30,p80:35,p90:40,percentile:77,
    referenceDate:'2026-08-31',sampleCount:760}}}))};
context.window.renderIndustries(data);
for(const code of order){
  assert.ok(panels[code]._nodes['.industry-chart'].innerHTML.includes('<svg'),'actual plot '+code);
  assert.ok(panels[code]._nodes['.industry-chart'].innerHTML.includes('circle'),'current point '+code);
  for(const p of ['10%','20%','50%','80%','90%'])assert.ok(panels[code]._nodes['.industry-legend'].innerHTML.includes(p));
}
console.log('PASS: seven industry charts and all five percentile lines');
