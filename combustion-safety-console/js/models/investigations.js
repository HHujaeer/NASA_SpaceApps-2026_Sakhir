/* MODEL: investigations list (search/filter/sort done by the backend), detail and AI summary. */
function listParams(q,f){
 const[sort,order]=f.sort.split(":"),g=GBANDS[f.grav]||[];
 return{q,fuel:f.mat,sensor:f.sens,min_oxygen:f.omin,max_oxygen:f.omax,min_pressure_kpa:f.pmin,max_pressure_kpa:f.pmax,
  min_gravity_g:g[0],max_gravity_g:g[1],sort,order}}
async function loadInvestigations(){
 const stats=await Data.stats();
 vd.inv={stats};
 if(st.sub==="add")return;
 if(st.sub==="detail"){
  try{vd.det=await Data.detail(st.sel);selectInvestigationPlot(vd.det);return}
  catch(x){if(x.code!=="investigation_not_found")throw x;st.sub="list"}}
 const r=await API.get("/investigations",listParams(st.q,st.f));
 vd.list=r.data.map(p=>adapt(p));vd.total=r.meta.total;vd.unreadable=r.meta.unreadable_files||[]}
/* Upload a CSV as a new investigation (POST /api/investigations). Resolves true when it was stored. */
async function addInvestigation(file,id,overwrite){
 vd.addErr=null;
 if(!file){vd.addErr=new Error("Choose a CSV file.");return false}
 const fd=new FormData();fd.append("file",file);if(id)fd.append("id",id);if(overwrite)fd.append("overwrite","true");
 try{const r=await API.post("/investigations",fd);Data.invalidate();st.sel=r.data.id;st.sub="detail";return true}
 catch(x){vd.addErr=x;return false}}
/* Delete the open investigation's CSV (DELETE /api/investigations/<id>). */
async function removeInvestigation(id){
 try{await API.del("/investigations/"+encodeURIComponent(id));Data.invalidate();st.sub="list";st.sel=null;vd.sum=null;return true}
 catch(x){alert(x.message);return false}}
