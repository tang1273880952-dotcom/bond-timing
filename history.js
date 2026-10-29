/* CSI 500 ERP historical valuation. Weekly only for verified official daily PE. */
(() => {
  'use strict';
  const root = document.getElementById('history-panel');
  if (!root) return;
  const el = id => document.getElementById(id);
  const state = {years: 10};
  const timestamp = date => Date.parse(String(date) + 'T00:00:00Z');
  const fmt = (n, decimals=2) => Number(n).toFixed(decimals) + '%';
  let saved = null;

  const lines = [
    {id:'p90', label:'90% · 极低估参考', color:'#147D52'},
    {id:'p80', label:'80% · 低估参考', color:'#55AC81'},
    {id:'p50', label:'50% · 历史中位', color:'#939BAA'},
    {id:'p20', label:'20% · 偏高估参考', color:'#E3A364'},
    {id:'p10', label:'10% · 高估参考', color:'#C66B43'}
  ];
  const zones = [
    {low:90, name:'极度相对低估', text:'中证500相对国债的历史吸引力非常高，可以重点研究分批买入。', tone:'positive'},
    {low:80, name:'相对低估', text:'中证500相对国债的估值吸引力较高，可以重点关注配置机会。', tone:'positive'},
    {low:50, name:'中性偏低估', text:'相对估值有一定吸引力，但尚未达到80%分位的低估参考区。', tone:'neutral'},
    {low:20, name:'中性偏高估', text:'当前ERP位于历史中低区域，相对估值优势不明显。', tone:'neutral'},
    {low:10, name:'相对高估', text:'中证500相对国债的估值吸引力偏弱，新增买入应更加谨慎。', tone:'warning'},
    {low:0, name:'极度相对高估', text:'中证500相对国债的历史吸引力很弱，需警惕估值风险。', tone:'warning'}
  ];
  const bandRows = [
    ['90%—100%', '极度相对低估', '相对国债非常便宜，重点研究买入机会'],
    ['80%—90%', '相对低估', '估值吸引力较高，关注分批配置'],
    ['50%—80%', '中性偏低估', '相对估值有一定优势'],
    ['20%—50%', '中性偏高估', '相对估值吸引力一般'],
    ['10%—20%', '相对高估', '新增买入需要更谨慎'],
    ['0%—10%', '极度相对高估', '相对国债吸引力很弱']
  ];

  root.addEventListener('click', event => {
    const button = event.target.closest('[data-history-years]');
    if (!button || ![3,5,10].includes(Number(button.dataset.historyYears))) return;
    state.years = Number(button.dataset.historyYears);
    render(saved);
  });

  const error = message => {
    el('history-current').innerHTML = '<div class="history-empty">' + message + '</div>';
    el('history-chart').innerHTML = '';
    el('history-hover').textContent = '';
    el('history-note').textContent = '没有可验证的数据时，不会生成模拟走势。';
    el('history-zones').innerHTML = '';
    el('history-legend').innerHTML = '';
  };

  function render(data) {
    saved = data;
    root.querySelectorAll('[data-history-years]').forEach(button => {
      const chosen = Number(button.dataset.historyYears) === state.years;
      button.classList.toggle('active', chosen);
      button.setAttribute('aria-pressed', String(chosen));
    });
    const d = data?.series?.csi500;
    const period = d?.periods?.[String(state.years)];
    if (!d || !Array.isArray(d.points) || d.points.length < 24 ||
        !period || !lines.every(l => Object.prototype.hasOwnProperty.call(period, l.id) &&
          Number.isFinite(Number(period[l.id]))) ||
        !Number.isFinite(Number(period.percentile))) {
      error('正在生成与所选年份对应的历史分位参考线，请等待网站数据更新。');
      return;
    }
    const end = timestamp(d.date);
    if (!Number.isFinite(end)) { error('历史数据日期异常。');return; }
    const cutoff = new Date(end);
    cutoff.setUTCFullYear(cutoff.getUTCFullYear() - state.years);
    const pts = d.points.map(p => ({
      date: String(p[0]), t: timestamp(p[0]), v: Number(p[1])
    })).filter(p =>
      Number.isFinite(p.t) && Number.isFinite(p.v) &&
      p.t >= cutoff.getTime() && p.t <= end
    ).sort((a,b)=>a.t-b.t);
    if (pts.length < 12) {error('该区间的实际数据不足。');return;}

    const percentile = Number(period.percentile);
    const zone = zones.find(z => percentile >= z.low) || zones[zones.length-1];
    const position = zones.indexOf(zone);
    const isWeekly = data.frequency === 'weekly';
    el('history-frequency').textContent =
      (isWeekly ? '真实周线 · 每周最后一个交易日' : '月线 · 日度历史PE尚不可用') +
      ' · 参考线按当前选定的近' + state.years + '年重新计算';
    el('history-current').innerHTML =
      '<div class="history-metric"><span>当前ERP</span><strong>' + fmt(d.latest) + '</strong></div>' +
      '<div class="history-metric"><span>近' + state.years + '年历史分位</span><strong>' + fmt(percentile,1) + '</strong></div>' +
      '<div class="history-state ' + zone.tone + '"><span>估值判断</span><strong>' + zone.name + '</strong></div>' +
      '<p class="history-asof">观测日期：' + d.date + ' · ' + (isWeekly ? '真实周度走势' : '真实月度走势') + '</p>';
    el('history-description').textContent = zone.text;
    el('history-note').textContent = '五条虚线依据近' + state.years + '年' +
      (isWeekly ? '真实日度' : '实际月度') + 'ERP观测计算（有效样本' +
      period.sampleCount + '个）。切换3年／5年／10年时，参考线和估值判断同步变化。';
    el('history-legend').innerHTML =
      '<div class="legend-item"><span class="legend-line" style="--line:#3769D2;--dash:none"></span>蓝线 · ERP' + (isWeekly ? '周' : '月') + '度走势</div>' +
      lines.map(l => '<div class="legend-item"><span class="legend-line" style="--line:' +
        l.color + '"></span>' + l.label + '（' + fmt(period[l.id]) + '）</div>').join('');
    el('history-zones').innerHTML = bandRows.map((r,i) =>
      '<div class="history-zone-row ' + (i === position ? 'selected' : '') +
      '"><span>' + r[0] + '</span><strong>' + r[1] + (i === position ? ' · 当前' : '') +
      '</strong><small>' + r[2] + '</small></div>'
    ).join('');

    const W=860,H=292,L=53,R=23,T=22,B=38;
    const plotW=W-L-R,plotH=H-T-B;
    const refValues=lines.map(l => Number(period[l.id]));
    const values=pts.map(p=>p.v).concat(refValues);
    const minVal=Math.min(...values), maxVal=Math.max(...values);
    const pad=Math.max(.10,(maxVal-minVal)*.10);
    const lo=minVal-pad,hi=maxVal+pad;
    const x=p=>L+(p.t-pts[0].t)/Math.max(1,pts[pts.length-1].t-pts[0].t)*plotW;
    const y=v=>T+(hi-v)/(hi-lo)*plotH;
    const path=pts.map((p,i)=>(i?'L':'M')+x(p).toFixed(2)+' '+y(p.v).toFixed(2)).join(' ');
    let svg='<svg id="history-svg" class="history-svg" viewBox="0 0 '+W+' '+H+
      '" role="img" aria-label="中证500 ERP历史估值和五条历史分位参考线">';
    for(let i=0;i<=4;i++){
      const value=lo+(hi-lo)*i/4,py=y(value);
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+py+'" y2="'+py+
        '" stroke="#e4eaf2"/><text x="'+(L-8)+'" y="'+(py+4)+'" font-size="11" fill="#8492a7" text-anchor="end">'+
        value.toFixed(2)+'</text>';
    }
    for(const l of lines){
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y(period[l.id])+'" y2="'+y(period[l.id])+
        '" stroke="'+l.color+'" stroke-width="1.5" stroke-dasharray="6 5"/>';
    }
    svg+='<path d="'+path+'" fill="none" stroke="#3769D2" stroke-width="2.6" stroke-linejoin="round" stroke-linecap="round"/>';
    const last=pts[pts.length-1];
    svg+='<circle cx="'+x(last)+'" cy="'+y(last.v)+'" r="5" fill="#3769D2" stroke="#fff" stroke-width="2"/>';
    svg+='<line id="history-guide" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+'" stroke="#7287ad" stroke-dasharray="4 4" visibility="hidden"/>';
    svg+='<circle id="history-dot" cx="0" cy="0" r="5" fill="#3769D2" stroke="#fff" stroke-width="2" visibility="hidden"/>';
    svg+='<rect x="'+L+'" y="'+T+'" width="'+plotW+'" height="'+plotH+'" fill="transparent"/>';
    svg+='<text x="'+L+'" y="'+(H-8)+'" font-size="11" fill="#8090a7">'+pts[0].date.slice(0,7)+'</text>';
    svg+='<text x="'+(W-R)+'" y="'+(H-8)+'" text-anchor="end" font-size="11" fill="#8090a7">'+last.date.slice(0,7)+'</text></svg>';
    el('history-chart').innerHTML=svg;
    const graph=el('history-svg'),hover=el('history-hover');
    hover.textContent='移动鼠标或点按曲线，查看历史日期和当时的ERP';
    function show(event){
      const box=graph.getBoundingClientRect();
      if(!box.width)return;
      const px=(event.clientX-box.left)*W/box.width;
      if(px<L||px>W-R)return;
      const t=pts[0].t+(px-L)/plotW*(last.t-pts[0].t);
      let picked=pts[0],best=Infinity;
      for(const p of pts){
        const gap=Math.abs(p.t-t);
        if(gap<best){best=gap;picked=p;}
      }
      const guide=el('history-guide'),dot=el('history-dot'),gx=x(picked);
      guide.setAttribute('x1',gx);guide.setAttribute('x2',gx);
      guide.setAttribute('visibility','visible');
      dot.setAttribute('cx',gx);dot.setAttribute('cy',y(picked.v));
      dot.setAttribute('visibility','visible');
      hover.textContent=picked.date+' · ERP '+fmt(picked.v);
    }
    graph.addEventListener('pointermove',show);
    graph.addEventListener('pointerdown',show);
    graph.addEventListener('pointerleave',()=>{
      el('history-guide')?.setAttribute('visibility','hidden');
      el('history-dot')?.setAttribute('visibility','hidden');
    });
  }
  window.renderHistory=render;
})();
