/* VIEW: builds HTML from the model. It never changes state. */
const RiskView={
res(){
 const r=st.r,R=vd.risk,rk=R.rank,M=R.match;
 const crit=x=>Object.entries(x.criteria).map(([k,c])=>`<li><b>${e(k.replace(/_/g," "))}</b> ${c.score} (${c.weight_percent}%): ${e(c.explanation)}</li>`).join("");
 return`<h3>Results</h3><dl><dt>Scenario</dt><dd>${r.o2}% O₂, ${r.p} kPa, ${r.g} g${r.mat?", "+e(r.mat):""}</dd>
 <dt>Matching evidence</dt><dd>${M.length?`<b>${M.length}</b> investigation${M.length>1?"s":""} with conditions overlapping the scenario (±${TOL.o2} points O₂, ±${TOL.p} kPa, ±${TOL.g} g): ${M.map(i=>`<a href="investigations.html" data-a="view" data-v="${e(i.id)}" style="color:var(--steel)">${e(i.id)}</a>`).join(", ")}`:"None. No investigation with usable oxygen, pressure and gravity values overlaps these conditions. Files with missing values or unknown units cannot be matched."}</dd>
 <dt>Limits</dt><dd>${e(rk.disclaimer)}</dd></dl>
 <h3>Most relevant investigations: ${e(rk.category_label)}</h3>${rk.ranked.length?`<table><tr><th>Rank</th><th>Investigation</th><th>Score (0–100)</th><th>Why</th></tr>${rk.ranked.map(x=>`<tr><td>${x.rank}</td><td><a href="investigations.html" data-a="view" data-v="${e(x.id)}" style="color:var(--steel)">${e(x.id)}</a><br><span style="color:var(--dim)">${e(x.name)}</span></td><td>${x.score}</td><td><details><summary>Criteria</summary><ul class="uses" style="padding-left:18px">${crit(x)}</ul></details></td></tr>`).join("")}</table>`:'<p class="sub">No investigations to rank.</p>'}
 <p class="note">Scores are application-generated from the CSV contents with the weights shown in each criterion (${Object.entries(rk.weights_percent).map(([k,v])=>k.replace(/_/g," ")+" "+v+"%").join(", ")}).</p>
 <h3>AI fire safety insights</h3>${RiskView.insights()}`},
insights(){
 const R=vd.risk,i=R.ins,r=st.r;
 const form=`<div class="row"><label class="f">Topic<select id="rtopic">${optKV(R.topics,r.topic)}</select></label><button class="btn" data-a="insight">Generate insights</button></div>`;
 if(!i)return form+'<p class="note">Asks the backend AI for insights on the topic from the matching experiment records and source passages.</p>';
 if(i.loading)return form+'<p class="sub">Generating insights…</p>';
 if(i.err)return form+errMsg(i.err);
 if(!i.res.answerable)return form+`<p>${e(i.res.message)}</p>`;
 return form+`<p class="note">${i.scoped?"Based on the matching investigations.":"Based on all investigations (none matched the scenario)."}</p>`+md(i.res.answer)+sourcesHtml(i.res)},
render(){
 const r=st.r,R=vd.risk;
 const o2s=R.stats.condition_ranges_normalized.oxygen,lo=Math.floor(Math.min(o2s?o2s.min:21,21,r.o2)),hi=Math.ceil(Math.max(o2s?o2s.max:85,21,r.o2));
 const envs=Object.entries(R.envs).map(([k,v])=>({key:k,label:v.label}));
 return`<h2>Fire risk analysis</h2><p class="sub">Scenario explorer. The settings alone do not determine fire risk; the result depends on matching evidence.</p>
 <div class="row"><label class="f">Reference environment<select id="renv">${optKV(envs,r.env)}</select></label><label class="f">Relevance category<select id="rcat">${optKV(R.cats,r.cat)}</select></label>
 <label class="f">Gravity (g)<input id="rg" type="number" step="0.001" min="0" value="${r.g}" style="width:100px;min-width:100px"></label>
 <label class="f">Oxygen: <span id="ro2v">${r.o2}%</span><input id="ro2" type="range" min="${lo}" max="${hi}" step="0.5" value="${r.o2}"></label><label class="f">Pressure (kPa)<input id="rp" type="number" value="${r.p}" style="width:100px;min-width:100px"></label>
 <label class="f">Material<select id="rmat">${opt((R.stats.materials||[]).map(x=>x.value),r.mat,"Any")}</select></label><button class="btn on" data-a="analyze">Analyze scenario</button></div>
 <p class="note">Reference environment values are served by the backend and are configurable assumptions there; choosing one fills the fields, which you can edit.</p>${r.go&&R.rank?RiskView.res():""}`}
};
RiskView.showO2=v=>{$("ro2v").textContent=v+"%"};
