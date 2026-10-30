/* Always-visible valuation index navigator and matching live status. */
(() => {
  'use strict';
  const nav=document.getElementById('valuation-jump');
  if(!nav)return;
  const charts=[
    {key:'winda',target:'winda-panel',kind:'erp',button:'data-winda-years',fallback:10},
    {key:'csi500',target:'history-panel',kind:'erp',button:'data-history-years',fallback:10},
    {key:'star100',target:'star-panel',kind:'erp',button:'data-star-years',fallback:3},
    {key:'bse50',target:'bse-panel',kind:'erp',button:'data-bse-years',fallback:3},
    ...['399975','399989','399971','399998','000807','399997','399986']
      .map(code=>({key:code,target:'industry-'+code,kind:'pe',
        button:'data-industry-years',fallback:3}))
  ];
  let current={market:null,industry:null,winda:null};
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
    if(chart.key==='winda'){
      const data=current.winda;
      return {period:data?.periods?.[String(selectedYears(chart))],date:data?.date,
        valid:data?.valid===true&&data?.code==='881001.WI'};
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
    return {period:data?.periods?.[String(selectedYears(chart))],date:data?.date,
      valid:data?.valid===true&&data?.metric==='PE-TTM'};
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
      const {period,date,valid}=lookup(chart);
      const p=period?.percentile;
      if(!valid||!pctValid(p)){
        chip.textContent='暂无';
        chip.dataset.tone='unknown';
        chip.title='当前选定年限暂无有效估值分位';
        continue;
      }
      const [name,tone]=status(p,chart.kind);
      chip.dataset.tone=tone;
      chip.textContent=name+' · '+Math.round(p)+'%';
      chip.title='近'+selectedYears(chart)+'年历史分位 '+p.toFixed(1)+'% · 数据 '+(date||'待核对')+
        (chart.kind==='erp'?' · ERP越高越便宜':' · PE越低越便宜');
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
      '[data-winda-years],[data-history-years],[data-star-years],[data-bse-years],[data-industry-years]');
    if(range)render();
  });
  window.updateValuationJump=(market,industry,winda)=>{
    current={market,industry,winda};
    render();
  };
  window.refreshValuationJump=render;
  render();
  onViewportChange();
})();
