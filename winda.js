/* Wind All-A chart and separate overview card. No stock-index proxies. */
(() => {
 'use strict';
 const panel=document.getElementById('winda-panel');
 const card=document.getElementById('winda-section');
 if(!panel||!card)return;
 const byId=id=>document.getElementById(id);
 const state={years:10};
 const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=v=>Number(v).toFixed(2);
 const dateMs=x=>Date.parse(String(x)+'T00:00:00Z');
 const bands=[
   ['p90','90% · 极低估','#147d52'],['p80','80% · 低估','#55ac81'],
   ['p50','50% · 中位','#939baa'],['p20','20% · 偏高估','#e3a364'],
   ['p10','10% · 高估','#c66b43']
 ];
 let saved=null;
 const valid=d=>d?.valid===true&&d.code==='881001.WI'&&
   typeof d.erp==='number'&&Number.isFinite(d.erp)&&
   typeof d.pe==='number'&&d.pe>0;
 const cls=p=>p>=80?['相对低估','cheap']:
   p>=60?['略偏低估','watch']:p>=40?['中性','neutral']:
   p>=20?['偏高估','caution']:['相对高估','rich'];
 function cardView(d){
   const content=byId('winda-card');
   const stamp=byId('winda-stamp');
   if(!valid(d)||!d.periods?.['10']){
     card.className='panel overview-card winda-card tone-neutral';
     stamp.textContent='881001.WI · PE数据待核实';
     content.innerHTML='<div class="score-line"><strong class="score-value">—</strong><span class="score-unit">历史分位</span></div>'+
       '<div class="valuation-status">暂无有效估值</div>'+
       '<p class="asset-footnote">不能用全A等权PE代替Wind全A</p>'+
       '<a class="winda-card-link" href="#winda-panel">查看估值图</a>';
     return;
   }
   const rank=d.periods['10'].percentile;
   const [label,tone]=cls(rank);
   card.className='panel overview-card winda-card tone-'+tone;
   stamp.textContent='881001.WI · 数据 '+d.date+(d.stale?' · 更新滞后':'');
   content.innerHTML='<div class="score-line"><strong class="score-value">'+fmt(rank)+
     '<small class="winda-score-unit">%</small></strong><span class="score-unit">10年ERP分位</span></div>'+
     '<div class="valuation-status">'+label+'</div>'+
     '<div class="asset-main-metric"><span>股债风险溢价</span><b>'+fmt(d.erp)+'%</b></div>'+
     '<p class="asset-footnote">PE '+fmt(d.pe)+'倍 · 10Y国债 '+fmt(d.yield10)+'%</p>'+
     '<a class="winda-card-link" href="#winda-panel">查看估值图</a>';
 }
 function empty(reason){
   byId('winda-current').className='history-current tone-neutral';
   byId('winda-current').innerHTML='<div class="history-empty">'+escape(reason)+'</div>';
   byId('winda-chart').innerHTML='<div class="history-empty">缺少可核验历史数据，暂不绘制估值曲线。</div>';
   byId('winda-hover').textContent='';
   byId('winda-legend').textContent='';
   byId('winda-frequency').textContent='指数：881001.WI · 不使用替代指数数据';
   byId('winda-note').textContent='真实指数PE-TTM与国债收益率匹配后才会展示股债风险溢价。';
 }
 function render(d){
   saved=d;
   cardView(d);
   panel.querySelectorAll('[data-winda-years]').forEach(btn=>{
     const selected=Number(btn.dataset.windaYears)===state.years;
     btn.classList.toggle('active',selected);
     btn.setAttribute('aria-pressed',String(selected));
   });
   const p=d?.periods?.[String(state.years)];
   if(!valid(d)||!p||!Array.isArray(d.points)||
     bands.some(b=>typeof p[b[0]]!=='number'||!Number.isFinite(p[b[0]]))||
     !Number.isFinite(p.percentile)){
     empty(d?.reason||'万得全A所选区间真实估值样本暂不可用');
     return;
   }
   const now=dateMs(d.date),from=new Date(now);
   from.setUTCFullYear(from.getUTCFullYear()-state.years);
   const raw=d.points.map(row=>({date:String(row[0]),t:dateMs(row[0]),v:Number(row[1])}))
     .filter(a=>Number.isFinite(a.t)&&Number.isFinite(a.v)&&a.t>=from.getTime()&&a.t<=now)
     .sort((a,b)=>a.t-b.t);
   if(raw.length<20){empty('该年限的真实历史观测不足');return;}
   const [name,tone]=cls(p.percentile);
   byId('winda-current').className='history-current tone-'+tone;
   byId('winda-current').innerHTML=
     '<div class="history-metric"><span>当前ERP</span><strong>'+fmt(d.erp)+'%</strong></div>'+
     '<div class="history-metric"><span>近'+state.years+'年分位</span><strong>'+fmt(p.percentile)+'%</strong></div>'+
     '<div class="history-state"><span>当前估值判断</span><strong>'+name+'</strong></div>'+
     '<p class="history-asof">观测日期：'+escape(d.date)+' · '+escape(d.code)+'</p>';
   byId('winda-frequency').textContent='真实ERP周线 · 近'+state.years+'年分位参考 · 截止'+p.referenceDate;
   byId('winda-note').textContent=p.sampleCount+'个日度真实观测 · ERP＝100÷指数PE-TTM－10年国债收益率 · 不等于中证全指';
   byId('winda-legend').innerHTML=
     '<span class="legend-item"><i class="legend-line" style="--line:#3769d2;--dash:none"></i>ERP真实走势</span>'+
     bands.map(([id,label,color])=>
       '<span class="legend-item"><i class="legend-line" style="--line:'+color+'"></i>'+label+' '+fmt(p[id])+'%</span>').join('');
   const W=860,H=304,L=55,R=43,T=23,B=40,PW=W-L-R,PH=H-T-B;
   const data=raw.map(x=>x.v).concat(bands.map(a=>p[a[0]]));
   const lo=Math.min(...data),hi=Math.max(...data),pad=Math.max(.15,(hi-lo)*.1);
   const ymin=lo-pad,ymax=hi+pad;
   const x=t=>L+(t-raw[0].t)/Math.max(1,raw[raw.length-1].t-raw[0].t)*PW;
   const y=v=>T+(ymax-v)/Math.max(.01,ymax-ymin)*PH;
   const path=raw.map((a,i)=>(i?'L':'M')+x(a.t).toFixed(2)+' '+y(a.v).toFixed(2)).join(' ');
   let svg='<svg class="history-svg" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="万得全A真实股债风险溢价走势图">';
   for(let i=0;i<5;i++){
     const v=ymin+(ymax-ymin)*i/4;
     const yy=y(v);
     svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy.toFixed(2)+'" y2="'+yy.toFixed(2)+
       '" stroke="#e5ebf2"/><text x="'+(L-8)+'" y="'+(yy+4).toFixed(2)+
       '" text-anchor="end" fill="#8b98aa" font-size="11">'+fmt(v)+'</text>';
   }
   for(const [id,,color] of bands){
     const yy=y(p[id]).toFixed(2);
     svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+
       '" stroke="'+color+'" stroke-width="1.7" stroke-dasharray="5 4"/>';
   }
   svg+='<path d="'+path+'" stroke="#3769d2" stroke-width="2.5" fill="none" stroke-linejoin="round"/>';
   const last=raw[raw.length-1];
   svg+='<circle cx="'+x(last.t).toFixed(2)+'" cy="'+y(last.v).toFixed(2)+
     '" r="5.5" fill="#3769d2" stroke="#fff" stroke-width="2"/>';
   svg+='<text x="'+L+'" y="'+(H-10)+'" fill="#8b98aa" font-size="11">'+raw[0].date.slice(0,7)+'</text>'+
     '<text x="'+(W-R)+'" y="'+(H-10)+'" text-anchor="end" fill="#8b98aa" font-size="11">'+last.date.slice(0,7)+'</text>'+
     '<line id="winda-guide" x1="0" x2="0" y1="'+T+'" y2="'+(H-B)+
     '" stroke="#6b89b8" stroke-dasharray="4 3" visibility="hidden"/>'+
     '<rect x="'+L+'" y="'+T+'" width="'+PW+'" height="'+PH+'" fill="transparent"/></svg>';
   const host=byId('winda-chart');host.innerHTML=svg;
   byId('winda-hover').textContent='鼠标移动或点击曲线查看历史ERP';
   const plot=host.querySelector('svg');
   const cursor=host.querySelector('#winda-guide');
   if(!plot||!cursor)return;
   function peek(e){
     const rect=plot.getBoundingClientRect();
     if(!rect.width)return;
     const pos=(e.clientX-rect.left)*W/rect.width;
     if(pos<L||pos>W-R)return;
     const date=raw[0].t+(pos-L)/PW*(last.t-raw[0].t);
     let nearest=raw[0];
     for(const a of raw)if(Math.abs(a.t-date)<Math.abs(nearest.t-date))nearest=a;
     const cx=x(nearest.t).toFixed(2);
     cursor.setAttribute('x1',cx);cursor.setAttribute('x2',cx);
     cursor.setAttribute('visibility','visible');
     byId('winda-hover').textContent=nearest.date+' · ERP '+fmt(nearest.v)+'%';
   }
   plot.addEventListener('pointermove',peek);
   plot.addEventListener('pointerdown',peek);
   plot.addEventListener('pointerleave',()=>cursor.setAttribute('visibility','hidden'));
 }
 panel.addEventListener('click',e=>{
   const button=e.target.closest('[data-winda-years]');
   if(!button)return;
   const n=Number(button.dataset.windaYears);
   if(![3,5,10].includes(n))return;
   state.years=n;render(saved);
   if(window.refreshValuationJump)window.refreshValuationJump();
 });
 window.renderWindAllA=render;
})();
