/* MODEL: scenario analysis. Reference environments, relevance ranking and matching investigations all come from the backend. */
async function loadRisk(){
 const[stats,cats,topics,envs]=await Promise.all([Data.stats(),Data.cats(),Data.topics(),Data.envs()]);
 const r=st.r;
 if(!cats.some(c=>c.key===r.cat))r.cat=(cats[0]||{}).key||"";
 if(!topics.some(t=>t.key===r.topic))r.topic=(topics[0]||{}).key||"";
 if(!envs[r.env]){r.env=Object.keys(envs)[0]||"";if(r.env)applyEnvironment(r.env,envs)}
 const prev=vd.risk&&vd.risk.ins;
 vd.risk={stats,cats,topics,envs,rank:null,match:null,ins:prev};
 if(!r.go||!r.cat)return;
 const[rank,match]=await Promise.all([
  API.get("/rankings",{category:r.cat,limit:6}),
  API.get("/investigations",{min_oxygen:r.o2-TOL.o2,max_oxygen:r.o2+TOL.o2,min_pressure_kpa:r.p-TOL.p,max_pressure_kpa:r.p+TOL.p,
   min_gravity_g:Math.max(0,r.g-TOL.g),max_gravity_g:r.g+TOL.g,fuel:r.mat})]);
 vd.risk.rank=rank.data;vd.risk.match=match.data.map(p=>adapt(p));vd.risk.unreadable=match.meta.unreadable_files||[]}
function applyEnvironment(k,envs){const E=(envs||vd.risk.envs)[k];if(E)Object.assign(st.r,{env:k,o2:E.oxygen_pct,p:E.pressure_kpa,g:E.gravity_g,go:false})}
/* AI fire-safety insights on a topic, limited to the matching investigations when there are any (POST /api/insights). */
async function generateInsights(){
 const m=(vd.risk.match||[]).map(i=>i.id);vd.risk.ins={loading:true};
 try{vd.risk.ins={res:(await API.post("/insights",{topic:st.r.topic,investigation_ids:m.length?m:undefined})).data,scoped:m.length>0}}
 catch(x){vd.risk.ins={err:x}}}
