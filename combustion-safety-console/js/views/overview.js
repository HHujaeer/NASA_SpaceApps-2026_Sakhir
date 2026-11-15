/* VIEW: builds HTML from the model. It never changes state. */
const OverviewView={
render(){
 const{items,R,m,meas,unreadable,truncated,top,recent,stats:S}=overviewSummary();
 const pts=R.filter(r=>r.y!=null&&r.o2!=null).map(r=>({x:r.o2,y:r.y,c:isEarthG(r.inv)?"pt2":"pt",t:r.inv.id+", "+r.inv.grav}));
 return`<div class="row sp"><div><h2>Overview</h2><p class="sub">What the loaded evidence covers</p></div><div class="row" style="margin:0"><input id="q" placeholder="Search investigations" aria-label="Search"><button class="btn" data-a="search">Search</button></div></div>
 <div class="stats">${S.map(s=>`<div><b>${s[0]}</b><span>${s[1]}</span></div>`).join("")}</div>
 ${meas.length?`<div class="row"><label class="f">Measurement<select id="om">${opt(meas,m)}</select></label></div>`:""}
 <div class="cols"><div><h3>${e(m||"Measurement")} vs. oxygen</h3>${m?scatter(pts,"Oxygen (%)",m):'<p class="sub">No numeric measurement columns found in the data.</p>'}<p class="note">Blue: below 0.9 g or gravity not recorded. Amber: about 1 g. Only records with both values are plotted.</p></div>
 <div><h3>Recently modified</h3>${items.length?`<table>${recent.map(i=>`<tr class="go" tabindex="0" data-a="view" data-v="${e(i.id)}"><td>${e(i.id)}</td><td>${e(i.title)}</td></tr>`).join("")}</table>`:'<p class="sub">No CSV files found in the backend data directory.</p>'}</div></div>
 <h3>Highest recorded values${m?": "+e(m):""}</h3>${top.length?`<table><tr><th>Investigation</th><th>Material</th><th>O₂ %</th><th>Pressure kPa</th><th>${e(m)}</th></tr>${top.map(r=>`<tr class="go" data-a="view" data-v="${e(r.inv.id)}"><td>${e(r.inv.id)}</td><td>${e(nr(r.inv.mat))}</td><td>${fm(r.o2)}</td><td>${fm(r.p)}</td><td>${r.y}</td></tr>`).join("")}</table><p class="note">Highest values in the loaded records for this column, not certified spacecraft safety ratings.${truncated?" Some large files were only partly loaded.":""}</p>`:'<p class="sub">No values recorded for this measurement.</p>'}
 ${unreadable.length?`<p class="err">Unreadable files: ${unreadable.map(u=>e(u.id+" ("+u.error+")")).join("; ")}</p>`:""}`}
};
