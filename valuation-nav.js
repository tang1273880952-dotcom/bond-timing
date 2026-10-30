/* Compact floating index navigation; status uses exactly each chart's selected horizon. */
(() => {
  'use strict';
  const wrap=document.getElementById('valuation-jump');
  const toggle=document.getElementById('valuation-jump-toggle');
  const panel=document.getElementById('valuation-jump-panel');
  if(!wrap||!toggle||!panel)return;

  const charts=[
    {key:'csi500',target:'history-panel',kind:'erp',button:'data-history-years',fallback:10},
    {key:'star100',target:'star-panel',kind:'erp',button:'data-star-years',fallback:3},
    {key:'bse50',target:'bse-panel',kind:'erp',button:'data-bse-years',fallback:3},
    ...['399975','399989','399971','399998','000807','399997','399986']
      .map(code=>({key:code,target:'industry-'+code,kind:'pe',
        button:'data-industry-years',fallback:3}))
  ];
  let current={market:null,industry:null};
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
    let lowCount=0;
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
      if(tone==='cheap'||tone==='watch')lowCount++;
      chip.dataset.tone=tone;
      chip.textContent=name+' · '+Math.round(p)+'%';
      chip.title='近'+selectedYears(chart)+'年历史分位 '+p.toFixed(1)+'% · 数据 '+(date||'待核对')+
        (chart.kind==='erp'?' · ERP越高越便宜':' · PE越低越便宜');
    }
    const count=document.getElementById('valuation-jump-count');
    if(count)count.textContent=lowCount?lowCount+'项偏低':'10张图';
  }
  function setOpen(open){
    panel.hidden=!open;
    toggle.setAttribute('aria-expanded',String(open));
    wrap.classList.toggle('is-open',open);
  }
  toggle.addEventListener('click',()=>setOpen(panel.hidden));
  panel.addEventListener('click',event=>{
    const link=event.target.closest('a[href^="#"]');
    if(link)setOpen(false);
  });
  document.addEventListener('click',event=>{
    const range=event.target.closest(
      '[data-history-years],[data-star-years],[data-bse-years],[data-industry-years]');
    if(range)render();
    if(!panel.hidden&&!wrap.contains(event.target))setOpen(false);
  });
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&!panel.hidden){
      setOpen(false);
      toggle.focus();
    }
  });
  window.updateValuationJump=(market,industry)=>{
    current={market,industry};
    render();
  };
  render();
})();
