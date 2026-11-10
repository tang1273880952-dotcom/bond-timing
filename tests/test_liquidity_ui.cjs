"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const html = fs.readFileSync("liquidity.html", "utf8");
const js = html.split("<script>")[1].split("</script>")[0];
const el = {};
const sandbox = {
  document: {getElementById: id => (el[id] ||= {innerHTML:"",textContent:"",disabled:false,className:"",querySelectorAll:()=>[]})},
  fetch: async () => ({ok:false,status:404}),
  Intl, Date, console
};
vm.createContext(sandbox);
vm.runInContext(js, sandbox);
vm.runInContext('usToday = () => "2026-11-10";', sandbox);
assert.equal(vm.runInContext('businessDaysSince("2026-11-05")',sandbox),3);
assert.equal(vm.runInContext('freshness({freq:"daily"},"2026-11-05").stale',sandbox),false);
assert.equal(vm.runInContext('freshness({freq:"daily"},"2026-10-29").stale',sandbox),true);
assert.equal(vm.runInContext('freshness({freq:"weekly"},"2026-11-04").stale',sandbox),false);
const funding=vm.runInContext('grade({key:"FUNDING_SPREAD",freq:"daily"},{last:{date:"2026-11-05",value:0.02}})',sandbox);
assert.equal(funding.color,"good","2 bp is not automatically severe even at the 94th percentile");
vm.runInContext('data={series:{HY_OAS:[{date:"2026-08-06",value:2.71},{date:"2026-11-05",value:3.48}],RESERVES:[{date:"2026-08-05",value:2993349},{date:"2026-11-04",value:2930088}]}}',sandbox);
const hy=vm.runInContext('grade({key:"HY_OAS",freq:"daily"},{last:{date:"2026-11-05",value:3.48}})',sandbox);
assert.equal(hy.color,"warn","13 week credit spread widening matters");
const reserves=vm.runInContext('grade({key:"RESERVES",freq:"weekly"},{last:{date:"2026-11-04",value:2930088}})',sandbox);
assert.equal(reserves.color,"good","historically low reserves alone are not proof of crisis");
console.log("PASS: US-business-day freshness and independent stress classification");
