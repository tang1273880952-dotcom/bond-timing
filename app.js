'use strict';
const names = {csi500:'中证500',bond10:'10年国债ETF',bond30:'30年国债ETF'};
const $ = x => document.getElementById(x);
const storageKey='bond-timing-positions-v1';
let latest=null, syncStatus=null, selected={}, expanded={};
let usLatest=null, usStatus=null;
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
    const open=Boolean(expanded[a.id]);
    const metrics=(a.metrics||[]).map(m=>'<div class="card-metric"><span>'+safe(m[0])+'</span><b>'+safe(m[1])+'</b></div>').join('');
    return '<article class="card decision-card" data-card="'+a.id+'" tabindex="0" aria-label="'+safe(a.name)+'：点击展开或收起判断依据">'+
    '<div class="asset-top"><h3>'+safe(a.name)+'</h3><span class="subrank">#'+(i+1)+'</span></div>'+
    '<div class="score">'+a.score+'<small>/100 · 买入估值分</small></div>'+
    '<div class="tag">'+grade(a.score)+'</div>'+
    '<div class="ownership" role="group" aria-label="'+safe(a.name)+'持仓状态"><button type="button" data-asset="'+a.id+'" data-held="false" class="'+(!held?'active':'')+'" aria-pressed="'+(!held)+'">未持有</button><button type="button" data-asset="'+a.id+'" data-held="true" class="'+(held?'active':'')+'" aria-pressed="'+held+'">已持有</button></div>'+
    '<div class="action '+tip.tone+'"><strong>'+tip.title+'</strong><p>'+tip.detail+'</p></div>'+
    '<button type="button" class="expand-trigger" data-expand="'+a.id+'" aria-expanded="'+open+'">'+(open?'收起判断依据 ▲':'点击查看判断依据 ▼')+'</button>'+
    (open?'<div class="card-metrics"><div class="mini-heading">指标明细 · '+safe(d.dataDate)+'</div>'+metrics+'<p>仅基于估值与收益率，不含你的真实持仓成本、ETF溢折价或经过回测的卖点。</p></div>':'')+
    '</article>';}).join('');
  const eligible=assets.filter(a=>a.score>=55);
  $('allocTitle').textContent=eligible.length===0?'当前估值没有明显新买优势':('新增资金可优先研究：'+eligible.map(a=>a.name).join('、'));
  $('bar').innerHTML='';
  $('allocation').textContent=eligible.length===0?'暂缓新增，不等于需要卖出已有持仓。':'不同资产的评分未进行跨资产回测校准，因此暂不自动分配资金比例。';
  $('details').innerHTML=assets.map(a=>'<h4>'+safe(a.name)+'</h4>'+(a.metrics||[]).map(m=>'<div class="item"><span>'+safe(m[0])+'</span><b>'+safe(m[1])+'</b></div>').join('')).join('');
}
$('cards').addEventListener('click',event=>{
  const btn=event.target.closest('button[data-asset]');
  if(btn){
    selected[btn.dataset.asset]=btn.dataset.held==='true';
    try{localStorage.setItem(storageKey,JSON.stringify(selected));}catch(e){}
    render();
    return;
  }
  const expandBtn=event.target.closest('[data-expand]');
  const card=event.target.closest('[data-card]');
  const id=expandBtn?expandBtn.dataset.expand:(card?card.dataset.card:null);
  if(!id)return;
  expanded[id]=!Boolean(expanded[id]);
  render();
});
$('cards').addEventListener('keydown',event=>{
  if(event.target.matches('[data-card]')&&(event.key==='Enter'||event.key===' ')){
    event.preventDefault();
    const id=event.target.dataset.card;
    expanded[id]=!Boolean(expanded[id]);
    render();
    const next=$('cards').querySelector('[data-card="'+id+'"]');
    if(next)next.focus();
  }
});
async function load() {
  const stamp=Date.now();
  const attempts=await Promise.allSettled([
    fetch('data/latest.json?'+stamp),fetch('data/status.json?'+stamp),
    fetch('data/us_latest.json?'+stamp),fetch('data/us_status.json?'+stamp)
  ]);
  async function get(i){
    if(attempts[i].status!=='fulfilled'||!attempts[i].value.ok)return null;
    try{return await attempts[i].value.json()}catch(e){return null}
  }
  latest=await get(0);syncStatus=await get(1);
  usLatest=await get(2);usStatus=await get(3);
  render();renderUS();
}
$('reload').onclick=load;
load();

function usDecision(asset,held){
  const s=asset.score,below=asset.trend==='below_10m',above=asset.trend==='above_10m',known=above||below;
  if(!held){
    if(s>=85&&below)return {title:'估值较低，但等趋势企稳',detail:'虽然风险溢价处于较有利区间，但月度指数价格低于近10个月均价；考虑等趋势改善或严格控制分批规模。',tone:'neutral'};
    if(s>=70)return {title:'关注分批买入',detail:'估值相对历史更有吸引力。'+(known?'同时检查中期趋势、分批金额与风险预算。':'暂缺有效价格趋势数据，不应据此判断最佳买点。'),tone:'positive'};
    if(s>=55)return {title:'小额观察，勿急于重仓',detail:'美股股债风险溢价尚未显示明显优势，可等待更好的风险补偿。',tone:'neutral'};
    return {title:'暂缓新增买入',detail:'标普500盈利收益率相对美国10年国债的吸引力较低。估值偏贵可以维持很久，不意味着马上会跌。',tone:'warning'};
  }
  if(s<=30&&below)return {title:'关注逐步减仓的条件',detail:'估值性价比偏低，且月度价格低于近10个月均价；应结合你的成本、仓位和投资期限评估减仓，不能机械清仓。',tone:'warning'};
  if(s<=40)return {title:'持有者关注止盈与仓位',detail:'估值风险相对偏高。'+(above?'月度价格仍高于近10个月均价，单凭估值不构成卖出确认。':'暂无足够的趋势确认。')+' 可检查仓位是否超出原定比例。',tone:'warning'};
  if(s>=70)return {title:'继续持有，观察趋势',detail:'历史估值相对有利，但市场可能继续波动。持仓风险、趋势和个人计划仍重要。',tone:'positive'};
  return {title:'持有观察',detail:'尚无仅凭估值就应卖出的依据。结合收益预期、仓位、成本及市场趋势再决定。',tone:'neutral'};
}
function renderUS(){
  const section=$('us-card'),meta=$('us-stamp');
  if(!section||!meta)return;
  const d=usLatest,status=usStatus;
  if(!d||d.mode!=='live'||d.id!=='sp500'||!Number.isFinite(d.score)){
    meta.textContent=(status&&status.success===false)?'美股数据尚未通过验证 · 上次错误已记录':'等待首次美股数据验证';
    section.innerHTML='<div class="us-empty">尚无核实的标普500股债比数据，暂不显示推测评分。'+(status&&status.success===false?' 云端数据源仍在检查。':'')+'</div>';
    return;
  }
  const held=Boolean(selected.sp500);
  const tip=usDecision(d,held);
  const open=Boolean(expanded.sp500);
  const trend=d.trend==='above_10m'?'月度指数高于近10个月均价':d.trend==='below_10m'?'月度指数低于近10个月均价':'月度价格趋势尚无可验证数据';
  meta.textContent='PE观测 '+d.valuationDate+' · 美债收益率 '+d.yieldDate+(status&&status.success===false?' · 最近更新失败，显示上次有效值':'');
  const metrics=(d.metrics||[]).map(m=>'<div class="card-metric"><span>'+safe(m[0])+'</span><b>'+safe(m[1])+'</b></div>').join('');
  section.innerHTML='<div class="us-card-main"><div><div class="us-score">'+d.score+'<small>/100 · 买入估值分</small></div><div class="us-result">'+grade(d.score)+'</div></div></div>'+
    '<div class="us-trend">'+safe(trend)+(d.priceDate?' · '+safe(d.priceDate):'')+'</div>'+
    '<div class="ownership" role="group" aria-label="标普500持仓状态"><button type="button" data-us-held="false" class="'+(!held?'active':'')+'" aria-pressed="'+(!held)+'">未持有</button><button type="button" data-us-held="true" class="'+(held?'active':'')+'" aria-pressed="'+held+'">已持有</button></div>'+
    '<div class="us-tip '+tip.tone+'"><strong>'+safe(tip.title)+'</strong><p>'+safe(tip.detail)+'</p></div>'+
    '<button type="button" data-us-expand="yes" class="expand-trigger" aria-expanded="'+open+'">'+(open?'收起美股数据 ▲':'展开美股股债比数据 ▼')+'</button>'+
    (open?'<div class="card-metrics">'+metrics+'</div>':'')+
    '<div class="us-observation">标普500PE为月度TTM口径，最新可能为估算；美债收益率目前也采用月度观测，不是当日10Y报价。风险溢价=100/PE−美债10Y。买入估值分不是卖出概率，策略未经回测。</div>'+
    '<div class="us-sources"><a href="https://www.multpl.com/s-p-500-pe-ratio/table/by-month" target="_blank" rel="noopener">PE来源</a><a href="https://www.multpl.com/10-year-treasury-rate/table/by-month" target="_blank" rel="noopener">美债月度来源</a><a href="https://www.multpl.com/s-p-500-historical-prices/table/by-month" target="_blank" rel="noopener">标普月度价格来源</a></div>';
}
const usSection=$('us-card');
if(usSection)usSection.addEventListener('click',event=>{
  const holding=event.target.closest('[data-us-held]');
  if(holding){
    selected.sp500=holding.dataset.usHeld==='true';
    try{localStorage.setItem(storageKey,JSON.stringify(selected))}catch(e){}
    renderUS();return;
  }
  if(event.target.closest('[data-us-expand]')){
    expanded.sp500=!Boolean(expanded.sp500);
    renderUS();
  }
});
