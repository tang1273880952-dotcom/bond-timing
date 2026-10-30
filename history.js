/* CSI500 ERP: real weekly data, five horizontally frozen monthly valuation levels. */
(() => {
  'use strict';
  const root=document.getElementById('history-panel');
  if (!root) return;
  const el=id=>document.getElementById(id);
  const state={years:10,showIndex:true};
  const dateValue=s=>Date.parse(String(s)+'T00:00:00Z');
  const fmt=(n,d=2)=>Number(n).toFixed(d)+'%';
  let saved=null;
  const lines=[
    {id:'p90',at:5,label:'90% · 极低估参考',color:'#147D52'},
    {id:'p80',at:4,label:'80% · 低估参考',color:'#55AC81'},
    {id:'p50',at:3,label:'50% · 历史中位',color:'#939BAA'},
    {id:'p20',at:2,label:'20% · 偏高估参考',color:'#E3A364'},
    {id:'p10',at:1,label:'10% · 高估参考',color:'#C66B43'}
  ];
  const zones=[
    {low:90,name:'极度相对低估',text:'中证500相对国债的历史估值吸引力非常高，可以重点研究分批买入。',tone:'positive'},
    {low:80,name:'相对低估',text:'中证500相对国债的估值吸引力较高，可以重点关注配置机会。',tone:'positive'},
    {low:50,name:'中性偏低估',text:'相对估值有一定吸引力，但尚未进入80%分位以上的低估参考区。',tone:'neutral'},
    {low:20,name:'中性偏高估',text:'当前ERP处于历史中低区域，估值优势不明显。',tone:'neutral'},
    {low:10,name:'相对高估',text:'中证500相对国债的估值吸引力偏弱，新增买入应更加谨慎。',tone:'warning'},
    {low:0,name:'极度相对高估',text:'中证500相对国债的历史吸引力很弱，需要留意估值风险。',tone:'warning'}
  ];
  const bandRows=[
    ['90%—100%','极度相对低估','相对国债非常便宜，重点研究买入机会'],
    ['80%—90%','相对低估','估值吸引力较高，关注分批配置'],
    ['50%—80%','中性偏低估','相对估值有一定优势'],
    ['20%—50%','中性偏高估','相对估值吸引力一般'],
    ['10%—20%','相对高估','新增买入需要更谨慎'],
    ['0%—10%','极度相对高估','相对国债吸引力很弱']
  ];
  root.addEventListener('click',event=>{
    const indexToggle=event.target.closest('[data-index-toggle]');
    if(indexToggle){
      if(!indexToggle.disabled){state.showIndex=!state.showIndex;render(saved);}
      return;
    }
    const btn=event.target.closest('[data-history-years]');
    if(!btn||![3,5,10].includes(Number(btn.dataset.historyYears)))return;
    state.years=Number(btn.dataset.historyYears);
    render(saved);
  });
  function error(msg){
    // Missing data must never trigger a second exception.
    el('history-current').className='history-current tone-neutral';
    el('history-current').innerHTML='<div class="history-empty">'+msg+'</div>';
    el('history-chart').innerHTML='';
    el('history-hover').textContent='';
    el('history-zones').innerHTML='';
    el('history-legend').innerHTML='';
    el('history-description').textContent='';
    el('history-note').textContent='水平参考线仅使用上个已完成月份的数据，数据不足时不会使用模拟数值。';
  }
  function render(data){
    saved=data;
    root.querySelectorAll('[data-history-years]').forEach(btn=>{
      const yes=Number(btn.dataset.historyYears)===state.years;
      btn.classList.toggle('active',yes);
      btn.setAttribute('aria-pressed',String(yes));
    });
    const d=data?.series?.csi500,p=d?.periods?.[String(state.years)];
    if(!d||!Array.isArray(d.points)||d.points.length<24||!p||
      !p.referenceDate||!Number.isFinite(Number(p.percentile))||
      !lines.every(l=>Number.isFinite(Number(p[l.id])))){
      error('每月水平估值参考线数据正在更新，暂不显示模拟参考线。');return;
    }
    const end=dateValue(d.date),cutoff=new Date(end);
    if(!Number.isFinite(end)){error('估值历史日期异常。');return;}
    cutoff.setUTCFullYear(cutoff.getUTCFullYear()-state.years);
    const prices=d.points.map(v=>({date:v[0],t:dateValue(v[0]),v:Number(v[1])}))
      .filter(v=>Number.isFinite(v.t)&&Number.isFinite(v.v)&&v.t>=cutoff.getTime()&&v.t<=end)
      .sort((a,b)=>a.t-b.t);
       if(prices.length<12){error('当前范围内有效ERP历史数据不足。');return;}
    const indexSource=d.indexClose;
    const indexPoints=Array.isArray(indexSource?.points)?indexSource.points.map(row=>({
      date:String(row[0]),t:dateValue(row[0]),v:Number(row[1])
    })).filter(row=>Number.isFinite(row.t)&&Number.isFinite(row.v)&&row.v>0&&
      row.t>=cutoff.getTime()&&row.t<=end).sort((a,b)=>a.t-b.t):[];
    const indexReady=indexPoints.length>=12;
    const indexVisible=state.showIndex&&indexReady;
    const indexToggle=el('history-index-toggle');
    if(indexToggle){
      indexToggle.disabled=!indexReady;
      indexToggle.textContent=!indexReady?'指数数据待更新':(indexVisible?'隐藏指数走势':'叠加指数走势');
      indexToggle.setAttribute('aria-pressed',String(indexVisible));
      indexToggle.classList.toggle('active',indexVisible);
    }
    const pct=Number(p.percentile),zone=zones.find(z=>pct>=z.low)||zones[zones.length-1];
    const position=zones.indexOf(zone),weekly=data.frequency==='weekly';
    const nearMedian=pct>=40&&pct<=60;
    const stateName=nearMedian?'历史中位附近':zone.name;
    const explanation=nearMedian?'接近历史中位':pct>=80?'相对偏便宜':pct>=60?'略偏便宜':pct<20?'相对偏贵':'处于历史常见区间';
    const isMonthlyBand=p.basis==='月度真实观测';
    el('history-frequency').textContent=(weekly?'ERP周线':'ERP月线')+
      ' · 近'+state.years+'年水平分位参考线 · '+(isMonthlyBand?'月度':'日度')+
      '样本 · 截止'+p.referenceDate+' · 每月更新';
    el('history-current').innerHTML=
      '<div class="history-metric"><span>当前ERP</span><strong>'+fmt(d.latest)+'</strong></div>'+
      '<div class="history-metric"><span>近'+state.years+'年历史分位'+(isMonthlyBand?'（月度）':'')+'</span><strong>'+fmt(pct,1)+'</strong></div>'+
      '<div class="history-state '+zone.tone+'"><span>当前估值判断</span><strong>'+stateName+'</strong></div>'+
      '<p class="history-asof">观测日期：'+d.date+' · '+(weekly?'周度ERP曲线':'月度ERP曲线')+'</p>';
    el('history-description').textContent=explanation;
    el('history-note').textContent='参考 '+p.referenceDate+' · '+p.sampleCount+
      '个真实'+(isMonthlyBand?'月度':'日度')+'样本 · 水平线每月更新'+
      (isMonthlyBand?'（10年采用月度口径）':'');
    el('history-legend').innerHTML=
      '<div class="legend-item"><span class="legend-line" style="--line:#3769D2;--dash:none"></span>蓝线 · ERP'+(weekly?'周度':'月度')+'真实走势（左轴 %）</div>'+
      (indexVisible?'<div class="legend-item"><span class="legend-line" style="--line:rgba(132,80,198,0.35);--dash:none"></span>紫线 · 中证500指数收盘（右轴 点）</div>':'')+
      lines.map(l=>'<div class="legend-item"><span class="legend-line" style="--line:'+
        l.color+'"></span>'+l.label+'（'+fmt(p[l.id])+'）</div>').join('');
    el('history-zones').innerHTML=bandRows.map((row,i)=>
      '<div class="history-zone-row '+(i===position?'selected':'')+'"><span>'+row[0]+'</span><strong>'+
      row[1]+(i===position?' · 当前':'')+'</strong><small>'+row[2]+'</small></div>'
    ).join('');

    const W=860,H=304,L=54,R=indexVisible?65:23,T=22,B=39,plotW=W-L-R,plotH=H-T-B;
    const all=prices.map(point=>point.v).concat(lines.map(l=>Number(p[l.id])));
    const rangeMin=Math.min(...all),rangeMax=Math.max(...all);
    const pad=Math.max(0.12,(rangeMax-rangeMin)*0.09),min=rangeMin-pad,max=rangeMax+pad;
    const left=prices[0].t,right=prices[prices.length-1].t;
    const x=t=>L+(t-left)/Math.max(1,right-left)*plotW;
    const y=v=>T+(max-v)/Math.max(0.001,max-min)*plotH;
    const indexLow=indexVisible?Math.min(...indexPoints.map(p=>p.v)):0;
    const indexHigh=indexVisible?Math.max(...indexPoints.map(p=>p.v)):1;
    const indexPad=indexVisible?Math.max(70,(indexHigh-indexLow)*0.08):0;
    const indexMin=indexLow-indexPad,indexMax=indexHigh+indexPad;
    const yIndex=v=>T+(indexMax-v)/Math.max(1,indexMax-indexMin)*plotH;
    const valuePath=(rows,read)=>rows.map((r,i)=>(i?'L':'M')+
      x(r.t).toFixed(2)+' '+y(read(r)).toFixed(2)).join(' ');
    let svg='<svg id="history-svg" class="history-svg" viewBox="0 0 '+W+' '+H+
      '" role="img" aria-label="中证500真实ERP周线及所选年份的五条每月更新的水平估值分位线">';
    for(let i=0;i<=4;i++){
      const value=min+(max-min)*i/4,yy=y(value);
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+
        '" stroke="#e4eaf2"/><text x="'+(L-8)+'" y="'+(yy+4)+
        '" fill="#8592a6" font-size="11" text-anchor="end">'+value.toFixed(2)+'</text>';
      if(indexVisible){
        const idxValue=indexMin+(indexMax-indexMin)*i/4;
        svg+='<text x="'+(W-R+8)+'" y="'+(yIndex(idxValue)+4)+
          '" fill="#8450C6" fill-opacity="0.58" font-size="11" text-anchor="start">'+Math.round(idxValue).toLocaleString('en-US')+'</text>';
      }
    }
    svg+='<text x="'+(L-12)+'" y="12" text-anchor="middle" fill="#71819b" font-size="10">ERP %</text>';
    if(indexVisible)svg+='<text x="'+(W-8)+'" y="12" text-anchor="end" fill="#8450C6" fill-opacity="0.58" font-size="10">指数点位</text>';
    // Horizontal bands use the previous completed month's REAL observations.
    // They are TODAY'S valuation references, not historical point-in-time signals.
    for(const l of lines){
      const yy=y(Number(p[l.id])).toFixed(2);
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+
        '" stroke="'+l.color+'" stroke-width="1.7" stroke-dasharray="6 4"/>';
    }
    if(indexVisible){
      svg+='<path d="'+indexPoints.map((row,i)=>(i?'L':'M')+
        x(row.t).toFixed(2)+' '+yIndex(row.v).toFixed(2)).join(' ')+
        '" fill="none" stroke="#8450C6" stroke-opacity="0.35" stroke-width="2.0" stroke-linejoin="round" stroke-linecap="round"/>';
      const lastIndex=indexPoints[indexPoints.length-1];
      svg+='<circle cx="'+x(lastIndex.t)+'" cy="'+yIndex(lastIndex.v)+
        '" r="4" fill="#8450C6" fill-opacity="0.48" stroke="white" stroke-width="1.5"/>';
    }
    svg+='<path d="'+valuePath(prices,r=>r.v)+
      '" fill="none" stroke="#3769D2" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>';
    const current=prices[prices.length-1];
    svg+='<circle cx="'+x(current.t)+'" cy="'+y(current.v)+
      '" r="5" fill="#3769D2" stroke="white" stroke-width="2"/>';
    svg+='<line id="history-guide" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+
      '" stroke="#7589ae" stroke-dasharray="4 4" visibility="hidden"/>';
    svg+='<circle id="history-dot" cx="0" cy="0" r="5" fill="#3769D2" stroke="#fff" stroke-width="2" visibility="hidden"/>';
    if(indexVisible)svg+='<circle id="index-dot" cx="0" cy="0" r="5" fill="#8450C6" fill-opacity="0.72" stroke="#fff" stroke-width="2" visibility="hidden"/>';
    svg+='<rect x="'+L+'" y="'+T+'" width="'+plotW+'" height="'+plotH+'" fill="transparent"/>';
    svg+='<text x="'+L+'" y="'+(H-9)+'" font-size="11" fill="#8191a7">'+prices[0].date.slice(0,7)+'</text>';
    svg+='<text x="'+(W-R)+'" y="'+(H-9)+'" font-size="11" fill="#8191a7" text-anchor="end">'+current.date.slice(0,7)+'</text></svg>';
    el('history-chart').innerHTML=svg;
    const graph=el('history-svg'),hover=el('history-hover');
    hover.textContent='悬停查看当时ERP与指数点位；水平参考线截止 '+p.referenceDate;
    const select=ev=>{
      const rect=graph.getBoundingClientRect();
      if(!rect.width)return;
      const px=(ev.clientX-rect.left)*W/rect.width;
      if(px<L||px>W-R)return;
      const target=left+(px-L)/plotW*(right-left);
      let picked=prices[0],gap=Infinity;
      for(const pnt of prices){
        const dist=Math.abs(pnt.t-target);
        if(dist<gap){gap=dist;picked=pnt;}
      }
      const guide=el('history-guide'),dot=el('history-dot'),cx=x(picked.t);
      guide.setAttribute('x1',cx);guide.setAttribute('x2',cx);
      guide.setAttribute('visibility','visible');
      dot.setAttribute('cx',cx);dot.setAttribute('cy',y(picked.v));
      dot.setAttribute('visibility','visible');
         let indexText='';
      if(indexVisible){
        let nearest=null,dist=Infinity;
        for(const indexPoint of indexPoints){
          const diff=Math.abs(indexPoint.t-picked.t);
          if(diff<dist){dist=diff;nearest=indexPoint;}
        }
        if(nearest&&dist<=7*864e5){
          const idxDot=el('index-dot');
          idxDot?.setAttribute('cx',x(nearest.t));
          idxDot?.setAttribute('cy',yIndex(nearest.v));
          idxDot?.setAttribute('visibility','visible');
          indexText=' ｜ 中证500指数 '+nearest.v.toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2})+'点';
        }else{
          el('index-dot')?.setAttribute('visibility','hidden');
        }
      }
      hover.textContent=picked.date+' · ERP '+fmt(picked.v)+indexText+
        ' ｜ 当前水平参考线（'+p.referenceDate+'）：80% '+fmt(p.p80)+'、20% '+fmt(p.p20);
    };
    graph.addEventListener('pointermove',select);
    graph.addEventListener('pointerdown',select);
    graph.addEventListener('pointerleave',()=>{
      el('history-guide')?.setAttribute('visibility','hidden');
      el('history-dot')?.setAttribute('visibility','hidden');
      el('index-dot')?.setAttribute('visibility','hidden');
    });
  }
  window.renderHistory=render;
})();
