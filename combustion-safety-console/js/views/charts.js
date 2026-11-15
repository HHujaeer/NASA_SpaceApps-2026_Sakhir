/* VIEW: SVG charts and the runs table. */
function scatter(p,xl,yl,categories=null){
 if(!p.length)return'<p class="sub">No records with both values to plot. Missing values stay blank, not zero.</p>';
 p=p.filter(a=>Number.isFinite(a.x)&&Number.isFinite(a.y));
 if(!p.length)return'<p class="sub">No numeric points to plot.</p>';
 const W=categories?720:520,H=categories?330:230,m=44,bottom=categories?135:44,x0=Math.min(...p.map(a=>a.x)),x1=Math.max(...p.map(a=>a.x)),y0=Math.min(0,...p.map(a=>a.y)),y1=Math.max(0,...p.map(a=>a.y))*1.15||1;
 const X=v=>m+(x1===x0?.5:(v-x0)/(x1-x0))*(W-m-(categories?130:16)),Y=v=>H-bottom-((v-y0)/(y1-y0))*(H-bottom-14);
 return`<svg data-scatter tabindex="0" viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(yl)} against ${e(xl)}. Hover to inspect records; use arrow keys to move between points."><line class="ax" x1="${m}" y1="${H-bottom}" x2="${W-10}" y2="${H-bottom}"/><line class="ax" x1="${m}" y1="14" x2="${m}" y2="${H-bottom}"/>
 ${categories?categories.map((label,index)=>`<text x="${X(index)}" y="${H-bottom+16}" transform="rotate(30 ${X(index)} ${H-bottom+16})" text-anchor="start">${e(label)}</text>`).join(''):`<text x="${m}" y="${H-bottom+16}">${x0}</text><text x="${W-16}" y="${H-bottom+16}" text-anchor="end">${x1}</text>`}<text x="${W/2}" y="${H-6}" text-anchor="middle">${e(xl)}</text>
 <text x="${m-6}" y="${H-bottom}" text-anchor="end">${y0}</text><text x="${m-6}" y="22" text-anchor="end">${(y1).toFixed(1)}</text><text x="12" y="${H/2}" transform="rotate(-90 12 ${H/2})" text-anchor="middle">${e(yl)}</text>
 ${p.map(a=>`<circle data-x="${e(a.xLabel==null?a.x:a.xLabel)}" data-y="${a.y}" data-label="${e(a.t||"Record")}" data-xl="${e(xl)}" data-yl="${e(yl)}" class="${a.c||"pt"}" cx="${X(a.x)}" cy="${Y(a.y)}" r="5"><title>${e(a.t||"")}</title></circle>`).join("")}
 <g data-hover visibility="hidden" pointer-events="none">
 <line data-cursor y1="14" y2="${H-bottom}" stroke="currentColor" stroke-dasharray="2 4"/>
 <circle data-marker r="8" fill="none" stroke="currentColor" stroke-width="2"/>
 <g data-tip><rect width="290" height="66" rx="5" fill="#15212d" stroke="#a6bacb"/>
 <text x="8" y="18" fill="#fff" data-tip-label></text><text x="8" y="37" fill="#fff" data-tip-x></text><text x="8" y="55" fill="#fff" data-tip-y></text></g></g></svg>`}
function bars(rows,yl){
 const r=rows.filter(a=>a.v!=null);if(!r.length)return'<p class="sub">No values for this measurement in the selected investigations. Missing values stay blank, not zero.</p>';
 const W=520,H=220,m=40,mx=Math.max(...r.map(a=>a.v))*1.15||1,bw=Math.min(50,(W-m)/r.length-10);
 return`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${e(yl)}"><line class="ax" x1="${m}" y1="${H-m}" x2="${W-10}" y2="${H-m}"/><text x="${m-6}" y="${H-m}" text-anchor="end">0</text><text x="${m-6}" y="20" text-anchor="end">${mx.toFixed(1)}</text>
 ${r.map((a,i)=>{const x=m+10+i*((W-m-10)/r.length),h=a.v/mx*(H-m-20);return`<rect class="${a.c}" x="${x}" y="${H-m-h}" width="${bw}" height="${h}"/><text x="${x+bw/2}" y="${H-m-h-4}" text-anchor="middle">${a.v}</text><text x="${x+bw/2}" y="${H-m+14}" text-anchor="middle">${e(a.l)}</text>`}).join("")}</svg>`}
const runTable=i=>{const C=i.runs.length?Object.keys(i.runs[0].raw):[...new Set([...i.cols,...i.meas])];
 return i.runs.length&&C.length?`<table><thead><tr><th>Row</th>${C.map(c=>`<th>${e(c)}</th>`).join("")}</tr></thead><tbody>${i.runs.map(r=>`<tr><td>${r.n}</td>${C.map(c=>`<td>${e(fm(r.raw[c]))}</td>`).join("")}</tr>`).join("")}</tbody></table>${i.total>i.runs.length?`<p class="note">Showing the first ${i.runs.length} of ${i.total} records.</p>`:""}`:'<p class="sub">No numeric condition or measurement columns in this investigation.</p>'};

/* Delegated events survive chart redraws. Coordinates use the SVG transform,
   including responsive scaling and viewBox letterboxing. Never interpolate data. */
function inspectScatter(svg, x, y, index){
 const points=[...svg.querySelectorAll('circle[data-x]')];
 if(!points.length)return;
 let chosen=index==null?0:Math.max(0,Math.min(points.length-1,index));
 if(index==null)points.forEach((p,i)=>{
  const dx=Math.abs(+p.getAttribute('cx')-x),best=points[chosen];
  const bx=Math.abs(+best.getAttribute('cx')-x);
  if(dx<bx||dx===bx&&Math.abs(+p.getAttribute('cy')-y)<Math.abs(+best.getAttribute('cy')-y))chosen=i;
 });
 const p=points[chosen],px=+p.getAttribute('cx'),py=+p.getAttribute('cy');
 svg.dataset.index=chosen;
 const hover=svg.querySelector('[data-hover]');hover.setAttribute('visibility','visible');
 const line=svg.querySelector('[data-cursor]'),cx=index==null?Math.max(44,Math.min(504,x)):px;
 line.setAttribute('x1',cx);line.setAttribute('x2',cx);
 const marker=svg.querySelector('[data-marker]');marker.setAttribute('cx',px);marker.setAttribute('cy',py);
 svg.querySelector('[data-tip]').setAttribute('transform',`translate(${px>260?48:214},14)`);
 svg.querySelector('[data-tip-label]').textContent=p.dataset.label+' (nearest recorded point)';
 svg.querySelector('[data-tip-x]').textContent=p.dataset.xl+': '+p.dataset.x;
 svg.querySelector('[data-tip-y]').textContent=p.dataset.yl+': '+p.dataset.y;
}
document.addEventListener('pointermove',ev=>{
 const svg=ev.target.closest('svg[data-scatter]');if(!svg)return;
 const matrix=svg.getScreenCTM();if(!matrix)return;
 const point=new DOMPoint(ev.clientX,ev.clientY).matrixTransform(matrix.inverse());
 inspectScatter(svg,point.x,point.y);
});
document.addEventListener('pointerout',ev=>{
 const svg=ev.target.closest('svg[data-scatter]');
 if(svg&&!svg.contains(ev.relatedTarget))svg.querySelector('[data-hover]').setAttribute('visibility','hidden');
});
document.addEventListener('keydown',ev=>{
 const svg=ev.target.closest('svg[data-scatter]');if(!svg)return;
 if(ev.key==='Escape'){svg.querySelector('[data-hover]').setAttribute('visibility','hidden');return}
 if(!['ArrowLeft','ArrowRight'].includes(ev.key))return;
 ev.preventDefault();inspectScatter(svg,0,0,+(svg.dataset.index||0)+(ev.key==='ArrowRight'?1:-1));
});
