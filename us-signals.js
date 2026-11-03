/* Source-backed S&P 500 buy/trim watch (not an automatic trading system). */
(() => {
  'use strict';
  const root=document.getElementById('sp500-signals-panel');
  if(!root)return;
  const el=id=>document.getElementById('signal-'+id);
  const labels={
    erp:['ERP估值','30分'],vix:['VIX恐慌','15分'],rsi:['RSI动能','15分'],
    breadth:['市场宽度','15分'],credit:['信用利差','15分'],trend:['均线趋势','10分']
  };
  const keys=Object.keys(labels);
  const fmt=n=>Number(n).toFixed(2);
  const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  })[c]);
  function failure(message){
    el('summary').innerHTML='<div class="signal-unavailable">'+safe(message)+'</div>';
    el('items').innerHTML=keys.map(k=>'<div class="signal-factor missing"><b>'+labels[k][0]+
      '</b><span>数据待核验</span></div>').join('');
    el('confirm').textContent='止跌确认：暂无可核验的完整信号';
    el('chart').innerHTML='';
    el('status').textContent='数据缺失或过期时不显示模拟买卖点';
  }
  function render(data,status){
    const parsed=Date.parse(String(data?.asof||'')+'T00:00:00Z');
    const stale=Number.isFinite(parsed) ? Date.now()-parsed>9*86400000 : true;
    const recentOk=data?.valid===true&&data?.mode==='sp500-signals-v1'&&
      typeof data.score==='number'&&data.score>=0&&data.score<=100&&
      data.coveredWeight>=70&&Array.isArray(data.priceHistory)&&data.priceHistory.length>40;
    if(!recentOk){
      failure(data?.reason||'尚未取得足够的标普500免费市场指标数据');
      return;
    }
    const statusFail=status?.success===false;
    const usable=!stale&&!statusFail;
    const tone=usable?(['cheap','watch','neutral','caution','rich'].includes(data.tone)?data.tone:'neutral'):'neutral';
    const action=usable?data.action:'仅供历史参考，停止输出新买卖信号';
    root.dataset.tone=tone;
    el('summary').innerHTML='<div class="signal-stat"><span>买入吸引力（可用指标折算）</span>'+
      '<strong>'+Math.round(data.score)+'<small>/100</small></strong>'+
      '<span class="signal-state">'+safe(action)+'</span></div>'+
      '<div class="signal-stat"><span>止跌确认</span><strong>'+Number(data.confirmed||0)+
      '<small>/3</small></strong><span class="signal-state">'+
      (data.riskVeto?'信用或恐慌风险过滤已触发':'未触发重大风险过滤')+
      '</span></div>'+
      '<div class="signal-stat"><span>有效数据覆盖</span><strong>'+Number(data.coveredWeight)+
      '<small>/100分权重</small></strong><span class="signal-state">未验证指标不计分</span></div>';
    const indicators=data.indicators||{};
    el('items').innerHTML=keys.map(k=>{
      const d=indicators[k],title=labels[k][0],total=Number(d?.weight||0);
      if(d?.value===null||!d||d.score===null){
        return '<div class="signal-factor missing"><div class="signal-factor-top"><b>'+title+
          '</b><span>待接入</span></div><span class="signal-value">—</span>'+
          '<div class="signal-track"></div><small>'+safe(d?.source||'真实数据未验证')+'</small></div>';
      }
      const ratio=Math.min(100,Math.max(0,Number(d.score)/Math.max(1,total)*100));
      const val=fmt(d.value)+(d.unit==='点'?' 点':d.unit||'');
      return '<div class="signal-factor"><div class="signal-factor-top"><b>'+title+
        '</b><span>'+fmt(d.score)+'/'+total+'分</span></div>'+
        '<span class="signal-value">'+val+'</span>'+
        '<div class="signal-track"><div style="width:'+ratio.toFixed(1)+'%"></div></div>'+
        '<small>'+safe(d.date||'暂无日期')+'</small></div>';
    }).join('');
    el('confirm').innerHTML=(data.confirmations||[]).map(item=>
      '<span class="signal-gate '+(item.met?'met':'')+'">'+(item.met?'● ':'○ ')+
      safe(item.name)+'</span>').join('');
    el('status').textContent='截至 '+safe(data.asof)+
      ' · ERP估值是月度数据，其余是日度收盘 · 评分阈值未回测 · '+
      (statusFail?'最近一次数据刷新失败，显示旧记录':stale?'行情已过期': '仅供观察，不是交易指令');
    const points=data.priceHistory.map(v=>({date:String(v[0]),value:Number(v[1])}))
      .filter(v=>Number.isFinite(v.value)&&v.value>0);
    if(points.length<40){el('chart').innerHTML='';return;}
    const W=940,H=235,L=48,R=18,T=15,B=36,pw=W-L-R,ph=H-T-B;
    const values=points.map(p=>p.value),lo=Math.min(...values),hi=Math.max(...values);
    const pad=Math.max(10,(hi-lo)*.08),bottom=lo-pad,top=hi+pad;
    const x=i=>L+i/Math.max(1,points.length-1)*pw;
    const y=v=>T+(top-v)/(top-bottom)*ph;
    const line=points.map((p,i)=>(i?'L':'M')+x(i).toFixed(1)+' '+y(p.value).toFixed(1)).join(' ');
    const ma50=data.indicators?.trend?.ma50,ma200=data.indicators?.trend?.ma200;
    let svg='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="标普500最近一年实际日度指数收盘价走势">';
    for(let i=0;i<4;i++){
      const gy=T+i*ph/3;
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+gy+'" y2="'+gy+
        '" stroke="#e1e9f3"/><text x="'+(L-8)+'" y="'+(gy+3)+'" text-anchor="end" font-size="11" fill="#8e99ab">'+
        (top-(top-bottom)*i/3).toFixed(0)+'</text>';
    }
    for(const [name,value,color] of [['MA50',ma50,'#54a07d'],['MA200',ma200,'#b487b8']]){
      if(!Number.isFinite(value)||value<bottom||value>top)continue;
      const yy=y(value).toFixed(1);
      svg+='<line x1="'+L+'" x2="'+(W-R)+'" y1="'+yy+'" y2="'+yy+
        '" stroke="'+color+'" stroke-dasharray="5 4" stroke-width="1.6"/>';
    }
    svg+='<path d="'+line+'" stroke="#356bd4" stroke-width="2.3" fill="none" stroke-linejoin="round"/>'+
      '<circle cx="'+x(points.length-1).toFixed(1)+'" cy="'+y(points.at(-1).value).toFixed(1)+
      '" r="5" fill="#356bd4" stroke="#fff" stroke-width="2"/>'+
      '<text x="'+L+'" y="'+(H-10)+'" font-size="11" fill="#8493aa">'+safe(points[0].date.slice(0,7))+'</text>'+
      '<text x="'+(W-R)+'" y="'+(H-10)+'" text-anchor="end" font-size="11" fill="#8493aa">'+
      safe(points.at(-1).date.slice(0,7))+'</text></svg>';
    el('chart').innerHTML=svg;
  }
  window.renderUSSignals=render;
})();
