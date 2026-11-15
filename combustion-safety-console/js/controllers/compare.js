/* CONTROLLER: compare page. */
document.addEventListener("change",ev=>{const id=ev.target.id;
 if(id==="ca"||id==="cb"){st.cmp[id==="ca"?"a":"b"]=ev.target.value;st.cmp.go=false;Controller.render()}
 else if(id==="cm"){st.cmp.m=ev.target.value;Controller.render()}
 else if(id==="cx")st.cmp.ex=ev.target.checked});
Controller.mount("compare",{
 load:loadCompare,
 view:CompareView.render,
 actions:{gen(){st.cmp.a=$("ca").value;st.cmp.b=$("cb").value;st.cmp.ex=$("cx").checked;st.cmp.m=$("cm")?$("cm").value:"";st.cmp.go=true;vd.fresh=true;return"reload"}}});
