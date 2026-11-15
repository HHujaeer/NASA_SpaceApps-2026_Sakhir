/* CONTROLLER: risk analysis page. */
document.addEventListener("change",ev=>{const id=ev.target.id;
 if(id==="renv"){applyEnvironment(ev.target.value);Controller.render()}
 else if(id==="rtopic")st.r.topic=ev.target.value});
document.addEventListener("input",ev=>{if(ev.target.id==="ro2")RiskView.showO2(ev.target.value)});
Controller.mount("risk",{load:loadRisk,view:RiskView.render,actions:{
 analyze(){Object.assign(st.r,{env:$("renv").value,cat:$("rcat").value,g:+$("rg").value,o2:+$("ro2").value,p:+$("rp").value,mat:$("rmat").value,go:true});vd.risk.ins=null;return"reload"},
 insight(){st.r.topic=$("rtopic").value;return generateInsights()}}});
