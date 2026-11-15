/* CONTROLLER: investigations list and detail. */
const FRESH_F=()=>({grav:"",mat:"",sens:"",omin:"",omax:"",pmin:"",pmax:"",sort:"name:asc"});
document.addEventListener("change",ev=>{const t=ev.target,id=t.id||"";
 if(id.startsWith("f_")){st.f[id.slice(2)]=t.value;Controller.reload()}
 else if(id==="q"){st.q=t.value;Controller.reload()}
 else if(id==="dm"||id==="dx"){st[id]=t.value;selectInvestigationPlot(vd.det);Controller.render()}});
Controller.mount("investigations",{
 load:loadInvestigations,
 init(){if(!st.keep)st.sub="list";st.keep=0},
 view:InvestigationsView.render,
 after(){InvestigationChatView.after()},
 actions:{
  sub(t,v){st.sub=v;return"reload"},
  'chat-example'(t,v){return sendInvestigationChat(v)},
  'chat-clear'(){const chat=investigationChat(st.sel);if(chat.busy)return false;chat.messages=[];chat.draft=''},
  'chart-download'(t,v){InvestigationChatView.download(v);return false},
  clear(){st.q="";st.f=FRESH_F();return"reload"},
  pub(){return addInvestigation($("a_f").files[0],$("a_id").value.trim(),$("a_ow").checked).then(ok=>ok?Controller.reload():undefined)},
  del(){if(!confirm("Delete "+st.sel+" and its CSV file from the backend? This cannot be undone."))return false;return removeInvestigation(st.sel).then(ok=>ok?Controller.reload():undefined)}
 }});

document.addEventListener('input',ev=>{if(ev.target.id==='investigation-prompt')investigationChat(st.sel).draft=ev.target.value});
function submitInvestigationChat(){const result=sendInvestigationChat();if(result&&typeof result.then==='function'){Controller.render();result.then(()=>Controller.render())}else Controller.render()}
document.addEventListener('submit',ev=>{if(ev.target.id==='investigation-chat-form'){ev.preventDefault();submitInvestigationChat()}});
document.addEventListener('keydown',ev=>{if(ev.target.id==='investigation-prompt'&&ev.key==='Enter'&&!ev.shiftKey&&!ev.isComposing){ev.preventDefault();submitInvestigationChat()}});
