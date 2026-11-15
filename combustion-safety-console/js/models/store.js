/* MODEL: UI state only (filters, selections, chat), kept per browser tab so it survives page changes. All data comes from the backend. */
function load(){try{return JSON.parse(sessionStorage.getItem("csc-state-3")||"{}")}catch(x){return{}}}
const st=Object.assign({sub:"list",sel:null,dm:"",q:"",f:{grav:"",mat:"",sens:"",omin:"",omax:"",pmin:"",pmax:"",sort:"name:asc"},aud:"ug",ov:{m:""},
 cmp:{a:"",b:"",m:"",go:false,ex:false},r:{cat:"",env:"",o2:21,p:101.3,g:0,mat:"",topic:"",go:false},chat:[],keep:0},load());
st.chat=(st.chat||[]).filter(m=>!m.pending);
const save=()=>{try{sessionStorage.setItem("csc-state-3",JSON.stringify(st))}catch(x){}};
addEventListener("pagehide",save);
