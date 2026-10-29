/* STAR 100 (000698): independently verified ERP, never simulated. */
(() => {
  'use strict';
  const root=document.getElementById('star-panel');
  if(!root)return;
  const el=id=>document.getElementById(id);
  const state={years:3};
  const levels=[
    ['p90','90% · 极低估','#147D52'],
    ['p80','80% · 低估','#55AC81'],
    ['p50','50% · 中位','#939BAA'],
    ['p20','20% · 偏高估','#E3A364'],
    ['p10','10% · 高估','#C66B43']
  ];
  const fmt=(n,d=2)=>Number(n).toFixed(d);
  const time=s=>Date.parse(String(s)+'T00:00:00Z');
  const zone=p=>p>=90?'极度相对低估':p>=80?'相对低估':p>=60?'相对偏低估':
    p>=40?'历史中位附近':p>=20?'相对偏高估':p>=10?'相对高估':'极度相对高估';
  let current=null;
  root.addEventListener('click',event=>{
    const button=event.target.closest('[data-star-years]');
    if(!button)return;
    const year=Number(button.dataset.starYears);
    if(![1,3].includes(year))return;
    state.years=year;
    render(current);
  });
  function metric(label,value,extra=''){
    return '<div class="star-metric"><span>'+label+'</span><strong>'+value+'</strong>'+
      (extra?'<small>'+extra+'</small>':'')+'</div>';
  }
  function render(data){
    current=data;
    root.querySelectorAll('[data-star-years]').forEach(button=>{
      const active=Number(button.dataset.starYears)===state.years;
      button.setAttribute('aria-pressed',String(active));
      button.classList.toggle('active',active);
    });
    const valid=data?.valid===true;
    const indexPoints=Array.isArray(data?.indexPoints)?
      data.indexPoints.map(p=>({date:String(p[0]),t:time(p[0]),v:Number(p[1])}))
        .filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.v)&&p.v>0):[];
    const period=valid?data.periods?.[String(state.years)]:null;
    const haveERP=valid&&period&&Array.isArray(data.points)&&
      levels.every(l=>Number.isFinite(Number(period[l[0]])));
    const cutoff=time(data?.date);
    const from=new Date(cutoff);
    if(Number.isFinite(cutoff))from.setUTCFullYear(from.getUTCFullYear()-state.years);
    const fromTime=Number.isFinite(cutoff)?from.getTime():0;
    const prices=indexPoints.filter(p=>p.t>=fromTime&&p.t<=cutoff);
    const erps=haveERP?data.points.map(p=>({date:String(p[0]),t:time(p[0]),v:Number(p[1])}))
      .filter(p=>Number.isFinite(p.t)&&Number.isFinite(p.v)&&p.t>=fromTime&&p.t<=cutoff):[];
    if(valid&& !data.periods?.["3"]){
      el('star-note').textContent='成立以来有效ERP样本不足完整三年，三年分位暂不计算。';
    }
    el('star-summary').innerHTML=valid?
      metric('当前ERP',fmt(data.erp)+'%','PE与同期10年国债收益率之差')+
      metric('滚动PE',fmt(data.pe)+'倍')+
      metric('10年国债收益率',fmt(data.yield10,3)+'%')+
      metric('近'+state.years+'年分位',haveERP?fmt(period.percentile,1)+'%':'—',haveERP?zone(period.percentile):'对应历史样本不足'):
      '<div class="star-alert"><strong>科创100ERP暂无法核验</strong>：'+
      '官方滚动PE缺失或数据尚未同步。不显示猜测的估值分位。'+
      '</div>'+(data?.indexLatest&&Number.isFinite(data.indexLatest)?
      metric('已核验指数点位',fmt(data.indexLatest)+'点',String(data.date||'')):'');
    if(!haveERP){
      el('star-note').textContent='科创100指数点位与历史ERP分开核验。'+
        (valid?'该时间范围尚不足以计算水平分位线。':(data?.reason||'尚无已核验的PE数据。'))+
        ' 没有真实ERP数据时不绘制假曲线。';
    }else{
      el('star-note').textContent='当前ERP日期 '+data.valuationDate+'。近'+state.years+
        '年分位参考截止 '+period.referenceDate+'，采用'+period.sampleCount+
        '个真实日度样本，每月根据上一个完整月份更新水平线。' +
        ' 科创100的历史分位不能与中证500直接比较。';
    }
    const plotIndex=prices.length>=12;
    const plotERP=haveERP&&erps.length>=12;
    if(!plotIndex&&!plotERP){
      el('star-chart').textContent='暂无足够真实数据绘制该区间走势。';
      el('star-legend').textContent='';el('star-hover').textContent='';return;
    }
    const W=860,H=300,L=55,R=67,T=20,B=36;
    const start=fromTime,end=cutoff,plotW=W-L-R,plotH=H-T-B;
    const x=t=>L+(t-start)/Math.max(1,end-start)*plotW;
    const vals=plotERP?erps.map(p=>p.v).concat(levels.map(l=>period[l[0]])):[];
    const eMin=plotERP?Math.min(...vals):0,eMax=plotERP?Math.max(...vals):1;
    const ePad=Math.max(.15,(eMax-eMin)*.1);
    const eY=v=>T+(eMax+ePad-v)/Math.max(.01,eMax-eMin+2*ePad)*plotH;
    const low=plotIndex?Math.min(...prices.map(p=>p.v)):0;
    const high=plotIndex?Math.max(...prices.map(p=>p.v)):1;
    const pad=Math.max(30,(high-low)*.08);
    const iY=v=>T+(high+pad-v)/Math.max(1,high-low+2*pad)*plotH;
    const line=(list,project)=>list.map((p,i)=>(i?'L':'M')+x(p.t).toFixed(2)+
      ' '+project(p.v).toFixed(2)).join(' ');
    let svg='<svg id="star-svg" viewBox="0 0 '+W+' '+H+
      '" role="img" aria-label="科创100指数真实周线和可验证的股债风险溢价历史走势">';
    for(let i=0;i<=4;i++){
      const y=T+(plotH*i/4);
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y+'" y2="'+y+
        '" stroke="#e5ebf4"/>';
      if(plotERP){
        const v=eMax+ePad-(eMax-eMin+2*ePad)*i/4;
        svg+='<text x="'+(L-8)+'" y="'+(y+4)+'" font-size="11" fill="#8795aa" text-anchor="end">'+fmt(v)+'</text>';
      }
      if(plotIndex){
        const v=high+pad-(high-low+2*pad)*i/4;
        svg+='<text x="'+(W-R+8)+'" y="'+(y+4)+'" font-size="11" fill="#997fbd">'+Math.round(v).toLocaleString('en-US')+'</text>';
      }
    }
    if(plotERP){
      for(const [key,,color] of levels){
        const y=eY(Number(period[key])).toFixed(2);
        svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+y+'" y2="'+y+
          '" stroke="'+color+'" stroke-width="1.6" stroke-dasharray="5 4"/>';
      }
      svg+='<path d="'+line(erps,eY)+
        '" fill="none" stroke="#3769D2" stroke-width="2.5" stroke-linejoin="round"/>';
      svg+='<text x="'+(L-8)+'" y="12" text-anchor="end" fill="#6a80a6" font-size="10">ERP %</text>';
    }
    if(plotIndex){
      svg+='<path d="'+line(prices,iY)+
        '" fill="none" stroke="#8450C6" stroke-opacity="'+(plotERP?'.35':'.68')+
        '" stroke-width="1.9" stroke-linejoin="round"/>';
      svg+='<text x="'+(W-4)+'" y="12" text-anchor="end" fill="#997fbd" font-size="10">指数点位</text>';
    }
    svg+='<line id="star-cursor" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+
      '" stroke="#8190ae" stroke-dasharray="3 4" visibility="hidden"/>';
    svg+='<rect x="'+L+'" y="'+T+'" width="'+plotW+'" height="'+plotH+'" fill="transparent"/>'+
      '<text x="'+L+'" y="'+(H-8)+'" font-size="11" fill="#8999aa">'+from.toISOString().slice(0,7)+'</text>'+
      '<text x="'+(W-R)+'" y="'+(H-8)+'" font-size="11" fill="#8999aa" text-anchor="end">'+String(data.date).slice(0,7)+'</text></svg>';
    el('star-chart').innerHTML=svg;
    el('star-legend').innerHTML=
      (plotERP?'<span class="legend-item"><i class="legend-line" style="--line:#3769D2;--dash:none"></i>ERP蓝线 · 左轴%</span>':'')+
      (plotIndex?'<span class="legend-item"><i class="legend-line" style="--line:rgba(132,80,198,.55);--dash:none"></i>科创100指数 · 右轴点</span>':'')+
      (plotERP?levels.map(l=>'<span class="legend-item"><i class="legend-line" style="--line:'+l[2]+
      '"></i>'+l[1]+'（'+fmt(period[l[0]])+'%）</span>').join(''):'');
    const svgElement=el('star-svg');
    const tooltip=el('star-hover');
    tooltip.textContent='悬停或点击走势图查看对应日期';
    const nearest=(list,t)=>list.reduce((best,v)=>!best||Math.abs(v.t-t)<Math.abs(best.t-t)?v:best,null);
    const hover=ev=>{
      const rect=svgElement.getBoundingClientRect();
      if(!rect.width)return;
      const pos=(ev.clientX-rect.left)*W/rect.width;
      if(pos<L||pos>W-R)return;
      const date=start+(pos-L)/plotW*(end-start);
      const ep=plotERP?nearest(erps,date):null;
      const ip=plotIndex?nearest(prices,date):null;
      const focus=ep||ip;
      if(!focus)return;
      const guide=el('star-cursor');
      guide.setAttribute('x1',x(focus.t));guide.setAttribute('x2',x(focus.t));
      guide.setAttribute('visibility','visible');
      tooltip.textContent=focus.date+
        (ep?' · ERP '+fmt(ep.v)+'%':'')+
        (ip?' · 指数 '+fmt(ip.v)+'点':'')+
        (plotERP?' · 当前'+state.years+'年80%参考 '+fmt(period.p80)+'%':'');
    };
    svgElement.addEventListener('pointermove',hover);
    svgElement.addEventListener('pointerdown',hover);
    svgElement.addEventListener('pointerleave',()=>{
      el('star-cursor')?.setAttribute('visibility','hidden');
    });
  }
  window.renderSTAR100=render;
})();
