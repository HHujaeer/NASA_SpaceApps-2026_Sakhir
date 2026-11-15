/* VIEW: builds HTML from the model. It never changes state. */
const CompareView={
render(){
 const A=vd.cmp.items,c=st.cmp;
 if(A.length<2)return`<h2>Compare experiments</h2><p class="sub">At least two investigations are needed. The backend currently has ${A.length}.</p>`;
 const o=s=>A.map(i=>`<option value="${e(i.id)}" ${i.id===s?"selected":""}>${e(i.id)}: ${e(i.title)}</option>`).join(""),M=compareMeasures();
 if(!M.includes(c.m))c.m=M[0]||"";
 const form=`<h2>Compare experiments</h2><p class="sub">Pick two investigations${M.length?" and one measurement":""}</p><div class="row"><label class="f">Investigation A<select id="ca">${o(c.a)}</select></label><label class="f">Investigation B<select id="cb">${o(c.b)}</select></label>${M.length?`<label class="f">Measurement<select id="cm">${opt(M,c.m)}</select></label>`:""}<label class="f">AI explanation<span><input type="checkbox" id="cx" ${c.ex?"checked":""} style="min-width:0"> include</span></label><button class="btn on" data-a="gen">Generate comparison</button></div>`;
 if(vd.cmp.err)return form+errMsg(vd.cmp.err);
 return form+(c.go&&vd.cmp.res?CompareView.result():"")},
result(){
 const{res,da,db}=vd.cmp,m=st.cmp.m,inv=[da,db],rows=inv.flatMap((i,k)=>i.runs.length?i.runs.map(r=>({i,r,k})):[{i,r:null,k}]);
 const tagOf=Object.fromEntries(res.investigations.map(x=>[x.tag,x.id])),ul=a=>a.length?`<ul class="uses" style="padding-left:18px">${a.map(x=>`<li>${e(x)}</li>`).join("")}</ul>`:'<p class="sub">None.</p>';
 const sm=res.results.shared_measurements,smk=Object.keys(sm),F=res.results.findings_text;
 const ex=res.explanation;
 return`<h3>Numerical comparison</h3><table><tr><th>Investigation</th><th>Gravity</th><th>Material</th><th>O₂ %</th><th>Pressure kPa</th><th>${e(m||"Measurement")}</th></tr>${rows.map(x=>`<tr><td>${e(x.i.id)}</td><td>${e(nr(x.i.grav))}</td><td>${e(nr(x.i.mat))}</td><td>${x.r?fm(x.r.o2):"—"}</td><td>${x.r?fm(x.r.p):"—"}</td><td>${x.r?fm(m?x.r.m[m]:null):"No records"}</td></tr>`).join("")}</table>${rows.some(x=>x.i.total>x.i.runs.length)?'<p class="note">Large files are shown partially.</p>':""}
 ${m?`<h3>Comparison chart</h3>${bars(rows.filter(x=>x.r).map(x=>({l:x.i.id.slice(0,8)+" "+(x.r.o2!=null?x.r.o2+"%":""),v:x.r.m[m],c:x.k?"pt2":"pt"})),m)}`:""}
 <h3>Similarities</h3>${ul(res.similarities)}<h3>Differences</h3>${ul(res.differences)}<h3>Not reported or not comparable</h3>${ul(res.not_available)}
 ${smk.length?`<h3>Measurements both files report</h3><table><tr><th>Column</th>${res.investigations.map(x=>`<th>${e(x.id)} (min – max, mean)</th>`).join("")}</tr>${smk.map(k=>`<tr><td>${e(k)}</td>${res.investigations.map(x=>{const s=sm[k][x.tag];return`<td>${s?s.min+" – "+s.max+", "+(+s.mean.toFixed(4)):"—"}</td>`}).join("")}</tr>`).join("")}</table>`:""}
 ${Object.keys(F).length?`<h3>Reported findings</h3>${Object.keys(F).map(t=>`<p><b>${e(tagOf[t]||t)}:</b> ${e(F[t].join("; "))}</p>`).join("")}`:""}
 ${ex?`<h3>AI explanation</h3>${ex.status==="ok"?md(ex.text)+`<span class="note">${e(ex.label)}${ex.context_truncated?" Some data was left out because of the context limit.":""}</span>`:errMsg(ex.error)}`:""}
 <p class="note">${e(res.note)}</p>`}
};
