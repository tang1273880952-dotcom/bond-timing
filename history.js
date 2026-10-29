/* Lightweight chart for historical ERP/sovereign yields; not ETF prices. */
(() => {
'use strict';
const assetNames={csi500:'中证500 · 股债风险溢价',bond10:'中国10年国债收益率',bond30:'中国30年国债收益率'};
const state={asset:'csi500',years:10};
let stored=null;
const el=id=>document.getElementById(id);
const pct=(n,d=2)=>Number(n).toFixed(d)+'%';
const ts=x=>Date.parse(String(x)+'T00:00:00Z');
const root=el('history-panel');
if(!root)return;
root.addEventListener('click',e=>{
 const a=e.target.closest('[data-history-asset]'),y=e.target.closest('[data-history-years]');
 if(a&&Object.prototype.hasOwnProperty.call(assetNames,a.dataset.historyAsset))state.asset=a.dataset.historyAsset;
 else if(y&&[3,5,10].includes(Number(y.dataset.historyYears)))state.years=Number(y.dataset.historyYears);
 else return;
 render(stored);
});
function render(data){
 stored=data;
 root.querySelectorAll('[data-history-asset]').forEach(b=>{
  const selected=b.dataset.historyAsset===state.asset;
  b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));
 });
 root.querySelectorAll('[data-history-years]').forEach(b=>{
  const selected=Number(b.dataset.historyYears)===state.years;
  b.classList.toggle('active',selected);b.setAttribute('aria-pressed',String(selected));
 });
 const chart=el('history-chart'),info=el('history-summary'),note=el('history-note');
 const d=data?.series?.[state.asset];
 if(!d||!Array.isArray(d.points)||d.points.length<12){
  chart.innerHTML='<div class="history-empty">历史数据尚未生成，等待下一次估值更新。</div>';
  info.textContent='历史数据待同步';
  note.textContent='不会用模拟数据代替真实历史走势。';
  return;
 }
 const end=ts(d.date),start=new Date(end);
 if(!Number.isFinite(end)){chart.innerHTML='<div class="history-empty">数据日期异常。</div>';return;}
 start.setUTCFullYear(start.getUTCFullYear()-state.years);
 const pts=d.points.map(row=>({date:String(row[0]),t:ts(row[0]),v:Number(row[1])}))
  .filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.v)&&p.t>=start.getTime()&&p.t<=end).sort((a,b)=>a.t-b.t);
 const low=Number(d.p20),high=Number(d.p80);
 if(pts.length<6||!Number.isFinite(low)||!Number.isFinite(high)){
  chart.innerHTML='<div class="history-empty">该时间范围的有效历史数据不足。</div>';
  info.textContent='历史数据不足';return;
 }
 info.textContent=assetNames[state.asset]+'：'+pct(d.latest,state.asset==='csi500'?2:3)+' · '+d.date;
 note.textContent='虚线：近10年日度数据的20% / 80%分位（'+pct(low)+' / '+pct(high)+'）。指标越高通常越值得研究，但不等于ETF买点。';
 const W=850,H=254,L=54,R=20,T=19,B=35,xspan=W-L-R,yspan=H-T-B;
 const left=pts[0].t,right=pts[pts.length-1].t;
 const startV=Math.min(...pts.map(p=>p.v),low,high),endV=Math.max(...pts.map(p=>p.v),low,high),padding=Math.max(.06,(endV-startV)*.1);
 const min=startV-padding,max=endV+padding;
 const x=p=>L+(p.t-left)/Math.max(1,right-left)*xspan;
 const y=v=>T+(max-v)/Math.max(.001,max-min)*yspan;
 const path=pts.map((p,i)=>(i?'L':'M')+x(p).toFixed(2)+' '+y(p.v).toFixed(2)).join(' ');
 let svg='<svg class="history-svg" id="history-svg" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="'+assetNames[state.asset]+'历史值">';
 for(let i=0;i<=4;i++){
  const v=min+(max-min)*i/4,yp=y(v);
  svg+='<line x1="'+L+'" y1="'+yp+'" x2="'+(W-R)+'" y2="'+yp+'" stroke="#e5ebf4"/><text x="'+(L-8)+'" y="'+(yp+4)+'" text-anchor="end" font-size="11" fill="#8292aa">'+v.toFixed(2)+'</text>';
 }
 for(const [val,color] of [[low,'#b98c5c'],[high,'#259673']])
  svg+='<line x1="'+L+'" y1="'+y(val)+'" x2="'+(W-R)+'" y2="'+y(val)+'" stroke="'+color+'" stroke-width="1.3" stroke-dasharray="6 5"/>';
 svg+='<path d="'+path+'" fill="none" stroke="#3769d2" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>';
 const last=pts[pts.length-1];
 svg+='<circle cx="'+x(last)+'" cy="'+y(last.v)+'" r="4.5" stroke="white" stroke-width="2" fill="#3769d2"/>';
 svg+='<line id="history-guide" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+'" stroke="#889cb9" stroke-dasharray="3 3" visibility="hidden"/>';
 svg+='<circle id="history-dot" cx="0" cy="0" r="5" fill="#3769d2" stroke="white" stroke-width="2" visibility="hidden"/>';
 svg+='<rect x="'+L+'" y="'+T+'" width="'+xspan+'" height="'+yspan+'" fill="transparent"/>';
 svg+='<text x="'+L+'" y="'+(H-8)+'" font-size="11" fill="#8191a7">'+pts[0].date.slice(0,7)+'</text>';
 svg+='<text x="'+(W-R)+'" y="'+(H-8)+'" text-anchor="end" font-size="11" fill="#8191a7">'+last.date.slice(0,7)+'</text></svg>';
 chart.innerHTML=svg;
 const svgNode=el('history-svg'),hover=el('history-hover');
 hover.textContent='悬停曲线查看历史日期和数值';
 svgNode.addEventListener('pointermove',e=>{
  const rect=svgNode.getBoundingClientRect();
  if(!rect.width)return;
  const px=(e.clientX-rect.left)*W/rect.width;
  if(px<L||px>W-R)return;
  const target=left+(px-L)/xspan*(right-left);
  let pick=pts[0],distance=Infinity;
  for(const p of pts){const diff=Math.abs(p.t-target);if(diff<distance){distance=diff;pick=p;}}
  const pos=x(pick);
  const line=el('history-guide'),dot=el('history-dot');
  line.setAttribute('x1',pos);line.setAttribute('x2',pos);line.setAttribute('visibility','visible');
  dot.setAttribute('cx',pos);dot.setAttribute('cy',y(pick.v));dot.setAttribute('visibility','visible');
  hover.textContent=pick.date+' · '+pct(pick.v,state.asset==='csi500'?2:3);
 });
 svgNode.addEventListener('pointerleave',()=>{
  el('history-guide')?.setAttribute('visibility','hidden');
  el('history-dot')?.setAttribute('visibility','hidden');
 });
}
window.renderHistory=render;
})();
