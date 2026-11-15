const InvestigationChatView={
 render(id){
 const chat=investigationChat(id),detail=vd.det,measurement=st.dm||detail.meas[0],chartPrompt=detail.oxygenColumn&&measurement?`Create a scatter chart of ${measurement} versus ${detail.oxygenColumn} using the experiment table.`:detail.runs&&detail.runs[0]&&Object.hasOwn(detail.runs[0].raw,"Sample Number")?`Create a bar chart of ${measurement} by Sample Number using the experiment table. Omit nonnumeric observations without replacing them with zero.`:"Create a chart of the available numeric measurements in this investigation.";
 return `<aside class="investigation-chat" aria-label="Investigation assistant"><div class="chat-heading"><div><h3>Investigation assistant</h3><p class="sub">Working with ${e(id)}</p></div><button class="btn" data-a="chat-clear" ${chat.busy?'disabled':''}>Clear</button></div>
 <div class="investigation-messages" id="investigation-messages" role="log" aria-live="polite">
 ${!chat.messages.length?`<p class="sub">Ask about the report, explore the results, or describe a chart.</p><div class="chat-suggestions"><button class="btn" data-a="chat-example" data-v="Summarize the main findings and cite the report pages.">Explain the findings</button><button class="btn" data-a="chat-example" data-v="${e(chartPrompt)}">Chart experiment measurements</button></div>`:''}
 ${chat.messages.map((m,index)=>m.role==='user'?`<div class="investigation-message user">${e(m.text)}</div>`:m.error?`<div class="investigation-message err">${e(m.error)}</div>`:`<div class="investigation-message">${md(m.response.answer||m.response.message)}${m.response.chart?InvestigationChatView.chart(m.response.chart,index):''}${m.response.chart_error?`<p class="err">Chart could not be created: ${e(m.response.chart_error)}</p>`:''}<details><summary>Evidence and citations</summary>${sourcesHtml(m.response)}</details></div>`).join('')}
 ${chat.busy?'<p class="sub" role="status">Reading evidence and preparing your response…</p>':''}</div>
 <form id="investigation-chat-form"><label for="investigation-prompt">Ask a question or request a chart</label><textarea id="investigation-prompt" rows="3" maxlength="1000" placeholder="Plot final CO against initial oxygen…">${e(chat.draft)}</textarea><div class="row sp"><span class="sub">Enter to send · Shift+Enter for a new line</span><button class="btn on" type="submit" ${chat.busy?'disabled':''}>Send</button></div>${chat.error?`<p class="err">${e(chat.error)}</p>`:''}</form></aside>`},
 chart(c,index){return `<figure class="generated-chart"><figcaption>${e(c.title)}</figcaption><div class="chart-canvas" data-chat-chart="${index}"></div><p class="note">${c.points.length} of ${c.total_points} paired records · ${c.skipped_rows} rows missing valid paired values${c.omitted_points?' · '+c.omitted_points+' points omitted':''}. ${e(c.note)}</p><button class="btn" data-a="chart-download" data-v="${index}">Download data (CSV)</button></figure>`},
 instances:[],
 after(){
 this.instances.forEach(c=>c.destroy());this.instances=[];
 if(st.sub!=='detail')return;
 const chat=investigationChat(st.sel);
 document.querySelectorAll('[data-chat-chart]').forEach(container=>{
  const c=chat.messages[+container.dataset.chatChart].response.chart;
  if(!window.Chart){
   container.innerHTML=c.type==='bar'?bars(c.points.map(p=>({v:p.y,l:String(p.x),c:'pt'})),c.y):scatter(c.points.map(p=>({x:p.x,y:p.y,t:'Row '+p.row_number})),c.x,c.y);
   container.insertAdjacentHTML('beforeend','<p class="note">Point preview. The interactive chart library is unavailable.</p>');return;
  }
  const canvas=document.createElement('canvas');canvas.setAttribute('role','img');canvas.setAttribute('aria-label',c.title);container.append(canvas);
  this.instances.push(new Chart(canvas,{type:c.type,data:{labels:c.type==='bar'?c.points.map(p=>String(p.x)):undefined,datasets:[{label:c.y,data:c.type==='bar'?c.points.map(p=>p.y):c.points.map(p=>({x:p.x,y:p.y})),borderColor:'#7fa6c9',backgroundColor:'#7fa6c9',pointRadius:3,showLine:c.type==='line',tension:0}]},plugins:[{
   id:'cursor',afterEvent(chart,args){const ev=args.event;chart.$cursor=ev.type==='mouseout'?null:ev.x;args.changed=true},
   afterDraw(chart){const x=chart.$cursor,a=chart.chartArea;if(x==null||x<a.left||x>a.right)return;const ctx=chart.ctx;ctx.save();ctx.strokeStyle='#b8cbe0';ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(x,a.top);ctx.lineTo(x,a.bottom);ctx.stroke();ctx.restore()}
  }],options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'nearest',intersect:false},scales:{x:{type:c.type==='bar'?'category':'linear',title:{display:true,text:c.x,color:'#adb9c9'},ticks:{color:'#adb9c9'}},y:{title:{display:true,text:c.y,color:'#adb9c9'},ticks:{color:'#adb9c9'}}},plugins:{legend:{display:false},tooltip:{callbacks:{title:items=>items.length?'Source row '+c.points[items[0].dataIndex].row_number:'',label:item=>{const p=c.points[item.dataIndex];return [c.x+': '+p.x,c.y+': '+p.y]}}}}}}));
 });
 const log=document.getElementById('investigation-messages');if(log)log.scrollTop=log.scrollHeight;
 },
 download(index){const c=investigationChat(st.sel).messages[+index].response.chart,quote=v=>'"'+String(v).replace(/"/g,'""')+'"';
 const csv=[[c.x,c.y,'source_file','source_row'],...c.points.map(p=>[p.x,p.y,p.source.file,p.row_number])].map(row=>row.map(quote).join(',')).join('\r\n');
 const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=st.sel+'-chart.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
 }
};
window.addEventListener('chart-library-ready',()=>{if(typeof Controller.render==='function')InvestigationChatView.after()});
