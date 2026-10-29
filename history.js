/* CSI500 ERP: actual weekly observations + honest monthly rolling percentile bands. */
(() => {
  'use strict';
  const root=document.getElementById('history-panel');
  if (!root) return;
  const el=id=>document.getElementById(id);
  const state={years:10};
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
    const btn=event.target.closest('[data-history-years]');
    if(!btn||![3,5,10].includes(Number(btn.dataset.historyYears)))return;
    state.years=Number(btn.dataset.historyYears);
    render(saved);
  });
  function error(msg){
    el('history-current').innerHTML='<div class="history-empty">'+msg+'</div>';
    el('history-chart').innerHTML='';
    el('history-hover').textContent='';
    el('history-zones').innerHTML='';
    el('history-legend').innerHTML='';
    el('history-description').textContent='';
    el('history-note').textContent='缺失真实数据的时期不会补画估值带。';
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
      !Array.isArray(p.bands)||!Number.isFinite(Number(p.percentile))||
      !lines.every(l=>Number.isFinite(Number(p[l.id])))){
      error('动态估值带数据正在更新，暂不显示模拟参考线。');return;
    }
    const end=dateValue(d.date),cutoff=new Date(end);
    if(!Number.isFinite(end)){error('估值历史日期异常。');return;}
    cutoff.setUTCFullYear(cutoff.getUTCFullYear()-state.years);
    const prices=d.points.map(v=>({date:v[0],t:dateValue(v[0]),v:Number(v[1])}))
      .filter(v=>Number.isFinite(v.t)&&Number.isFinite(v.v)&&v.t>=cutoff.getTime()&&v.t<=end)
      .sort((a,b)=>a.t-b.t);
    const bands=p.bands.map(row=>({date:row[0],t:dateValue(row[0]),vals:row.slice(1).map(Number)}))
      .filter(row=>Number.isFinite(row.t)&&row.vals.length===5&&row.vals.every(Number.isFinite)&&
        row.t>=cutoff.getTime()&&row.t<=end)
      .sort((a,b)=>a.t-b.t);
    if(prices.length<12){error('当前范围内有效ERP历史数据不足。');return;}
    const pct=Number(p.percentile),zone=zones.find(z=>pct>=z.low)||zones[zones.length-1];
    const position=zones.indexOf(zone),weekly=data.frequency==='weekly';
    const nearMedian=pct>=40&&pct<=60;
    const stateName=nearMedian?'历史中位附近':zone.name;
    const explanation=nearMedian?'目前ERP接近所选区间的历史中位，属于相对估值正常区间，不能认定明显高估或低估。':zone.text;
    const isMonthlyBand=p.basis==='月度真实观测';
    el('history-frequency').textContent=(weekly?'真实ERP周线':'真实ERP月线')+
      ' · '+state.years+'年滚动估值带按'+(isMonthlyBand?'月度':'日度')+
      '样本统计、每月更新 · 历史参考不使用未来数据';
    el('history-current').innerHTML=
      '<div class="history-metric"><span>当前ERP</span><strong>'+fmt(d.latest)+'</strong></div>'+
      '<div class="history-metric"><span>近'+state.years+'年历史分位'+(isMonthlyBand?'（月度）':'')+'</span><strong>'+fmt(pct,1)+'</strong></div>'+
      '<div class="history-state '+zone.tone+'"><span>当前估值判断</span><strong>'+stateName+'</strong></div>'+
      '<p class="history-asof">观测日期：'+d.date+' · '+(weekly?'周度ERP曲线':'月度ERP曲线')+'</p>';
    el('history-description').textContent=explanation;
    const bandStarts=p.bands.length ? dateValue(p.bands[0][0]) : NaN;
    const incomplete=Number.isFinite(bandStarts)&&bandStarts>cutoff.getTime()+60*864e5;
    el('history-note').textContent='五条彩色曲线：在每个历史月末，用此前'+state.years+
      '年ERP观测重新计算10% / 20% / 50% / 80% / 90%分位。本月按最新交易日更新。'+
      ' 当前参考线使用'+p.sampleCount+'个'+(isMonthlyBand?'月度':'日度')+'真实样本。'+
      (isMonthlyBand?' 10年带为统一月度来源的长期回填，和蓝色官方周度ERP使用不同估值数据源；因此其当前ERP数值可能略有差异。':'')+
      '滚动分位线可能因旧数据离开窗口而出现拐点或跳变；为保证数据口径准确，未对分位数进行人为平滑。'+
      (incomplete?' 较早时期缺少完整'+state.years+'年估值历史，滚动参考带从'+p.bands[0][0]+'才开始绘制；空白区域不是0%。':'');
    el('history-legend').innerHTML=
      '<div class="legend-item"><span class="legend-line" style="--line:#3769D2;--dash:none"></span>蓝线 · ERP'+(weekly?'周度':'月度')+'真实走势</div>'+
      lines.map(l=>'<div class="legend-item"><span class="legend-line" style="--line:'+
        l.color+'"></span>'+l.label+'（目前'+fmt(p[l.id])+'）</div>').join('');
    el('history-zones').innerHTML=bandRows.map((row,i)=>
      '<div class="history-zone-row '+(i===position?'selected':'')+'"><span>'+row[0]+'</span><strong>'+
      row[1]+(i===position?' · 当前':'')+'</strong><small>'+row[2]+'</small></div>'
    ).join('');

    const W=860,H=304,L=54,R=23,T=22,B=39,plotW=W-L-R,plotH=H-T-B;
    const bvals=bands.flatMap(x=>x.vals),all=prices.map(x=>x.v).concat(bvals);
    const rangeMin=Math.min(...all),rangeMax=Math.max(...all);
    const pad=Math.max(0.12,(rangeMax-rangeMin)*0.09),min=rangeMin-pad,max=rangeMax+pad;
    const left=prices[0].t,right=prices[prices.length-1].t;
    const x=t=>L+(t-left)/Math.max(1,right-left)*plotW;
    const y=v=>T+(max-v)/Math.max(0.001,max-min)*plotH;
    const valuePath=(rows,read)=>rows.map((r,i)=>(i?'L':'M')+
      x(r.t).toFixed(2)+' '+y(read(r)).toFixed(2)).join(' ');
    let svg='<svg id="history-svg" class="history-svg" viewBox="0 0 '+W+' '+H+
      '" role="img" aria-label="中证500真实ERP历史周线及五条每月滚动计算的历史估值分位曲线">';
    for(let i=0;i<=4;i++){
      const value=min+(max-min)*i/4,yy=y(value);
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+
        '" stroke="#e4eaf2"/><text x="'+(L-8)+'" y="'+(yy+4)+
        '" fill="#8592a6" font-size="11" text-anchor="end">'+value.toFixed(2)+'</text>';
    }
    // Pale center band, with lines retained as the precise data. No future values.
    if(bands.length>=2){
      // Raw bands order: [date, p10, p20, p50, p80, p90].
      const upper=bands.map(row=>x(row.t).toFixed(2)+' '+y(row.vals[3]).toFixed(2));
      const lower=[...bands].reverse().map(row=>x(row.t).toFixed(2)+' '+y(row.vals[1]).toFixed(2));
      svg+='<path d="M'+upper.join(' L')+' L'+lower.join(' L')+
        ' Z" fill="#c6d1e6" fill-opacity=".17"/>';
    }
    for(const l of lines){
      if(bands.length<2)continue;
      // The backend only returns genuinely observed, history-sufficient monthly anchors.
      // Break the line across any gap longer than two months.
      let segment=[];
      const flush=()=>{
        if(segment.length>=2)svg+='<path d="'+valuePath(segment,r=>r.vals[l.at-1])+
          '" fill="none" stroke="'+l.color+'" stroke-width="1.7" stroke-dasharray="6 4" stroke-linecap="round"/>';
        segment=[];
      };
      for(const b of bands){
        if(segment.length&&b.t-segment[segment.length-1].t>64*864e5)flush();
        segment.push(b);
      }
      flush();
    }
    svg+='<path d="'+valuePath(prices,r=>r.v)+
      '" fill="none" stroke="#3769D2" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>';
    const current=prices[prices.length-1];
    svg+='<circle cx="'+x(current.t)+'" cy="'+y(current.v)+
      '" r="5" fill="#3769D2" stroke="white" stroke-width="2"/>';
    svg+='<line id="history-guide" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+
      '" stroke="#7589ae" stroke-dasharray="4 4" visibility="hidden"/>';
    svg+='<circle id="history-dot" cx="0" cy="0" r="5" fill="#3769D2" stroke="#fff" stroke-width="2" visibility="hidden"/>';
    svg+='<rect x="'+L+'" y="'+T+'" width="'+plotW+'" height="'+plotH+'" fill="transparent"/>';
    svg+='<text x="'+L+'" y="'+(H-9)+'" font-size="11" fill="#8191a7">'+prices[0].date.slice(0,7)+'</text>';
    svg+='<text x="'+(W-R)+'" y="'+(H-9)+'" font-size="11" fill="#8191a7" text-anchor="end">'+current.date.slice(0,7)+'</text></svg>';
    el('history-chart').innerHTML=svg;
    const graph=el('history-svg'),hover=el('history-hover');
    if(bands.length<2)hover.textContent='历史滚动估值带样本不足，当前仅显示真实ERP及有效参考值。';
    else hover.textContent='鼠标悬停或点击曲线，可查看当时ERP与历史估值带';
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
      // Only historical reference dates <= selected date are eligible.
      let band=null;
      for(const candidate of bands){if(candidate.t<=picked.t)band=candidate;else break;}
      hover.textContent=picked.date+' · ERP '+fmt(picked.v)+
        (band?' ｜ 截至'+band.date+'的'+state.years+'年参考：80% '+fmt(band.vals[3])+
        '、20% '+fmt(band.vals[1]):' ｜ 当时历史样本不足，暂无分位参考');
    };
    graph.addEventListener('pointermove',select);
    graph.addEventListener('pointerdown',select);
    graph.addEventListener('pointerleave',()=>{
      el('history-guide')?.setAttribute('visibility','hidden');
      el('history-dot')?.setAttribute('visibility','hidden');
    });
  }
  window.renderHistory=render;
})();
