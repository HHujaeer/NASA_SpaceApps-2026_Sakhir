/* MODEL: the chat history, answered by POST /api/ask. The backend retrieves CSV rows, calls the AI and returns cited answers. */
async function askAssistant(q){
 if(st.chat.some(m=>m.pending))return;
 const history=st.chat.filter(m=>m.u||m.res&&m.res.answer).slice(-12).map(m=>({role:m.u?'user':'assistant',content:(m.u?m.t:m.res.answer).slice(0,6000)}));
 const m={a:1,pending:1};st.chat.push({u:1,t:q},m);
 try{m.res=(await API.post("/ask",{question:q,history})).data}
 catch(x){m.err={code:x.code,message:x.message,refs:((x.details||{}).references||[]).filter(r=>r.type==="experiment")}}
 delete m.pending;Controller.render()}
