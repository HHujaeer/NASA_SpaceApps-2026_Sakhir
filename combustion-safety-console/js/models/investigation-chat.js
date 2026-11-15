/* Per-investigation state stays separate even if navigation changes during a request. */
const investigationChats={};
function investigationChat(id){return investigationChats[id]||(investigationChats[id]={messages:[],draft:'',busy:false})}
async function sendInvestigationChat(prompt){
 const id=st.sel,chat=investigationChat(id),question=(prompt||chat.draft).trim();
 if(!question||chat.busy)return false;
 if(question.length>1000){chat.error='Please keep the question to 1,000 characters.';return}
 const history=chat.messages.filter(m=>!m.error).slice(-12).map(m=>({role:m.role,content:(m.role==='user'?m.text:m.response.answer).slice(0,6000)}));
 chat.error=null;chat.draft='';chat.busy=true;chat.messages.push({role:'user',text:question});
 try{const r=await API.post('/investigations/'+encodeURIComponent(id)+'/chat',{question,history});chat.messages.push({role:'assistant',response:r.data})}
 catch(error){chat.messages.push({role:'assistant',error:error.message})}
 finally{chat.busy=false}
}
