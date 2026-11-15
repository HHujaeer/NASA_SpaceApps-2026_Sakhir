/* MODEL: numbers for the overview page, built from /api/statistics and every investigation's records. */
async function loadOverview(){
 const[stats,cat]=await Promise.all([Data.stats(),Data.catalog()]);
 const dets=await Promise.all(cat.items.map(i=>Data.detail(i.id)));
 const cnt=new Map();dets.forEach(d=>[...new Set(d.plots.filter(p=>p.x===d.oxygenColumn).map(p=>p.y))].forEach(k=>cnt.set(k,(cnt.get(k)||0)+1)));
 const meas=[...cnt].sort((a,b)=>b[1]-a[1]).map(x=>x[0]);
 if(!meas.includes(st.ov.m))st.ov.m=meas[0]||"";
 vd.ov={stats,items:cat.items,dets,meas,unreadable:cat.unreadable}}
function overviewSummary(){
 const o=vd.ov,m=st.ov.m,s=o.stats,R=o.dets.flatMap(d=>d.runs.map(r=>({...r,inv:d,y:r.m[m]})));
 return{items:o.items,R,m,meas:o.meas,unreadable:o.unreadable,
  truncated:o.dets.some(d=>d.total>d.runs.length),
  top:R.filter(r=>r.y!=null).sort((a,b)=>b.y-a.y).slice(0,5),
  recent:[...o.items].sort((a,b)=>(b.modified||"").localeCompare(a.modified||"")).slice(0,5),
  stats:[[s.investigation_count,"Investigations"],[s.total_records,"Experimental records"],[s.materials.length,"Materials"],
   [s.average_completeness==null?"—":Math.round(s.average_completeness*100)+"%","Average data completeness"]]}}
