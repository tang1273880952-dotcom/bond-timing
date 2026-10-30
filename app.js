'use strict';
const names = {csi500:'中证500',bond10:'10年国债ETF',bond30:'30年国债ETF'};
const $ = x => document.getElementById(x);
const storageKey='bond-timing-positions-v1';
let latest=null, syncStatus=null, selected={}, expanded={};
let usLatest=null, usStatus=null;
try { selected=JSON.parse(localStorage.getItem(storageKey)||'{}')||{}; } catch(e) {selected={};}

function dataHealth(date,status,maxDataDays=10){
  const now=Date.now(),day=86400000;
  const observed=Date.parse(String(date||'').slice(0,10)+'T00:00:00+08:00');
  const attempt=Date.parse(status?.attemptAt||'');
  if(!Number.isFinite(observed)||observed>now+day)
    return {ok:false,label:'数据日期待核验'};
  if(now-observed>maxDataDays*day)
    return {ok:false,label:'数据较旧，暂作历史参考'};
  if(!Number.isFinite(attempt)||attempt>now+day)
    return {ok:false,label:'更新状态待核验'};
  if(now-attempt>4*day)
    return {ok:false,label:'多日未更新，暂作历史参考'};
  if(status?.success===false)
    return {ok:false,label:'更新失败，沿用旧数据'};
  if(status?.success!==true)
    return {ok:false,label:'更新状态待核验'};
  return {ok:true,label:''};
}
window.dataHealth=dataHealth;

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
function scoreTone(n){
  return n>=70?'cheap':n>=55?'watch':n>=40?'neutral':n>=25?'caution':'rich';
}
function scoreText(n){
  return n>=85?'明显偏低估':n>=70?'相对低估':n>=55?'略偏低估':
    n>=40?'中性':n>=25?'偏高估':'相对高估';
}
function render() {
  const d=latest,st=syncStatus;
  if(!d||d.mode!=='live'||!Array.isArray(d.assets)||d.assets.length!==3){
    $('stamp').textContent='数据暂不可用';
    $('pick').textContent='等待行情';
    $('reason').textContent='暂不显示未经核验的估值';
    $('cards').innerHTML='';
    return;
  }
  const byId=Object.fromEntries(d.assets.map(a=>[a.id,a]));
  const assets=['csi500','bond10','bond30'].map(id=>byId[id]).filter(Boolean);
  const health=dataHealth(d.dataDate,st);
  const usHealth=dataHealth(usLatest?.valuationDate,usStatus,45);
  $('stamp').textContent='数据 '+safe(d.dataDate)+(health.ok?'':' · '+health.label);
  $('stamp').classList.toggle('data-warning',!health.ok);
  const individuallyCheap=[...(health.ok?assets:[]),
    (usHealth.ok&&usLatest?.mode==='live'&&Number.isFinite(usLatest.score))?usLatest:null]
    .filter(a=>a&&a.score>=70);
  $('pick').textContent=individuallyCheap.length?
    '低估参考：'+individuallyCheap.map(a=>a.name).join('、'):'暂无明显低估信号';
  $('reason').textContent=(!health.ok||!usHealth.ok)?
    '更新异常或日期较旧的数据只作历史参考，不参与新增资金观察。':
    '仅按各自历史估值观察，不代表跨资产收益排名或买入指令。';
  $('cards').innerHTML=assets.map(a=>{
    const tone=scoreTone(a.score),open=Boolean(expanded[a.id]),held=Boolean(selected[a.id]);
    const first=(a.metrics||[])[0];
    const tip=advice(a,held);
    return '<article class="card decision-card compact-asset tone-'+tone+'" data-card="'+safe(a.id)+
      '" tabindex="0" aria-label="'+safe(a.name)+'，查看估值指标">'+
      '<div class="asset-top"><h3>'+safe(a.name)+'</h3></div>'+
      '<div class="score-line"><strong class="score-value">'+safe(a.score)+'</strong><span class="score-unit">/100 · 估值分</span></div>'+
      '<div class="valuation-status">'+scoreText(a.score)+'</div>'+
      (first?'<div class="asset-main-metric"><span>'+safe(first[0])+'</span><b>'+safe(first[1])+'</b></div>':'')+
      (a.id==='csi500'?'<p class="asset-footnote" title="概览使用乐咕乐股PE/PB；历史曲线使用中证指数官方PE，两者可略有差异">PE / PB / ERP · 源不同</p>':
        '<p class="asset-footnote">国债收益率代理 · 非ETF价格</p>')+
      '<button type="button" class="expand-trigger" data-expand="'+safe(a.id)+
        '" aria-expanded="'+open+'">'+(open?'收起详情 −':'查看指标 +')+'</button>'+
      (open?'<div class="card-metrics">'+(a.metrics||[]).map(m=>
        '<div class="card-metric"><span>'+safe(m[0])+'</span><b>'+safe(m[1])+'</b></div>').join('')+
        '<div class="ownership" role="group" aria-label="持仓状态"><button type="button" data-asset="'+safe(a.id)+
        '" data-held="false" class="'+(!held?'active':'')+'" aria-pressed="'+!held+'">未持有</button>'+
        '<button type="button" data-asset="'+safe(a.id)+'" data-held="true" class="'+(held?'active':'')+
        '" aria-pressed="'+held+'">已持有</button></div>'+
        '<p class="compact-advice">'+safe(tip.title)+' · '+safe(tip.detail)+'</p></div>':'')+
      '</article>';
  }).join('');
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
    fetch('data/us_latest.json?'+stamp),fetch('data/us_status.json?'+stamp),
    fetch('data/industry_latest.json?'+stamp),
    fetch('data/industry_status.json?'+stamp)
  ]);
  async function get(i){
    if(attempts[i].status!=='fulfilled'||!attempts[i].value.ok)return null;
    try{return await attempts[i].value.json()}catch(e){return null}
  }
  latest=await get(0);syncStatus=await get(1);
  usLatest=await get(2);usStatus=await get(3);
  render();renderUS();if(window.renderHistory)window.renderHistory(latest&&latest.history);if(window.renderBSE50)window.renderBSE50(latest&&latest.bse50);if(window.renderSTAR100)window.renderSTAR100(latest&&latest.star100);
  const industryData=await get(4);
  const industryStatus=await get(5);
  if(window.renderIndustries)window.renderIndustries(industryData,industryStatus);
  if(window.updateValuationJump)window.updateValuationJump(latest,industryData,
    {market:syncStatus,industry:industryStatus});
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
  const panel=$('us-section');
  if(!d||d.mode!=='live'||d.id!=='sp500'||!Number.isFinite(d.score)){
    panel.className='panel us-panel overview-card tone-neutral';
    meta.textContent='等待有效数据';
    section.innerHTML='<p class="us-empty">美股估值暂不可用</p>';
    return;
  }
  const tone=scoreTone(d.score),held=Boolean(selected.sp500),open=Boolean(expanded.sp500);
  panel.className='panel us-panel overview-card tone-'+tone;
  const metrics=(d.metrics||[]).map(m=>
    '<div class="card-metric"><span>'+safe(m[0])+'</span><b>'+safe(m[1])+'</b></div>').join('');
  const erp=(d.metrics||[]).find(m=>String(m[0]).includes('风险溢价（盈利收益率')) || (d.metrics||[])[2];
  const health=dataHealth(d.valuationDate,status,45);
  meta.textContent='数据 '+safe(d.valuationDate)+(d.estimatedPE?' · PE估算':'')+
    (health.ok?'':' · '+health.label);
  meta.classList.toggle('data-warning',!health.ok);
  const tip=usDecision(d,held);
  section.innerHTML=
    '<div class="score-line"><strong class="score-value">'+safe(d.score)+
    '</strong><span class="score-unit">/100 · 估值分</span></div>'+
    '<div class="valuation-status">'+scoreText(d.score)+'</div>'+
    (erp?'<div class="asset-main-metric"><span>股债风险溢价</span><b>'+safe(erp[1])+'</b></div>':'')+
    '<p class="asset-footnote">美国10年国债 · 月度PE'+(d.estimatedPE?'估算':'')+'</p>'+
    '<button type="button" class="expand-trigger" data-us-expand="yes" aria-expanded="'+open+'">'+
    (open?'收起详情 −':'查看指标 +')+'</button>'+
    (open?'<div class="card-metrics">'+metrics+
      '<div class="ownership" role="group" aria-label="标普500持仓状态">'+
      '<button type="button" data-us-held="false" class="'+(!held?'active':'')+
      '" aria-pressed="'+!held+'">未持有</button><button type="button" data-us-held="true" class="'+
      (held?'active':'')+'" aria-pressed="'+held+'">已持有</button></div>'+
      '<p class="compact-advice">'+safe(tip.title)+' · '+safe(tip.detail)+'</p>'+
      '<p class="compact-advice">美股PE可能为估算，未结合ETF实际交易价格。</p></div>':'');
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
