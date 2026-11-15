/* MODEL: backend data. Fetch helpers (cached for the life of the page) and adapters that reshape backend profiles/records for the views.
   Nothing here is seed data: every value shown comes from the API. */
const vd={}; /* view data for the current page, filled by that page's loader */
const memo={};
const once=(k,fn)=>memo[k]||(memo[k]=fn().catch(x=>{delete memo[k];throw x}));
const join=a=>(a||[]).join(", ");
const NUM=/^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([%A-Za-z/°µ]*)\s*$/;
const num=v=>{const m=NUM.exec(v==null?"":String(v));return m?+m[1]:null};
/* Factor that turns a column's raw values into the unit the backend normalised it to (1 when it could not normalise). */
const scale=c=>{const n=c&&c.type==="numeric"&&c.normalized;if(!n)return 1;return c.max!==c.min?(n.max-n.min)/(c.max-c.min):(c.max?n.max/c.max:1)};
const r4=x=>x==null?null:+x.toFixed(4);
const cell=(col,cond,vals)=>{if(!col||!cond||cond.type!=="numeric")return null;const x=num(vals[col]);return x==null?null:r4(x*scale(cond))};
/* Range text for a numeric condition, preferring the backend's normalised values. */
const rng=c=>{if(!c||c.type!=="numeric")return"";const n=c.normalized,lo=n?n.min:c.min,hi=n?n.max:c.max,u=n?n.unit:(c.unit||""),f=x=>+x.toFixed(3);
 return(lo===hi?""+f(lo):f(lo)+" to "+f(hi))+(u?(u==="%"?u:" "+u):" (unit not stated)")};
const VARY={oxygen:"Oxygen",pressure:"Pressure",flow:"Airflow",gravity:"Gravity",material:"Material"};

/* Backend investigation profile (+ optional records) -> the object the views use. Empty string = not reported. */
function adapt(p,recs){
 const metadata=p.metadata||{};
 const c=p.conditions||{},v=k=>(c[k]&&c[k].values)||[],f=p.detected_fields||{},g=c.gravity,meas=Object.keys(p.measurements||{});
 const i={id:p.id,title:p.name,file:p.file,rows:p.row_count,total:p.records_total==null?p.row_count:p.records_total,modified:p.last_modified,
  mat:join(v("material")),sens:join(v("sensors")),hw:join(metadata["Comment[Experiment Hardware]"]||v("mission")),desc:join(v("objective"))||join(v("notes")),find:join(v("findings")),findings:p.findings||[],documents:p.documents||[],dataNotes:p.data_notes||[],tableNotes:p.table_notes||[],approach:join(metadata["Comment[Approach]"]),testPlan:join(metadata["Comment[Test Plan]"]),oxygenColumn:c.oxygen&&c.oxygen.type==="numeric"?f.oxygen:"",
  src:join((p.source_references||{}).values)||p.file,
  grav:g?(g.type==="categorical"?join(g.values):rng(g)):"",gmax:g&&g.normalized?g.normalized.max:null,
  o2:rng(c.oxygen)||join(v("oxygen")),pr:rng(c.pressure),
  vary:Object.keys(VARY).filter(k=>c[k]&&((c[k].distinct_values||c[k].values||[]).length>1)).map(k=>VARY[k]).join(", "),
  meas,cols:["oxygen","pressure","flow","gravity"].map(k=>f[k]).filter(Boolean),dq:p.data_quality||{},runs:[]};
 if(recs)i.runs=recs.map(r=>({n:r.row_number,raw:r.values,o2:cell(f.oxygen,c.oxygen,r.values),p:cell(f.pressure,c.pressure,r.values),
  m:Object.fromEntries(meas.map(k=>[k,num(r.values[k])]))}));
 i.plots=investigationPlots(p,i.runs);
 return i}

/* Gravity filter bands (g) used by the UI's gravity dropdown; the backend filters on normalised g. */
const GBANDS={Microgravity:[0,.05],Lunar:[.1,.25],Martian:[.3,.45],Earth:[.9,1.1]};
const GR=Object.keys(GBANDS);
/* How close an investigation must be to a scenario to count as matching. */
const TOL={o2:5,p:20,g:.1};
const isEarthG=i=>i.gmax!=null&&i.gmax>=.9;

const Data={
 invalidate:()=>Object.keys(memo).forEach(k=>delete memo[k]),
 health:()=>once("health",async()=>(await API.get("/health")).data),
 stats:()=>once("stats",async()=>(await API.get("/statistics")).data),
 catalog:()=>once("catalog",async()=>{const r=await API.get("/investigations");return{items:r.data.map(p=>adapt(p)),unreadable:r.meta.unreadable_files||[]}}),
 detail:id=>once("d:"+id,async()=>{const r=await API.get("/investigations/"+encodeURIComponent(id),{include_records:"true",limit:1000});return adapt(r.data,r.data.records)}),
 cats:()=>once("cats",async()=>(await API.get("/rankings/categories")).data),
 topics:()=>once("topics",async()=>(await API.get("/insights/topics")).data),
 /* reference environments (ISS, lunar, Mars...) are served with every ranking response */
 envs:async()=>once("envs",async()=>{const c=await Data.cats();if(!c.length)return{};return(await API.get("/rankings",{category:c[0].key,limit:1})).data.reference_environments||{}})
};

/* Plot choices are validated against paired records, rather than every numeric column.
   Inputs and geometry are x candidates; outcomes are y candidates. */
function investigationPlots(profile, runs){
 const fields=profile.detected_fields||{},columns=profile.columns||[];
 const identifiers=/\b(id|identifier|date|gmt|camera|gain|frames?|display|restrictor)\b|sample\s*(?:#|number)|test\s*(?:#|number)/i;
 const input=/initial|thickness|ignition|ambient|oxygen|pressure|air.?flow|flow.?speed|flow.?velocity/i;
 const categorical=columns.filter(c=>c===fields.material||/^(?:fuel|material|flow direction)$/i.test(c));
 const numeric=columns.filter(c=>!identifiers.test(c)).filter(c=>{
  const values=runs.map(r=>NUM.exec(r.raw[c]==null?'':String(r.raw[c]))).filter(Boolean);
  return values.length>=2&&new Set(values.map(m=>m[2].toLowerCase()).filter(Boolean)).size<=1;
 });
 const independent=numeric.filter(c=>input.test(c)||['oxygen','pressure','flow','gravity'].some(f=>fields[f]===c));
 const outcomes=numeric.filter(c=>!independent.includes(c)&&!categorical.includes(c));
 const plots=[];
 for(const x of [...independent,...categorical])for(const y of outcomes){
  if(x===y)continue;
  const category=categorical.includes(x);
  const records=runs.map(r=>({x:category?r.raw[x]:num(r.raw[x]),y:num(r.raw[y]),n:r.n})).filter(p=>p.x!=null&&p.x!==''&&Number.isFinite(p.y)&&(category||Number.isFinite(p.x)));
  if(records.length<2||new Set(records.map(p=>p.x)).size<2)continue;
  const labels=category?[...new Set(records.map(p=>p.x))]:null;
  if(labels&&labels.length>12)continue;
  plots.push({x,y,labels,points:records.map(p=>({x:category?labels.indexOf(p.x):p.x,y:p.y,xLabel:category?p.x:undefined,t:'Row '+p.n})),omitted:runs.length-records.length});
 }
 return plots;
}
function selectInvestigationPlot(i){
 const plots=i.plots||[];
 if(!plots.length){st.dx='';st.dm='';return null}
 const preferred={
  'PSI-25':{x:/initial.*o2/i,y:/final.*co.*ppm/i},
  'PSI-69':{x:/droplet initial diameter/i,y:/burning rate/i},
  'PSI-99':{x:/^material$/i,y:/burn time/i}
 }[i.id];
 const fallback=plots.find(p=>preferred&&preferred.x.test(p.x)&&preferred.y.test(p.y))||plots[0];
 if(!plots.some(p=>p.x===st.dx))st.dx=fallback.x;
 const choices=plots.filter(p=>p.x===st.dx);
 if(!choices.some(p=>p.y===st.dm))st.dm=(choices.find(p=>p.y===fallback.y)||choices[0]).y;
 return choices.find(p=>p.y===st.dm);
}
