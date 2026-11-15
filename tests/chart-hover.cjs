const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={};
const context=vm.createContext({document:{addEventListener:(name,fn)=>handlers[name]=fn},e:s=>String(s),console});
vm.runInContext(fs.readFileSync('js/views/charts.js','utf8'),context);
const markup=vm.runInContext('scatter([{x:21,y:5,t:"Row 1"},{x:21,y:8,t:"Row 2"}],"Oxygen (%)","CO (ppm)")',context);
assert.match(markup,/stroke-dasharray="2 4"/);
assert.match(markup,/data-hover visibility="hidden"/);
function element(attrs={},dataset={}){return {dataset,textContent:'',setAttribute(k,v){attrs[k]=v},getAttribute:k=>attrs[k]};}
const p1=element({cx:100,cy:80},{x:'21',y:'5',label:'Row 1',xl:'Oxygen (%)',yl:'CO (ppm)'});
const p2=element({cx:100,cy:40},{x:'21',y:'8',label:'Row 2',xl:'Oxygen (%)',yl:'CO (ppm)'});
const nodes=Object.fromEntries(['hover','cursor','marker','tip','tip-label','tip-x','tip-y'].map(k=>[`[data-${k}]`,element()]));
context.svg={dataset:{},querySelectorAll:()=>[p1,p2],querySelector:s=>nodes[s]};
vm.runInContext('inspectScatter(svg,103,41)',context);
assert.equal(context.svg.dataset.index,1); // Duplicate x: choose actual point nearest pointer y.
assert.equal(nodes['[data-cursor]'].getAttribute('x1'),103);
assert.equal(nodes['[data-marker]'].getAttribute('cy'),40);
assert.equal(nodes['[data-tip-y]'].textContent,'CO (ppm): 8');
vm.runInContext('inspectScatter(svg,0,0,0)',context);
assert.equal(nodes['[data-tip-label]'].textContent,'Row 1 (nearest recorded point)');
assert.equal(nodes['[data-cursor]'].getAttribute('x1'),100);
console.log('Chart hover checks passed: cursor, marker, exact values, duplicate x, keyboard selection.');
