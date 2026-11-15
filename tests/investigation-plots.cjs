const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ctx=vm.createContext({console,window:{},st:{dm:'',dx:''}});
vm.runInContext(fs.readFileSync('js/models/records.js','utf8'),ctx);
// Synthetic records: no missing values, approximate values, mixed units or constant inputs may create phantom choices.
ctx.p={id:'synthetic',columns:['O2_pct','Initial diameter (mm)','Burn Time (s)','No values','Mixed units','Test #'],detected_fields:{oxygen:'O2_pct'},conditions:{oxygen:{type:'numeric',min:20,max:21}},measurements:{'Burn Time (s)':{},'No values':{},'Mixed units':{}},source_references:{values:[]}};
ctx.records=[{row_number:1,values:{O2_pct:'20','Initial diameter (mm)':'1','Burn Time (s)':'5 s','No values':null,'Mixed units':'1 cm','Test #':'1'}},{row_number:2,values:{O2_pct:'21','Initial diameter (mm)':'2','Burn Time (s)':'10 s','No values':null,'Mixed units':'2 mm','Test #':'2'}}];
ctx.i=vm.runInContext('adapt(p,records)',ctx);
assert.equal(ctx.i.plots.length,2);
assert.ok(ctx.i.plots.every(p=>p.y==='Burn Time (s)'&&p.points.length===2));
vm.runInContext('st.dx="O2_pct";st.dm="No values";selectInvestigationPlot(i)',ctx);
assert.equal(ctx.st.dm,'Burn Time (s)');
ctx.i.runs[1].raw.O2_pct='20';ctx.i.runs[1].raw['Initial diameter (mm)']='1';
assert.equal(vm.runInContext('investigationPlots(p,i.runs).length',ctx),0);
// Optional API profile fixture allows the same checks against actual investigations.
if(process.argv[2]){
 const profiles=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 for(const profile of profiles){
  ctx.p=profile;ctx.records=profile.records;ctx.i=vm.runInContext('adapt(p,records)',ctx);
  const selected=vm.runInContext('st.dx="stale";st.dm="stale";selectInvestigationPlot(i)',ctx);
  assert.ok(selected&&selected.points.length>=2);
  assert.ok(ctx.i.plots.every(p=>p.x!==p.y&&new Set(p.points.map(v=>v.x)).size>=2));
  if(profile.id==='PSI-69')assert.match(selected.x,/droplet initial diameter/i);
  if(profile.id==='PSI-99'){assert.equal(selected.x,'Material');assert.equal(selected.y,'Burn Time (s)');assert.equal(selected.points.length,3)}
  console.log(profile.id+': '+selected.x+' → '+selected.y+' ('+selected.points.length+' paired records)');
 }
}
console.log('Plot eligibility checks passed.');
