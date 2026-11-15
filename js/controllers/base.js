/* CONTROLLER base: connects clicks to a page's actions, loads the page's data from the backend, then redraws the view.
   A page may pass load() (async, fills the model from the API). An action may return:
   false (do nothing more), "reload" (run load() again, then redraw), a Promise (redraw now, and again when it settles), or nothing (redraw). */
const Controller={tk:0,mount(page,o){
 const ui={ready:false,err:null};
 const render=Controller.render=()=>{
  const v=$("view"),y=v.scrollTop,k=page+st.sub+st.sel;
  v.innerHTML=ui.err?errPage(ui.err):!ui.ready?'<p class="sub">Loading from the backend…</p>':o.view();
  v.scrollTop=k===Controller.k?y:0;Controller.k=k;save();if(ui.ready&&!ui.err&&o.after)o.after();
 };
 const reload=Controller.reload=async()=>{
  if(!o.load){ui.ready=true;ui.err=null;render();return}
  const tk=++Controller.tk,v=$("view");
  v.setAttribute("aria-busy","true");if(!ui.ready)render();
  let err=null;try{await o.load()}catch(x){err=x;console.error(x)}
  if(tk!==Controller.tk)return;
  v.removeAttribute("aria-busy");ui.err=err;ui.ready=!err;render();
 };
 document.addEventListener("click",ev=>{
  const tb=ev.target.closest(".tabs a");
  if(tb&&page==="investigations"&&tb.getAttribute("href")==="investigations.html"&&st.sub!=="list"){ev.preventDefault();st.sub="list";reload();return}
  const t=ev.target.closest("[data-a]");if(!t)return;const a=t.dataset.a,v=t.dataset.v;
  if(a==="retry"){reload();return}
  if(a==="view"){ev.preventDefault();st.sel=v;st.sub="detail";if(page==="investigations")reload();else{st.keep=1;save();location.href="investigations.html"}return}
  const r=o.actions&&o.actions[a]?o.actions[a](t,v):undefined;
  if(r===false)return;
  if(r==="reload"){reload();return}
  if(r&&typeof r.then==="function"){render();r.then(render,render);return}
  render();
 });
 document.addEventListener("keydown",ev=>{if(ev.key==="Enter"&&ev.target.dataset&&ev.target.dataset.a==="view")ev.target.click()});
 if(o.init)o.init();
 reload();
 /* backend status in the header; the pages work without it */
 const s=$("status");
 if(s)Data.health().then(h=>{s.className="pill ok";s.textContent="Backend online · "+h.csv_files_found+" CSV file"+(h.csv_files_found===1?"":"s")+" · AI "+(h.ai.configured?h.ai.provider+" / "+h.ai.model:"not configured");if(!h.ai.configured)s.title="Missing: "+h.ai.missing.join(", ")},
  x=>{s.className="pill bad";s.textContent="Backend offline"});
}};
