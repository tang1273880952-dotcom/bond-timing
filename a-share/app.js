"use strict";
const $=x=>document.getElementById(x),repo="tang1273880952-dotcom/bond-timing";
let market={mode:"pending",stocks:[],top:[],history:{},coverage:{}},user={positions:[],watch:[]};
let mode="top",sort="balanced",query="";
const addUrl="https://github.com/"+repo+"/issues/new?template=holding.yml";
const fmt=(n,d=2)=>n===null||n===undefined||n===""?"—":Number.isFinite(Number(n))?Number(n).toLocaleString("zh-CN",{minimumFractionDigits:d,maximumFractionDigits:d}):"—";
const safe=x=>String(x??"").replace(/[&<>"']/g,k=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[k]));
const normal=x=>/^\d{6}$/.test(String(x||"").trim())?String(x).trim():"";
const num=x=>x===null||x===undefined||x===""?null:(Number.isFinite(Number(x))?Number(x):null);
const asset=code=>(market.stocks||[]).find(s=>s.code===code)||{code,name:"未同步的股票",score:null};
function qualityWord(s){
 if(s.score===null||s.score===undefined)return {label:"数据不足 · 待复核",tone:"warn"};
 if(s.flag)return {label:"风险复核 · 暂不入选",tone:"warn"};
 if(s.score>=85)return {label:"优先研究，观察分批条件",tone:"good"};
 if(s.score>=70)return {label:"可以重点关注",tone:"good"};
 if(s.score>=55)return {label:"继续观察估值与财报",tone:""};
 return {label:"暂不新增 · 核查风险",tone:"warn"};
}
function holdingAdvice(s){
 if(s.score===null||s.score===undefined)return "持仓继续跟踪中，缺少核验过的财报/估值数据，暂不能作买卖判断。";
 if(s.flag)return "发现基本面或数据风险标记，建议先核对原因，再评估是否降低风险敞口。";
 if(s.score>=70)return "估值与质量评分较好，持有者仍应检查原定仓位、持有期限和盈利预期。";
 if(s.score>=50)return "继续观察：暂不足以仅凭评分作出卖出判断。";
 return "估值性价比或企业质量偏弱：关注止盈、仓位和财务恶化，但不代表必须卖出。";
}
function title(s,extra=""){
 let a=qualityWord(s);
 let text='<div class="stock-head"><div><div class="stock-title">'+safe(s.name)+' <span class="stock-code">'+safe(s.code)+'</span></div>'+
 (extra?'<div class="stock-code">'+safe(extra)+'</div>':'')+'</div><div class="score">'+(s.score===null||s.score===undefined?'—':fmt(s.score,0))+'<small>/100</small></div></div>';
 return text+'<div class="metrics"><div class="metric"><span>当前价格</span><strong>'+(num(s.price)!==null?fmt(s.price):'待同步')+'</strong></div><div class="metric"><span>市净率 PB</span><strong>'+fmt(s.pb)+'倍</strong></div><div class="metric"><span>历史PB分位</span><strong>'+(num(s.pbPct)!==null?fmt(s.pbPct,0)+'%':'待采集')+'</strong></div></div>'+
 '<div class="msg '+a.tone+'">'+safe(a.label)+'</div>';
}
function stockCard(s,extra="",holding=false){
 const ele=document.createElement("article");ele.className="stock";ele.tabIndex=0;
 const own=holding?'<div class="msg">'+safe(holdingAdvice(s))+'</div>':"";
 ele.innerHTML=title(s,extra)+own;
 ele.addEventListener("click",()=>openDetail(s.code));
 ele.addEventListener("keydown",e=>{if(e.key==="Enter"){openDetail(s.code)}});
 return ele;
}
function appendCards(target,items,extraFn,held=false){
 const el=$(target);el.textContent="";
 if(!items.length){el.innerHTML='<div class="empty">当前没有符合条件的已核验股票。历史行情或财报尚未就绪时，系统不会虚构评分。</div>';return}
 for(const [i,s] of items.entries())el.appendChild(stockCard(s,extraFn?extraFn(s,i):"",held));
}
function topList(){
 const list=(market.stocks||[]).filter(s=>num(s.score)!==null&&!s.flag);
 const key={balanced:"score",value:"valuationScore",quality:"qualityScore",growth:"growthScore"}[sort]||"score";
 list.sort((a,b)=>(num(b[key])??-1)-(num(a[key])??-1));
 return list.slice(0,10);
}
function renderTop(){
 const c=market.coverage||{};let ranked=topList();
 $("count").textContent=ranked.length+"只精选";
 $("coverage").textContent="本次估值扫描 "+(c.market||0)+" 只，已取得有效估值 "+(c.scanned||0)+" 只；财务评分核验 "+(c.qualityVerified||0)+" 只。"+(market.mode==="live"?"":" 当前为待同步/部分数据状态。")+" 排名只在已核验样本中产生，不等于全市场全部公司已完成财报复核。";
 appendCards("ranking",ranked,(s,i)=>"精选榜 #"+(i+1));
 let q=query.trim().toLowerCase(),res=q?(market.stocks||[]).filter(s=>s.code.includes(q)||String(s.name).toLowerCase().includes(q)).slice(0,25):[];
 $("all-title").textContent=q?'搜索到 '+res.length+' 只（最多显示25只）':'可输入股票代码/名称，查询已扫描的股票。';
 $("all-results").textContent="";
 if(q){if(res.length)for(const s of res)$("all-results").appendChild(stockCard(s));else $("all-results").innerHTML='<div class="empty">尚未扫描到该股票。可先通过 GitHub 表单添加到持仓或观察池，下一轮会优先查询。</div>'}
}
function renderPortfolio(){
 const arr=(user.positions||[]).map(p=>({p,s:asset(p.code)}));
 const node=$("holdings");node.textContent="";
 if(!arr.length){node.innerHTML='<div class="empty">当前持仓池为空。点击右上角「添加 / 修改」，登录 GitHub 并提交股票代码、成本价和持仓股数即可同步到手机与电脑。</div>';return}
 for(const {p,s} of arr){
   const hasprice=num(s.price)!==null,cost=num(p.cost),shares=num(p.shares);
   const pnl=hasprice&&cost!==null&&cost>0?(s.price/cost-1)*100:null;
   const extra="成本 ¥"+fmt(cost)+" · "+fmt(shares,0)+"股"+(pnl===null?"":" · 浮动 "+(pnl>=0?"+":"")+fmt(pnl,1)+"%");
   node.appendChild(stockCard(s,extra,true));
 }
}
function renderWatch(){
 const arr=(user.watch||[]).map(w=>({w,s:asset(typeof w==="string"?w:w.code)}));
 appendCards("watchlist",arr.map(x=>x.s),null,false);
 if(!arr.length)$("watchlist").innerHTML='<div class="empty">观察池为空。通过「添加观察」表单即可保存感兴趣的股票。</div>';
}
function pointNum(v){return Number.isFinite(Number(v))?Number(v):null}
function chart(h){
 const p=(h&&h.points||[]).filter(x=>x&&num(x.price)!==null&&num(x.bps)!==null);
 if(p.length<6)return '<div class="empty">PB历史样本不足，暂不绘制估值带。</div>';
 let vals=[],k=["p10","p25","p50","p75","p90"].filter(x=>num(h[x])!==null);
 for(const x of p){vals.push(x.price);for(const z of k)vals.push(x.bps*Number(h[z]))}
 let low=Math.min(...vals),high=Math.max(...vals); if(!(high>low)){low*=.9;high*=1.1}
 const W=580,H=260,left=38,right=10,top=13,bottom=25,fw=W-left-right,fh=H-top-bottom;
 const X=i=>left+fw*i/(p.length-1),Y=v=>top+fh*(high-v)/(high-low);
 function path(fn){return p.map((d,i)=>(i?'L':'M')+X(i).toFixed(2)+' '+Y(fn(d)).toFixed(2)).join(' ')}
 let lines=[["p10","#319b70"],["p25","#54b89a"],["p50","#bd9849"],["p75","#e39958"],["p90","#d46f68"]];
 let svg='<svg class="pb-svg" viewBox="0 0 '+W+' '+H+'" role="img" aria-label="蓝线为历史股价；其他线为历史PB参考带价格"><rect width="'+W+'" height="'+H+'" rx="9" fill="#f8faff"/>';
 for(let i=0;i<5;i++){const y=top+fh*i/4;let v=high-(high-low)*i/4;svg+='<line x1="'+left+'" y1="'+y+'" x2="'+(W-right)+'" y2="'+y+'" stroke="#dae3f3" stroke-dasharray="3 4"/><text x="3" y="'+(y+4)+'" font-size="10" fill="#77869f">'+v.toFixed(1)+'</text>'}
 for(const [name,color] of lines){if(num(h[name])!==null)svg+='<path d="'+path(d=>d.bps*Number(h[name]))+'" fill="none" stroke="'+color+'" stroke-width="1.8" opacity=".9"/>'}
 svg+='<path d="'+path(d=>d.price)+'" fill="none" stroke="#2d61ce" stroke-width="2.5"/><text x="'+left+'" y="'+(H-6)+'" font-size="10" fill="#8090a7">'+safe(p[0].date)+'</text><text text-anchor="end" x="'+(W-right)+'" y="'+(H-6)+'" font-size="10" fill="#8090a7">'+safe(p.at(-1).date)+'</text></svg>';
 return svg+'<div class="legend">蓝线：股价；绿色：历史低PB带；黄色：中位PB带；红色：历史高PB带。当前PB分位使用已收集的历史样本，历史带使用同一回看期分位，不能作为无前瞻偏差的回测。</div>';
}
function detailsHTML(code){
 const s=asset(code),h=(market.history||{})[code],hold=(user.positions||[]).find(p=>p.code===code);
 let bps=h&&num(h.currentBps),ranges=bps!==null&&h?[
 ["低估参考（PB10%）",bps*Number(h.p10)],["偏低估值（PB25%）",bps*Number(h.p25)],["历史中位（PB50%）",bps*Number(h.p50)],["偏贵观察（PB75%）",bps*Number(h.p75)],["高估观察（PB90%）",bps*Number(h.p90)]
 ]:[];
 let html='<h2>'+safe(s.name)+' <small>'+safe(s.code)+'</small></h2><p class="minor">数据日期 '+safe(s.date||market.marketDate||"未同步")+' · '+safe(s.industry||"行业待确认")+'</p>'+
 '<div class="row"><span>综合评分</span><b>'+((num(s.score)===null)?"暂无已核验评分":fmt(s.score,0)+"/100")+'</b></div>'+
 '<div class="row"><span>当前收盘价</span><b>¥'+fmt(s.price)+'</b></div>'+
 '<div class="row"><span>PE TTM / PB</span><b>'+fmt(s.pe)+' / '+fmt(s.pb)+'</b></div>'+
 '<div class="row"><span>质量 / 估值 / 成长 / 风险</span><b>'+["qualityScore","valuationScore","growthScore","riskScore"].map(k=>fmt(s[k],0)).join(" / ")+'</b></div>'+
 '<div class="row"><span>ROE（报告期）</span><b>'+fmt(s.roe)+'%</b></div>'+
 '<div class="row"><span>净利润同比（报告期）</span><b>'+fmt(s.growth)+'%</b></div>'+
 '<div class="row"><span>经营现金流相关指标</span><b>'+fmt(s.cfoRatio)+'</b></div>'+
 '<div class="row"><span>财报截止日 / 发布日</span><b>'+safe(s.reportDate||"未取得")+' / '+safe(s.pubDate||"未取得")+'</b></div>'+
 '<div class="msg '+qualityWord(s).tone+'">'+safe(hold?holdingAdvice(s):qualityWord(s).label)+'</div>';
 if(s.flag)html+='<p class="flag">风险标记：'+safe(s.flag)+'</p>';
 if(h&&num(h.currentBps)!==null&&Number(h.samples)>=50){
   html+='<h3>PB Band · '+safe(h.start||"")+' 至 '+safe(h.end||"")+'</h3>'+chart(h)+ranges.map(([k,v])=>'<div class="row"><span>'+k+'</span><b>¥'+fmt(v)+'</b></div>').join('')+
    '<p class="minor">当前每股净资产（估算）¥'+fmt(h.currentBps)+'；基于历史PB样本 '+fmt(h.samples,0)+' 条。估值区间不是保证成交价。</p>';
 }else html+='<h3>PB Band</h3><div class="empty">本股票历史PB正在增量采集。不能用缺少历史数据的单点PB推算10年分位或合理股价。</div>';
 html+='<div class="actions"><a class="primary" target="_blank" rel="noopener" href="'+addUrl+'">添加 / 修改持仓</a><button class="mini-btn" data-band="'+safe(code)+'">到PB Band页面</button></div>';
 return html;
}
function openDetail(code){
 if(!normal(code))return;
 $("detail-body").innerHTML=detailsHTML(code);
 const dlg=$("detail");
 if(typeof dlg.showModal==="function"){dlg.showModal()}else dlg.setAttribute("open","");
}
function renderBand(){
 const code=normal($("band-code").value);
 if(!code){$("band-details").innerHTML='<div class="empty">请输入6位沪深A股代码。</div>';return}
 $("band-details").innerHTML=detailsHTML(code);
}
async function load(){
 const t=Date.now(),results=await Promise.allSettled([
 fetch("./data/snapshot.json?t="+t,{cache:"no-store"}),fetch("./data/holdings.json?t="+t,{cache:"no-store"})
 ]);
 for(let i=0;i<results.length;i++){if(results[i].status!=="fulfilled"||!results[i].value.ok)continue;try{const d=await results[i].value.json();if(i===0&&Array.isArray(d.stocks))market=d;if(i===1&&Array.isArray(d.positions))user=d}catch(e){}}
 $("status").textContent="行情日期："+safe(market.marketDate||"待首次更新")+" · 云端更新时间："+safe(market.generatedAt||"未验证")+" · 持仓云端同步："+safe(user.updatedAt||"尚无记录");
 renderTop();renderPortfolio();renderWatch();if(mode==="band")renderBand();
}
function choose(tab){
 if(!$("top")||!$(tab))return;mode=tab;
 document.querySelectorAll(".view").forEach(e=>e.classList.toggle("hidden",e.id!==tab));
 document.querySelectorAll("[data-tab]").forEach(e=>e.classList.toggle("current",e.dataset.tab===tab));
 if(tab==="band")renderBand();
}
$("tabs").addEventListener("click",e=>{const b=e.target.closest("[data-tab]");if(b)choose(b.dataset.tab)});
$("sort").addEventListener("change",e=>{sort=e.target.value;renderTop()});
$("search").addEventListener("input",e=>{query=e.target.value;renderTop()});
$("band-find").addEventListener("click",renderBand);
$("band-code").addEventListener("keydown",e=>{if(e.key==="Enter")renderBand()});
$("detail").addEventListener("click",e=>{if(e.target===$("detail"))$("detail").close();if(e.target.matches("[data-band]")){$("detail").close();$("band-code").value=e.target.dataset.band;choose("band")}});
$("close").onclick=()=>$("detail").close();
$("refresh").onclick=load;
if(window.location.hash){const tab=window.location.hash.slice(1);if(["top","portfolio","watch","band"].includes(tab))choose(tab)}
load();