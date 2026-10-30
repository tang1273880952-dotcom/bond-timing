/* Spot gold / publicly disclosed global AISC. User-defined cost bands, no PE. */
(() => {
  'use strict';
  const $=id=>document.getElementById(id);
  if(!$('gold-section')||!$('gold-panel'))return;
  const levels=[[1.3,'#15835c'],[1.5,'#68ae86'],[2.2,'#8998aa'],[2.7,'#dfa05f'],[3.0,'#c56843']];
  const tones=new Set(['cheap','watch','neutral','caution','rich']);
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const time=d=>Date.parse(String(d)+'T00:00:00Z');
  const number=(v,n=2)=>Number(v).toLocaleString('en-US',{minimumFractionDigits:n,maximumFractionDigits:n});
  const money=v=>'$'+number(v);
  let data=null,sync=null,years=5,view='price',expanded=false;

  function valid(){
    return data?.valid===true&&data?.mode==='gold-aisc-v1'&&data.quoteType==='spot'&&
      Number.isFinite(data.price)&&data.price>0&&Number.isFinite(data.aisc)&&data.aisc>0&&
      Number.isFinite(data.ratio)&&Math.abs(data.price/data.aisc-data.ratio)<.0001;
  }
  function health(){
    if(!valid())return {ok:false,label:'等待真实金价与公开成本'};
    if(data.costStale)return {ok:false,label:'公开成本较旧，暂作历史参考'};
    if(sync?.costCheckSuccess===false)return {ok:false,label:'成本核验受限，沿用已公开值'};
    return typeof window.dataHealth==='function'?window.dataHealth(data.priceDate,sync):
      {ok:sync?.success!==false,label:sync?.success===false?'更新失败，沿用旧数据':''};
  }
  function renderCard(){
    const box=$('gold-card'),stamp=$('gold-stamp'),h=health();
    const tone=valid()&&tones.has(data.classification?.tone)?data.classification.tone:'neutral';
    $('gold-section').className='panel gold-panel overview-card tone-'+tone;
    stamp.classList?.toggle('data-warning',!h.ok);
    if(!valid()){
      stamp.textContent='等待有效数据';
      box.innerHTML='<p class="us-empty">'+esc(h.label)+'</p>';
      return;
    }
    stamp.textContent='数据 '+data.priceDate+(h.ok?'':' · '+h.label);
    const source=/^https:\/\/(www\.)?gold\.org\//.test(data.costSource)?data.costSource:null;
    box.innerHTML='<div class="score-line"><strong class="score-value">'+number(data.ratio)+
      '</strong><span class="score-unit">× AISC</span></div>'+
      '<div class="valuation-status">'+esc(data.classification.label)+'</div>'+
      '<div class="asset-main-metric"><span>伦敦金</span><b>'+money(data.price)+'</b></div>'+
      '<p class="asset-footnote">公开AISC '+esc(data.costPeriod)+' · 季度成本</p>'+
      '<button type="button" class="expand-trigger" data-gold-expand aria-expanded="'+expanded+'">'+
      (expanded?'收起详情 −':'查看指标 +')+'</button>'+
      (expanded?'<div class="card-metrics">'+[
        ['伦敦金现货（美元/盎司）',money(data.price)],
        ['行业平均AISC（美元/盎司）',money(data.aisc)],
        ['金价 ÷ AISC',number(data.ratio)+'倍'],
        ['成本所属季度',data.costPeriod],['成本公布日期',data.costPublishedDate],
        ['图表生效日期',data.costEffectiveDate]
      ].map(([label,value])=>'<div class="card-metric"><span>'+esc(label)+'</span><b>'+esc(value)+'</b></div>').join('')+
      '<p class="compact-advice">倍数为自设成本参考，非公允价值或历史分位。日线最新价可能为盘中值。</p>'+
      (source?'<a class="gold-source" href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">查看公开成本来源 ↗</a>':'')+
      '</div>':'');
  }

  function renderChart(){
    const h=health();
    const summary=$('gold-summary'),chart=$('gold-chart');
    $('gold-panel').querySelectorAll('[data-gold-years]').forEach(btn=>{
      const active=String(btn.dataset.goldYears)===String(years);
      btn.classList.toggle('active',active);btn.setAttribute('aria-pressed',String(active));
    });
    $('gold-panel').querySelectorAll('[data-gold-view]').forEach(btn=>{
      const active=btn.dataset.goldView===view;
      btn.classList.toggle('active',active);btn.setAttribute('aria-pressed',String(active));
    });
    if(!valid()||!Array.isArray(data.points)){
      summary.className='bse-summary tone-neutral';
      summary.innerHTML='<p class="history-empty">等待可核验的黄金成本参考数据</p>';
      chart.innerHTML='';$('gold-legend').innerHTML='';$('gold-note').textContent='不使用猜测成本补齐历史。';return;
    }
    const end=time(data.priceDate),first=time(data.historyStartDate),cutoff=new Date(end);
    if(years!=='all')cutoff.setUTCFullYear(cutoff.getUTCFullYear()-Number(years));
    const start=years==='all'?first:Math.max(first,cutoff.getTime());
    const points=data.points.map(p=>({date:String(p[0]),t:time(p[0]),price:Number(p[1]),
      aisc:Number(p[2]),ratio:Number(p[3]),period:String(p[4]),published:String(p[5])}))
      .filter(p=>p.t>=start&&p.t<=end&&[p.price,p.aisc,p.ratio].every(x=>Number.isFinite(x)&&x>0));
    if(points.length<12){chart.innerHTML='<p class="history-empty">该区间历史数据不足</p>';return;}
    const tone=tones.has(data.classification?.tone)?data.classification.tone:'neutral';
    summary.className='bse-summary tone-'+tone;
    summary.innerHTML=[['当前成本倍数',number(data.ratio)+'×',data.classification.label],
      ['伦敦金现货',money(data.price),data.priceDate],
      ['公开行业AISC',money(data.aisc),data.costPeriod+' · 有披露滞后']]
      .map(([label,value,note])=>'<div class="bse-metric"><span>'+esc(label)+'</span><strong>'+esc(value)+
        '</strong><small>'+esc(note)+'</small></div>').join('');
    const events=(data.costEvents||[]).map(e=>({...e,t:time(e.effectiveDate)}))
      .filter(e=>Number.isFinite(e.t)&&e.t<=end&&Number.isFinite(e.aisc)&&e.aisc>0).sort((a,b)=>a.t-b.t);
    const baseline=events.filter(e=>e.t<=start).at(-1)||events[0];
    if(!baseline){chart.innerHTML='<p class="history-empty">缺少可核验的成本公布记录</p>';return;}
    const steps=[{...baseline,t:start},...events.filter(e=>e.t>start)];
    const W=900,H=355,L=66,R=22,T=24,B=42,pW=W-L-R,pH=H-T-B;
    const isPrice=view==='price';
    const vals=points.map(p=>isPrice?p.price:p.ratio).concat(
      isPrice?steps.flatMap(e=>levels.map(([m])=>e.aisc*m)):levels.map(([m])=>m));
    const lo=Math.min(...vals),hi=Math.max(...vals),padding=Math.max(isPrice?20:.06,(hi-lo)*.09);
    const min=lo-padding,max=hi+padding;
    const x=t=>L+(t-start)/Math.max(1,end-start)*pW;
    const y=v=>T+(max-v)/Math.max(.001,max-min)*pH;
    const fix=n=>Number(n).toFixed(2);
    let svg='<svg id="gold-svg" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="黄金AISC'+
      (isPrice?'价格参考带':'成本倍数走势')+'"><defs><clipPath id="gold-clip"><rect x="'+L+'" y="'+T+
      '" width="'+pW+'" height="'+pH+'"/></clipPath></defs>';
    for(let i=0;i<=5;i++){
      const value=min+(max-min)*i/5,py=y(value);
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+fix(py)+'" y2="'+fix(py)+'" stroke="#e9eef5"/>'+
        '<text x="'+(L-9)+'" y="'+fix(py+4)+'" text-anchor="end" class="chart-axis">'+
        (isPrice?number(value,0):number(value,1)+'×')+'</text>';
    }
    for(let i=0;i<=4;i++){
      const t=start+(end-start)*i/4;
      svg+='<text x="'+fix(x(t))+'" y="'+(H-13)+'" text-anchor="'+(i===0?'start':i===4?'end':'middle')+
        '" class="chart-axis">'+new Date(t).toISOString().slice(0,7)+'</text>';
    }
    svg+='<g clip-path="url(#gold-clip)">';
    for(const [multiple,color] of levels){
      let path;
      if(!isPrice)path='M'+L+' '+fix(y(multiple))+'H'+(W-R);
      else{
        path='M'+L+' '+fix(y(steps[0].aisc*multiple));
        for(let i=1;i<steps.length;i++)path+='H'+fix(x(steps[i].t))+'V'+fix(y(steps[i].aisc*multiple));
        path+='H'+(W-R);
      }
      svg+='<path class="gold-reference" data-gold-multiple="'+multiple+'" d="'+path+
        '" fill="none" stroke="'+color+'" stroke-width="1.5" stroke-dasharray="5 4"/>';
    }
    const path=points.map((p,i)=>(i?'L':'M')+fix(x(p.t))+' '+fix(y(isPrice?p.price:p.ratio))).join(' ');
    const last=points.at(-1);
    svg+='<path class="gold-main-line" d="'+path+'" fill="none" stroke="#3975d6" stroke-width="2.5"/>'+
      '<circle cx="'+fix(x(last.t))+'" cy="'+fix(y(isPrice?last.price:last.ratio))+
      '" r="4" fill="#3975d6" stroke="#fff" stroke-width="1.5"/>'+
      '<line id="gold-cursor" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+
      '" stroke="#9aacbf" stroke-dasharray="3 4" visibility="hidden"/></g></svg>';
    chart.innerHTML=svg;
    $('gold-legend').innerHTML='<span class="legend-item"><i class="legend-line" style="--line:#3975d6;--dash:none"></i>'+
      (isPrice?'伦敦金现货':'金价 / 已披露AISC')+'</span>'+levels.map(([m,color])=>
      '<span class="legend-item"><i class="legend-line" style="--line:'+color+'"></i>'+m.toFixed(1)+'×'+
      (isPrice?' · '+money(data.aisc*m):'')+'</span>').join('');
    $('gold-note').className='bse-note'+(h.ok?'':' data-warning');
    $('gold-note').textContent='公开成本 '+data.costPeriod+' · 公布 '+data.costPublishedDate+
      ' · 按公布次日生效 · 五档倍数自设参考'+(h.ok?'':' · '+h.label);
    $('gold-hover').textContent='移动或点击查看当时金价、已披露成本和倍数。';
    const graph=$('gold-svg'),cursor=$('gold-cursor');
    if(graph&&cursor){
      function hover(event){
        const rect=graph.getBoundingClientRect();if(!rect.width)return;
        const sx=(event.clientX-rect.left)*W/rect.width;
        const when=start+(Math.max(L,Math.min(W-R,sx))-L)/pW*(end-start);
        let closest=points[0];
        for(const point of points)if(Math.abs(point.t-when)<Math.abs(closest.t-when))closest=point;
        const cx=fix(x(closest.t));cursor.setAttribute('x1',cx);cursor.setAttribute('x2',cx);cursor.setAttribute('visibility','visible');
        $('gold-hover').textContent=closest.date+' · 金价 '+money(closest.price)+' · AISC '+money(closest.aisc)+
          '（'+closest.period+'，'+closest.published+'公布） · '+number(closest.ratio)+'×';
      }
      graph.addEventListener('pointermove',hover);graph.addEventListener('pointerdown',hover);
      graph.addEventListener('pointerleave',()=>cursor.setAttribute('visibility','hidden'));
    }
  }
  $('gold-card').addEventListener('click',event=>{
    if(event.target.closest('[data-gold-expand]')){expanded=!expanded;renderCard();}
  });
  $('gold-panel').addEventListener('click',event=>{
    const range=event.target.closest('[data-gold-years]'),mode=event.target.closest('[data-gold-view]');
    if(range){years=range.dataset.goldYears==='all'?'all':Number(range.dataset.goldYears);renderChart();}
    if(mode){view=mode.dataset.goldView==='ratio'?'ratio':'price';renderChart();}
  });
  window.renderGold=(payload,status)=>{data=payload;sync=status;renderCard();renderChart();};
})();
