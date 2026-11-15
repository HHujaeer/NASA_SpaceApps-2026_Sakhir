/* MODEL: comparison of two investigations, computed by POST /api/compare. */
async function loadCompare(){
 const cat=await Data.catalog(),A=cat.items,c=st.cmp;
 vd.cmp={items:A,res:null,err:null};
 if(A.length<2)return;
 if(!A.some(i=>i.id===c.a))c.a=A[0].id;
 if(!A.some(i=>i.id===c.b))c.b=A[1].id;
 if(c.a!==c.b){[vd.cmp.da,vd.cmp.db]=await Promise.all([Data.detail(c.a),Data.detail(c.b)])}
 if(!c.go)return;
 if(c.a===c.b){vd.cmp.err=new Error("Pick two different investigations to compare.");return}
 const explain=!!(c.ex&&vd.fresh);vd.fresh=false;
 const[res,da,db]=await Promise.all([API.post("/compare",{ids:[c.a,c.b],explain}),Data.detail(c.a),Data.detail(c.b)]);
 vd.cmp.res=res.data;vd.cmp.da=da;vd.cmp.db=db}
/* measurement columns offered for the current pair (shared ones first) */
function compareMeasures(){
 const a=vd.cmp.da,b=vd.cmp.db;if(!a||!b)return[];
 const available=i=>[...new Set(i.plots.map(p=>p.y))],am=available(a),bm=available(b);
 const both=am.filter(k=>bm.includes(k)),rest=[...am,...bm].filter(k=>!both.includes(k));
 return[...new Set([...both,...rest])]}
