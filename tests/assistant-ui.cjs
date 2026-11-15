const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const ctx=vm.createContext({document:{getElementById:()=>null}});
vm.runInContext(fs.readFileSync('js/views/helpers.js','utf8'),ctx);
const table=vm.runInContext('md("| Investigation | Findings |\\n| --- | --- |\\n| PSI-69 | <script>x</script> [E1:C1] |")',ctx);
assert.match(table,/<thead>/);assert.match(table,/&lt;script&gt;/);assert.doesNotMatch(table,/<script>/);assert.match(table,/class="cite"/);
ctx.st={chat:[]};ctx.Controller={render(){}};
ctx.API={post:async(path,body)=>{ctx.request={path,body};return {data:{answer:'Evidence [E1]',answerable:true}}}};
vm.runInContext(fs.readFileSync('js/models/assistant.js','utf8'),ctx);
(async()=>{
 await vm.runInContext('askAssistant("Summarize FLEX")',ctx);
 await vm.runInContext('askAssistant("What are its limitations?")',ctx);
 assert.equal(ctx.request.body.history.length,2);
 assert.equal(ctx.request.body.history[0].content,'Summarize FLEX');
 vm.runInContext(fs.readFileSync('js/views/assistant.js','utf8'),ctx);
 ctx.ranking={category_label:'Fire suppression',ranked:[{investigation_id:'PSI-69',name:'FLEX',score:75,record_count:274,completeness:.9}],methodology:'Heuristic',disclaimer:'Not a hazard ranking'};
 const html=vm.runInContext('rankingHtml(ranking)',ctx);
 assert.match(html,/75\/100 relevance/);assert.match(html,/Not a hazard ranking/);
 console.log('Assistant UI checks passed: safe comparison tables, citations, follow-up history, relevance ranking cards.');
})().catch(e=>{console.error(e);process.exitCode=1});
