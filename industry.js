/* Seven independently validated industry valuation charts.  No synthetic PE/PB. */
(() => {
  'use strict';
  const CONFIG=[
    ['399975','证券公司'],['399989','中证医疗'],['399971','中证传媒'],
    ['399998','中证煤炭'],['000807','食品饮料'],['399997','中证白酒'],
    ['399986','中证银行']
  ];
  const LEVELS=[
    ['p0','0%','#106d51'],['p10','10%','#15835c'],
    ['p20','20%','#64af88'],['p50','50%','#8c98a9'],
    ['p80','80%','#e1a462'],['p90','90%','#c96d49'],
    ['p100','100%','#ac4f3e']
  ];
  const years={};
  for (const [code] of CONFIG) years[code]=3;
  let source=null;
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  })[c]);
  const fmt=n=>Number(n).toFixed(2);
  const time=d=>Date.parse(String(d)+'T00:00:00Z');
  const zone=p=>p<=10?['极低估','cheap']:p<=20?['低估','cheap']:
    p<=40?['偏低估','watch']:p<60?['中性','neutral']:
    p<80?['偏高估','caution']:p<90?['高估','rich']:['极高估','rich'];
  function renderPanel(panel,entry){
    const code=panel.dataset.industryCode;
    const data=entry&&entry.code===code?entry:null;
    const year=years[code];
    panel.querySelectorAll('[data-industry-years]').forEach(button=>{
      const active=Number(button.dataset.industryYears)===year;
      button.classList.toggle('active',active);
      button.setAttribute('aria-pressed',String(active));
    });
    const summary=panel.querySelector('.industry-summary');
    const chart=panel.querySelector('.industry-chart');
    const legend=panel.querySelector('.industry-legend');
    const hover=panel.querySelector('.industry-hover');
    const note=panel.querySelector('.industry-note');
    const metric=String(data?.metric||panel.dataset.metric||'PE-TTM');
    const all=Array.isArray(data?.points)?data.points.map(p=>({
      date:String(p[0]),t:time(p[0]),value:Number(p[1])
    })).filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.value)&&p.value>0):[];
    const today=Number.isFinite(time(data?.date))?time(data.date):0;
    const begin=new Date(today);
    if(today)begin.setUTCFullYear(begin.getUTCFullYear()-year);
    const low=begin.getTime();
    const points=all.filter(p=>p.t>=low&&p.t<=today);
    const period=data?.valid===true?data.periods?.[String(year)]:null;
    const ok=data?.valid===true&&period&&points.length>=24&&
      LEVELS.every(l=>typeof period[l[0]]==='number'&&Number.isFinite(period[l[0]]))&&
      LEVELS.every((l,i)=>!i||period[LEVELS[i-1][0]]<=period[l[0]])&&
      Number.isFinite(Number(period.percentile));
    if(!ok){
      summary.className='industry-summary tone-neutral';
      summary.textContent=data?.valid===true?'该年限真实估值样本不足':
        (data?.reason||'等待真实历史估值数据');
      chart.innerHTML='<p class="industry-empty">暂无足够真实数据绘制'+year+'年估值图</p>';
      legend.textContent='';hover.textContent='';
      note.textContent=(data?.valid===true?'数据 '+escape(data.date)+' · ':'' )+
        (data?.note||'不使用指数价格代替PE、PB。');
      return;
    }
    const [label,tone]=zone(Number(period.percentile));
    summary.className='industry-summary tone-'+tone;
    summary.innerHTML=
      '<div class="industry-metric"><span>当前'+escape(metric)+'</span><strong>'+fmt(data.value)+'<small> 倍</small></strong></div>'+
      '<div class="industry-metric"><span>近'+year+'年分位</span><strong>'+fmt(period.percentile)+'<small>%</small></strong></div>'+
      '<div class="industry-metric"><span>估值状态</span><strong class="industry-state">'+label+'</strong></div>';
    const W=860,H=300,L=58,R=64,T=25,B=42,pW=W-L-R,pH=H-T-B;
    const vals=points.map(p=>p.value).concat(LEVELS.map(l=>Number(period[l[0]])));
    const min=Math.min(...vals),max=Math.max(...vals);
    const pad=Math.max(.2,(max-min)*.10);
    const y1=min-pad,y2=max+pad;
    const x=t=>L+(t-low)/Math.max(1,today-low)*pW;
    const y=v=>T+(y2-v)/(y2-y1)*pH;
    const val=v=>Number(v).toFixed(1);
    const path=points.map((p,i)=>(i?'L':'M')+x(p.t).toFixed(2)+' '+y(p.value).toFixed(2)).join(' ');
    const last=points[points.length-1];
    const endx=x(last.t),endy=y(last.value);
    let svg='<svg viewBox="0 0 '+W+' '+H+'" class="industry-svg" role="img" aria-label="'+
      escape(data.name)+'真实历史'+escape(metric)+'，分位参考线和当前点">';
    for(let k=0;k<=4;k++){
      const gy=T+pH*k/4;
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+gy+'" y2="'+gy+
        '" stroke="#e8eef5"/><text x="'+(L-10)+'" y="'+(gy+4)+
        '" text-anchor="end" font-size="11" fill="#8493a8">'+val(y2-(y2-y1)*k/4)+'</text>';
    }
    // Separate closely spaced labels, but leave every reference line at its
    // exact historical level: labels must not make lines look mispositioned.
    const ruleLabels=LEVELS.map(([key,pct,color])=>({
      key,pct,color,yy:y(period[key])
    })).sort((a,b)=>a.yy-b.yy);
    for(let i=0;i<ruleLabels.length;i++){
      const item=ruleLabels[i];
      item.ly=Math.max(T+7,item.yy+3,i?ruleLabels[i-1].ly+13:T+7);
    }
    const overflow=ruleLabels[ruleLabels.length-1].ly-(H-B-2);
    if(overflow>0)for(const item of ruleLabels)item.ly-=overflow;
    for (const item of ruleLabels) {
      const yy=item.yy;
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy.toFixed(2)+'" y2="'+yy.toFixed(2)+
        '" stroke="'+item.color+'" stroke-width="1.5" stroke-dasharray="6 5"/>';
      svg+='<text x="'+(W-R+8)+'" y="'+item.ly.toFixed(2)+
        '" fill="'+item.color+'" font-size="10">'+item.pct+'</text>';
    }
    svg+='<path d="'+path+'" fill="none" stroke="#356bd4" stroke-width="2.5" stroke-linejoin="round"/>';
    svg+='<circle cx="'+endx.toFixed(2)+'" cy="'+endy.toFixed(2)+
      '" r="6" stroke="#fff" stroke-width="2.5" fill="#356bd4"/>';
    const tagX=Math.min(Math.max(L+7,endx-105),W-R-109);
    const tagY=Math.min(Math.max(T+3,endy-41),H-B-24);
    svg+='<rect x="'+tagX.toFixed(1)+'" y="'+tagY.toFixed(1)+
      '" width="109" height="22" rx="7" fill="#2f5ea8"/>';
    svg+='<text x="'+(tagX+7).toFixed(1)+'" y="'+(tagY+15).toFixed(1)+
      '" fill="#fff" font-size="12">当前 '+fmt(last.value)+'倍</text>';
    const mid=new Date((low+today)/2).toISOString().slice(0,7);
    svg+='<text x="'+L+'" y="'+(H-11)+'" font-size="11" fill="#8190a5">'+
      new Date(low).toISOString().slice(0,7)+'</text>'+
      '<text x="'+(L+pW/2)+'" y="'+(H-11)+'" text-anchor="middle" font-size="11" fill="#8190a5">'+mid+'</text>'+
      '<text x="'+(W-R)+'" y="'+(H-11)+'" text-anchor="end" font-size="11" fill="#8190a5">'+
      String(data.date).slice(0,7)+'</text>'+
      '<line class="industry-cursor" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+
      '" stroke="#7189b7" stroke-dasharray="3 4" visibility="hidden"/>'+
      '<rect x="'+L+'" y="'+T+'" width="'+pW+'" height="'+pH+'" fill="transparent"/></svg>';
    chart.innerHTML=svg;
    legend.innerHTML='<span class="legend-item"><i class="legend-line" style="--line:#356bd4;--dash:none"></i>'+escape(metric)+'实线</span>'+
      LEVELS.map(([key,pct,color])=>'<span class="legend-item"><i class="legend-line" style="--line:'+
        color+'"></i>'+pct+' · '+fmt(period[key])+'倍</span>').join('');
    note.textContent='数据 '+data.date+' · 参考截止 '+period.referenceDate+
      ' · '+period.sampleCount+'个交易日样本 · '+data.source+
      (data.note?' · '+data.note:'');
    hover.textContent='移动或点击走势图查看历史估值';
    const svgNode=chart.querySelector('svg');
    const cursor=chart.querySelector('.industry-cursor');
    if(!svgNode||!cursor)return;
    function show(ev){
      const rect=svgNode.getBoundingClientRect();
      if(!rect.width)return;
      const sx=(ev.clientX-rect.left)*W/rect.width;
      if(sx<L||sx>W-R)return;
      const when=low+(sx-L)/pW*(today-low);
      let best=points[0];
      for (const pt of points)if(Math.abs(pt.t-when)<Math.abs(best.t-when))best=pt;
      const cx=x(best.t).toFixed(2);
      cursor.setAttribute('x1',cx);cursor.setAttribute('x2',cx);
      cursor.setAttribute('visibility','visible');
      hover.textContent=best.date+' · '+metric+' '+fmt(best.value)+'倍';
    }
    svgNode.addEventListener('pointermove',show);
    svgNode.addEventListener('pointerdown',show);
    svgNode.addEventListener('pointerleave',()=>cursor.setAttribute('visibility','hidden'));
  }
  function render(payload){
    source=payload;
    for(const [code] of CONFIG){
      const panel=document.querySelector('[data-industry-code="'+code+'"]');
      if(!panel)continue;
      const entry=payload?.items?.find(x=>x.code===code);
      renderPanel(panel,entry);
    }
  }
  document.addEventListener('click',event=>{
    const btn=event.target.closest('[data-industry-years]');
    if(!btn)return;
    const panel=btn.closest('[data-industry-code]');
    if(!panel)return;
    years[panel.dataset.industryCode]=Number(btn.dataset.industryYears);
    render(source);
  });
  window.renderIndustries=render;
})();
