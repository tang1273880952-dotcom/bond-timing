/* Always-visible valuation index navigator and matching live status. */
(() => {
  'use strict';
  const nav=document.getElementById('valuation-jump');
  if(!nav)return;
  const charts=[
    {key:'csi500',target:'history-panel',kind:'erp',button:'data-history-years',fallback:10},
    {key:'star100',target:'star-panel',kind:'erp',button:'data-star-years',fallback:3},
    {key:'bse50',target:'bse-panel',kind:'erp',button:'data-bse-years',fallback:3},
    {key:'sp500',target:'sp500-panel',kind:'erp',button:'data-sp500-years',fallback:10},
    {key:'gold',target:'gold-panel',kind:'cost',button:'data-gold-years',fallback:5},
    ...['399975','399989','399971','399998','000807','399997','399986']
      .map(code=>({key:code,target:'industry-'+code,kind:'pe',
        button:'data-industry-years',fallback:3}))
  ];
  let current={market:null,industry:null,statuses:null,gold:null,us:null};
  const pctValid=v=>typeof v==='number'&&Number.isFinite(v)&&v>=0&&v<=100;
  function selectedYears(chart){
    const active=document.querySelector(
      '#'+chart.target+' ['+chart.button+'][aria-pressed="true"]');
    const n=Number(active?.getAttribute(chart.button)||
      active?.dataset?.[chart.button.replace(/-([a-z])/g,(_,l)=>l.toUpperCase())]);
    return [1,3,5,10].includes(n)?n:chart.fallback;
  }
  function lookup(chart){
    const market=current.market,industries=current.industry;
    if(chart.key==='sp500'){
      const data=current.us?.history;
      return {period:data?.periods?.[String(selectedYears(chart))],date:data?.date,
        valid:current.us?.mode==='live'&&data?.valid===true&&data?.id==='sp500'};
    }
    if(chart.key==='csi500'){
      const data=market?.history?.series?.csi500;
      return {period:data?.periods?.[String(selectedYears(chart))],date:data?.date,
        valid:market?.mode==='live'&&Boolean(data)};
    }
    if(chart.key==='star100'||chart.key==='bse50'){
      const data=market?.[chart.key];
      return {period:data?.periods?.[String(selectedYears(chart))],date:data?.valuationDate||data?.date,
        valid:data?.valid===true};
    }
    const data=industries?.items?.find(x=>x.code===chart.key);
    const expectsPB=['399975','399998','399986'].includes(chart.key);
    const verified=expectsPB?(data?.metric==='PB'&&
      ['PB_MULTIPLE','PB_10Y_PERCENTILE'].includes(data?.pointMetric)):
      data?.metric==='PE-TTM';
    return {period:data?.periods?.[String(selectedYears(chart))],date:data?.date,
      isPB:expectsPB,valid:data?.valid===true&&verified};
  }
  function status(percentile,kind){
    // ERP is inverse to PE: a higher ERP percentile means cheaper.
    const cheap=kind==='pe'?percentile:100-percentile;
    if(cheap<=20)return ['低估','cheap'];
    if(cheap<=40)return ['偏低','watch'];
    if(cheap<60)return ['中性','neutral'];
    if(cheap<80)return ['偏高','caution'];
    return ['高估','rich'];
  }
  function render(){
    for(const chart of charts){
      const chip=document.querySelector('[data-valuation-status="'+chart.key+'"]');
      if(!chip)continue;
      if(chart.kind==='cost'){
        const gold=current.gold;
        const valid=gold?.valid===true&&gold.quoteType==='spot'&&Number.isFinite(gold.ratio)&&gold.ratio>0;
        const sync=current.statuses?.gold;
        const health=typeof window.dataHealth==='function'&&current.statuses?
          window.dataHealth(gold?.priceDate,sync):{ok:true};
        if(!valid||!health.ok||gold?.costStale||sync?.costCheckSuccess===false){
          chip.textContent=valid?'待更新':'暂无';chip.dataset.tone='unknown';
          chip.title=valid?(health.label||'公开成本需核验'):'暂无可核验的黄金成本参考';
        }else{
          const tone=gold.classification?.tone;
          chip.dataset.tone=['cheap','watch','neutral','caution','rich'].includes(tone)?tone:'neutral';
          chip.textContent=gold.ratio.toFixed(2)+'× AISC';
          chip.title='黄金成本溢价：'+(gold.classification?.label||'参考')+' · '+gold.priceDate+
            ' · 公开AISC '+gold.costPeriod+'；非历史分位';
        }
        continue;
      }
      const {period,date,valid,isPB}=lookup(chart);
      const p=period?.percentile;
      if(!valid||!pctValid(p)){
        chip.textContent='暂无';
        chip.dataset.tone='unknown';
        chip.title='当前选定年限暂无有效估值分位';
        continue;
      }
      if(current.statuses&&typeof window.dataHealth==='function'){
        const industry=chart.kind==='pe';
        let sync=chart.key==='sp500'?current.statuses.us:
          industry?current.statuses.industry:current.statuses.market;
        if(industry&&sync&&typeof sync.success==='boolean')
          sync={...sync,success:!Boolean(sync.errors?.[chart.key])};
        const health=window.dataHealth(date,sync,chart.key==='sp500'?45:10);
        if(!health.ok){
          chip.textContent='待更新';
          chip.dataset.tone='unknown';
          chip.title=health.label+' · 历史数据 '+(date||'待核对');
          continue;
        }
      }
      const [name,tone]=status(p,chart.kind);
      chip.dataset.tone=tone;
      chip.textContent=name+' · '+Math.round(p)+'%';
      const pbItem=isPB?current.industry?.items?.find(x=>x.code===chart.key):null;
      const truePbYears=pbItem?.pointMetric==='PB_MULTIPLE';
      chip.title=(isPB?(truePbYears?'近'+selectedYears(chart)+'年真实PB分位 '+p.toFixed(1)+'%':
        'PB仅有近10年分位 '+p.toFixed(1)+'%（3/5年暂无真实PB倍数）'):
        '近'+selectedYears(chart)+'年历史分位 '+p.toFixed(1)+'%')+' · 数据 '+(date||'待核对')+
        (isPB?' · PB越低越便宜':chart.kind==='erp'?' · ERP越高越便宜':' · PE越低越便宜');
    }
  }
  // Highlight the chart occupying the reading area, not the hovered tab.
  // The probe is placed below the fixed navigation to avoid selecting the
  // next chart simply because a small part appears at the screen bottom.
  const tabs=charts.map(chart=>({
    target:chart.target,
    link:nav.querySelector('a[href="#'+chart.target+'"]'),
    section:document.getElementById(chart.target)
  })).filter(item=>item.link&&item.section);
  let selected=null;
  function selectChart(target){
    if(selected===target)return;
    selected=target;
    for(const item of tabs){
      const active=item.target===target;
      item.link.classList.toggle('is-current',active);
      if(active)item.link.setAttribute('aria-current','location');
      else item.link.removeAttribute('aria-current');
    }
  }
  function trackVisibleChart(){
    const navBottom=Math.max(0,nav.getBoundingClientRect().bottom);
    const viewportHeight=window.innerHeight||800;
    const probe=Math.min(viewportHeight-20,
      navBottom+Math.min(180,Math.max(80,viewportHeight*0.20)));
    let target=null;
    for(const item of tabs){
      const rect=item.section.getBoundingClientRect();
      if(rect.top<=probe&&rect.bottom>navBottom+8)target=item.target;
    }
    selectChart(target);
  }
  let framePending=false;
  function onViewportChange(){
    if(framePending)return;
    framePending=true;
    window.requestAnimationFrame(()=>{
      framePending=false;
      trackVisibleChart();
    });
  }
  window.addEventListener('scroll',onViewportChange,{passive:true});
  window.addEventListener('resize',onViewportChange);
  window.addEventListener('hashchange',onViewportChange);
  nav.addEventListener('click',event=>{
    const link=event.target.closest('a[href^="#"]');
    if(link&&tabs.some(item=>item.link===link))selectChart(link.getAttribute('href').slice(1));
  });
  document.addEventListener('click',event=>{
    const range=event.target.closest(
      '[data-history-years],[data-star-years],[data-bse-years],[data-sp500-years],[data-industry-years],[data-gold-years]');
    if(range)render();
  });
  window.updateValuationJump=(market,industry,statuses,gold,us)=>{
    current={market,industry,statuses,gold,us};
    render();
  };
  render();
  onViewportChange();
})();
