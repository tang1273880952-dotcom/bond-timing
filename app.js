'use strict';
const names = {csi500:'中证500',bond10:'10年国债ETF',bond30:'30年国债ETF'};
const $ = x => document.getElementById(x);
const storageKey='bond-timing-positions-v1';
let latest=null, syncStatus=null, selected={};
try { selected=JSON.parse(localStorage.getItem(storageKey)||'{}')||{}; } catch(e) {selected={};}

function grade(n) {
  if (n>=85) return '历史低估区';
  if (n>=70) return '估值较有吸引力';
  if (n>=55) return '可观察分批';
  if (n>=40) return '一般 / 观察';
  if (n>=25) return '估值偏贵';
  return '历史偏贵区';
}
function advice(a, held) {
  const s=a.score, bond=a.id!=='csi500';
  if (!held) {
    if(s>=85) return {title:'分批买入观察',detail:bond?'历史收益率位置较有利；下单前仍需核对ETF折溢价、成交价与久期风险。':'历史估值吸引力较高；适合评估分批计划，不保证见底。',tone:'positive'};
    if(s>=70) return {title:'可以考虑分批',detail:bond?'收益率相对历史较有吸引力，但需确认ETF折溢价和利率方向。':'估值较有吸引力，建议按计划分批而非一次买满。',tone:'positive'};
    if(s>=55) return {title:'谨慎小额观察',detail:'估值优势不突出；如配置需求明确，可结合风险预算少量分批。',tone:'neutral'};
    return {title:'暂缓新买',detail:bond?'当前国债收益率处于偏低历史区间，追高长期债券的风险收益比不理想。':'当前估值模型没有显示足够的买入优势。',tone:'warning'};
  }
  if(s>=70) return {title:'持有观察',detail:'估值位置尚未触发止盈观察；仍应检查仓位集中度和投资期限。',tone:'positive'};
  if(s>=40) return {title:'继续持有，观察变化',detail:'单看历史估值尚不足以决定卖出；关注未来趋势和原定持仓计划。',tone:'neutral'};
  if (bond) return {title:'关注减仓 / 止盈条件',detail:(a.id==='bond30'?'30年债久期风险尤其大。':'')+'目前收益率处历史偏低区域，但不等于马上下跌；需要结合仓位、利率趋势、成本和ETF折溢价，才能决定是否卖出。',tone:'warning'};
  return {title:'评估是否逐步减仓',detail:'估值偏贵不等于顶部。先核对盈利预期、持仓比例及趋势，再评估是否兑现部分收益。',tone:'warning'};
}
function safe(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function render() {
  const d=latest, st=syncStatus;
  if(!d||d.mode!=='live'||!Array.isArray(d.assets)||d.assets.length!==3){
    $('stamp').textContent='尚无有效市场数据 · 等待首次云端同步';
    $('cards').innerHTML='';return;
  }
  const assets=[...d.assets].sort((a,b)=>b.score-a.score);
  const top=assets[0];
  $('stamp').textContent='市场日期 '+d.dataDate+' · '+(st&&st.success===false?'最近同步失败，使用上次有效数据':'云端估值已更新');
  $('pick').textContent=top.score<55?'新增资金：等待 / 现金':'新增资金：关注'+top.name;
  $('reason').textContent=top.score<55?'三类资产都未达到新增资金的估值门槛；这不等于必须卖掉已有仓位。':(top.score-assets[1].score>=15?'新增资金的估值性价比明显偏向'+top.name+'。':'新增资金可优先研究'+top.name+'，仍应比较风险和资产配置。');
  $('cards').innerHTML=assets.map((a,i)=>{
    const held=Boolean(selected[a.id]);const tip=advice(a,held);
    return '<article class="card decision-card"><div class="asset-top"><h3>'+safe(a.name)+'</h3><span class="subrank">#'+(i+1)+'</span></div>'+
    '<div class="score">'+a.score+'<small>/100 · 买入估值分</small></div>'+
    '<div class="tag">'+grade(a.score)+'</div>'+
    '<div class="ownership" role="group" aria-label="'+safe(a.name)+'持仓状态"><button type="button" data-asset="'+a.id+'" data-held="false" class="'+(!held?'active':'')+'">未持有</button><button type="button" data-asset="'+a.id+'" data-held="true" class="'+(held?'active':'')+'">已持有</button></div>'+
    '<div class="action '+tip.tone+'"><strong>'+tip.title+'</strong><p>'+tip.detail+'</p></div></article>';}).join('');
  const eligible=assets.filter(a=>a.score>=55);
  $('allocTitle').textContent=eligible.length===0?'当前估值没有明显新买优势':('新增资金可优先研究：'+eligible.map(a=>a.name).join('、'));
  $('bar').innerHTML='';
  $('allocation').textContent=eligible.length===0?'暂缓新增，不等于需要卖出已有持仓。':'不同资产的评分未进行跨资产回测校准，因此暂不自动分配资金比例。';
  $('details').innerHTML=assets.map(a=>'<h4>'+safe(a.name)+'</h4>'+(a.metrics||[]).map(m=>'<div class="item"><span>'+safe(m[0])+'</span><b>'+safe(m[1])+'</b></div>').join('')).join('');
}
$('cards').addEventListener('click',event=>{
  const btn=event.target.closest('button[data-asset]');if(!btn)return;
  selected[btn.dataset.asset]=btn.dataset.held==='true';
  try{localStorage.setItem(storageKey,JSON.stringify(selected));}catch(e){}
  render();
});
async function load() {
  try{
    const [a,b]=await Promise.all([fetch('data/latest.json?'+Date.now()),fetch('data/status.json?'+Date.now())]);
    latest=a.ok?await a.json():null;syncStatus=b.ok?await b.json():null;render();
  }catch(e){$('stamp').textContent='云端数据加载失败：'+e.message;}
}
$('reload').onclick=load;
load();