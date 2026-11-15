/* MODEL: thin client for the Flask backend. Resolves to {data, meta} from the response envelope, or throws ApiError. */
class ApiError extends Error{constructor(code,message,status,details){super(message);this.code=code;this.status=status;this.details=details}}
const API={
 base:(window.CSC_CONFIG.apiBase||"").replace(/\/$/,""),
 async call(method,path,{params,body}={}){
  const qs=new URLSearchParams();
  for(const[k,v]of Object.entries(params||{}))if(v!==""&&v!=null)qs.set(k,v);
  const url=API.base+"/api"+path+(qs.toString()?"?"+qs:"");
  let res,json;
  try{const raw=body instanceof FormData;res=await fetch(url,{method,headers:body&&!raw?{"Content-Type":"application/json"}:undefined,body:body?(raw?body:JSON.stringify(body)):undefined})}
  catch(x){throw new ApiError("network","Cannot reach the backend at "+API.base+". Start it (python app.py) and check js/config.js.",0)}
  try{json=await res.json()}catch(x){throw new ApiError("bad_response","The backend sent an unreadable response (HTTP "+res.status+").",res.status)}
  if(!json.success){const er=json.error||{};throw new ApiError(er.code||"error",er.message||"Request failed.",res.status,er.details)}
  return{data:json.data,meta:json.meta||{}}},
 get:(path,params)=>API.call("GET",path,{params}),
 post:(path,body)=>API.call("POST",path,{body}),
 del:path=>API.call("DELETE",path)
};
