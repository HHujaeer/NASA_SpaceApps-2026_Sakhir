/* VIEW: small HTML helpers. */
const $=id=>document.getElementById(id);
const e=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fm=v=>v==null?"—":v;
const nr=s=>s||"—";
const opt=(a,s,blank)=>(blank!=null?`<option value="">${blank}</option>`:"")+a.map(x=>`<option ${x===s?"selected":""}>${e(x)}</option>`).join("");
const optKV=(a,s)=>a.map(x=>`<option value="${e(x.key)}" ${x.key===s?"selected":""}>${e(x.label)}</option>`).join("");
const pct=x=>x==null?"—":Math.round(x*100)+"%";
const errMsg=x=>`<p class="err">${e(x&&x.message||x)}</p>`;
const errPage=x=>`<h2>Could not load data</h2>${errMsg(x)}<p class="note">${x&&x.code&&x.code!=="network"?"Backend error code: "+e(x.code)+". ":""}Data comes from the backend API; nothing is stored in this page.</p><div class="row"><button class="btn on" data-a="retry">Retry</button></div>`;
/* Small safe markdown renderer for AI text: headings, bullets, **bold**, and [E1:R2] citation tags. */
const md=t=>{
 const inl=s=>e(s).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/\[(E\d+(?::[RC]\d+)?(?:[,;\s]+E\d+(?::[RC]\d+)?)*)\]/g,'<span class="cite">[$1]</span>');
 let h="",ul=false;const close=()=>{if(ul){h+="</ul>";ul=false}};
 const lines=String(t||"").split(/\r?\n/);
 const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(s=>s.trim());
 for(let index=0;index<lines.length;index++){const raw=lines[index],l=raw.trim();let m;
  if(l.includes('|')&&index+1<lines.length&&/^\s*\|?\s*:?-{3,}/.test(lines[index+1])&&cells(lines[index+1]).every(c=>/^:?-{3,}:?$/.test(c))){
   close();const headers=cells(l);h+='<div class="md-table"><table><thead><tr>'+headers.map(c=>'<th>'+inl(c)+'</th>').join('')+'</tr></thead><tbody>';index++;
   while(index+1<lines.length&&lines[index+1].trim().includes('|')){const row=cells(lines[++index]);h+='<tr>'+headers.map((_,n)=>'<td>'+inl(row[n]||'')+'</td>').join('')+'</tr>'}
   h+='</tbody></table></div>';continue;
  }
  if(!l){close();continue}
  if(m=/^#{1,6}\s*(.+)$/.exec(l)){close();h+=`<h4>${inl(m[1])}</h4>`}
  else if(m=/^(?:[-*•]|\d+[.)])\s+(.+)$/.exec(l)){if(!ul){h+="<ul>";ul=true}h+=`<li>${inl(m[1])}</li>`}
  else{close();h+=`<p>${inl(l)}</p>`}}
 close();return`<div class="md">${h}</div>`};
/* Sources behind an AI answer: backend-built references and a warning when citations do not check out. */
const sourcesHtml=(r)=>{
 const ex=(r.references||[]).filter(x=>x.type==="experiment"),used={};(r.retrieval||[]).forEach(x=>used[x.tag]=x.records_used||[]);
 const cc=r.citation_check;
 return(ex.length?`<h4>Sources</h4><ul class="uses">${ex.map(x=>`<li>${e(x.tag)}: <a href="investigations.html" data-a="view" data-v="${e(x.investigation_id)}" style="color:var(--steel)">${e(x.name)}</a> <span class="note" style="display:inline">(${e(x.file)}${used[x.tag]&&used[x.tag].length?"; rows "+used[x.tag].join(", "):""})</span></li>`).join("")}</ul>`:"")
 +((r.references||[]).filter(x=>x.type==="chunk").length?`<ul class="uses">${r.references.filter(x=>x.type==="chunk").map(x=>`<li>${e(x.tag)}: ${e(x.file)}${x.page?", PDF page "+x.page:""}${x.field?", "+e(x.field):""}${x.paragraph?", paragraph "+x.paragraph:""}${x.figure?", "+e(x.figure):""}${x.row_number?", source row "+x.row_number:""}</li>`).join("")}</ul>`:"")
 +(cc&&cc.unknown_citations&&cc.unknown_citations.length?`<p class="err">Citations not matching any retrieved record: ${e(cc.unknown_citations.join(", "))}. Treat those statements with caution.</p>`:"")
 +(cc&&!cc.has_citations?`<p class="err">This answer has no citations. Verify it against the sources.</p>`:"")
 +((r.retrieval||[]).length?`<span class="note">Retrieval: ${(r.retrieval||[]).some(x=>x.method==='hybrid')?'semantic + keyword':'keyword'} search over saved investigation evidence.</span>`:'')
 +(r.context_truncated?`<p class="note">Some matching records were left out because the context limit was reached.</p>`:"")
 +(r.disclaimer?`<span class="note">${e(r.disclaimer)}</span>`:"")+(r.ai?`<span class="note">Model: ${e(r.ai.provider)} / ${e(r.ai.model)}</span>`:"")};
