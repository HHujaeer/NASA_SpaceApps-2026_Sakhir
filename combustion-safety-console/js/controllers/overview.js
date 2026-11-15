/* CONTROLLER: overview page. */
document.addEventListener("keydown",ev=>{if(ev.key==="Enter"&&ev.target.id==="q")document.querySelector('[data-a="search"]').click()});
document.addEventListener("change",ev=>{if(ev.target.id==="om"){st.ov.m=ev.target.value;Controller.render()}});
Controller.mount("overview",{load:loadOverview,view:OverviewView.render,actions:{search(){st.q=$("q").value;st.sub="list";save();location.href="investigations.html";return false}}});
