/* Expired, failed, or unverifiable snapshots cannot issue current signals. */
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes={};
function node(){return {innerHTML:'',textContent:'',className:'',dataset:{},
 classList:{toggle(){}},setAttribute(){},addEventListener(){},
 querySelector(){return null},querySelectorAll(){return []}};}
class Clock extends Date {
 constructor(...args){super(...(args.length?args:['2026-11-02T04:00:00Z']));}
 static now(){return Date.parse('2026-11-02T04:00:00Z');}
}
const ctx={Date:Clock,console,window:{},document:{getElementById(id){return nodes[id]||(nodes[id]=node())}},
 localStorage:{getItem(){return null},setItem(){}},
 fetch:async url=>({ok:true,json:async()=>JSON.parse(fs.readFileSync(String(url).replace(/\?.*$/,''),'utf8'))})};
vm.runInNewContext(fs.readFileSync('app.js','utf8'),ctx);
const health=ctx.window.dataHealth;
const fresh={success:true,attemptAt:'2026-11-02T10:00:00+08:00'};
assert.ok(health('2026-10-30',fresh).ok,'Friday data remains valid on Monday');
assert.ok(health('2026-10-01',fresh,45).ok,'monthly US observations retain their own frequency');
assert.ok(!health('2026-10-01',fresh).ok,'old daily data never looks current');
assert.ok(!health('2026-10-30',{success:true,attemptAt:'2026-10-27T22:00:00+08:00'}).ok,
 'a stopped schedule is detected even if old status says success');
assert.ok(!health('2026-10-30',null).ok,'missing status is not presumed successful');
assert.ok(!health('2026-10-30',{...fresh,success:false}).ok,'failed updates retain explicit warning');
assert.ok(!health('2030-01-01',fresh).ok,'future data is rejected');
setImmediate(()=>{
 const payload=JSON.parse(fs.readFileSync('data/latest.json','utf8'));
 payload.dataDate='2026-10-30';
 payload.assets.forEach(a=>a.score=90);
 vm.runInNewContext('latest='+JSON.stringify(payload)+';syncStatus='+
  JSON.stringify({...fresh,attemptAt:'2026-10-01T22:00:00+08:00'})+';usLatest=null;render();',ctx);
 assert.ok(!nodes.pick.textContent.includes('中证500'),'stale high scores excluded from capital watch');
 assert.ok(nodes.stamp.textContent.includes('多日未更新'),'stopped schedule visible to user');
 assert.ok(nodes.cards.innerHTML.includes('估值分'),'authentic old snapshot remains available as history');
 console.log('PASS: source frequency, stopped schedule, missing status, stale high-score suppression');
});
