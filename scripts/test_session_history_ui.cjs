// Execute the shipped app against a small deterministic DOM and HTTP fixture.
// This checks interaction/state transitions; it is not browser visual QA.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const assets = path.join(root, 'RUT_Science/rut_science/science_bot/workbench_assets/dist');

async function harness(ids, pdf = false) {
  const elements = new Map(), nodes = [];
  class Element {
    constructor(tag) { this.tagName = tag; this.children = []; this.dataset = {}; this.attrs = {}; this.listeners = {}; this.className = ''; this.value = ''; this.disabled = false; nodes.push(this); }
    set id(v) { this._id = v; elements.set(v, this); } get id() { return this._id; }
    set textContent(v) { this._text = String(v); this.children = []; } get textContent() { return (this._text || '') + this.children.map(n => n.textContent).join(''); }
    append(...ns) { this.children.push(...ns); ns.forEach(n => n.parent = this); }
    replaceChildren(...ns) { this._text = ''; this.children = []; this.append(...ns); }
    setAttribute(k,v) { this.attrs[k] = String(v); }
    addEventListener(k,v) { this.listeners[k] = v; }
    async click() { if (!this.disabled) await this.listeners.click?.({ preventDefault() {} }); }
    get lastElementChild() { return this.children.at(-1); }
    get classList() { const self = this; return { contains(k) { return self.className.split(' ').includes(k); },
      add(k) { if (!this.contains(k)) self.className += ' ' + k; }, remove(k) { self.className = self.className.split(' ').filter(v => v !== k).join(' '); },
      toggle(k,v) { v ? this.add(k) : this.remove(k); } }; }
    descendants() { return this.children.flatMap(n => [n, ...n.descendants()]); }
    querySelectorAll(selector) { return this.descendants().filter(n => selector === 'button' ? n.tagName === 'button' : false); }
    before(node) { body.append(node); } focus() {} close() {} showModal() {} requestSubmit() {}
  }
  const body = new Element('body');
  const html = fs.readFileSync(path.join(assets,'index.html'),'utf8');
  [...html.matchAll(/id="([^"]+)"/g)].forEach(m => { const n = new Element('div'); n.id = m[1]; body.append(n); });
  elements.get('previewNotice').append(new Element('span'),new Element('span'));
  const formatGrid = new Element('div'); body.append(formatGrid);
  const special = {};
  for (const [selector,key,values] of [['[data-tab]','tab',['overview','chat','plan','evidence','delivery']],['[data-panel]','panel',['overview','chat','plan','evidence','delivery']],['[data-download]','download',['html','md','json']]]) {
    special[selector] = values.map(v => { const n = new Element('button'); n.dataset[key] = v; body.append(n); return n; });
  }
  function query(selector) {
    if (special[selector]) return special[selector];
    const all = body.descendants();
    if (selector === '.session-row button' || selector === '.current-choice button') {
      const cls = selector.split(' ')[0].slice(1);
      return all.filter(n => n.classList.contains(cls)).flatMap(n => n.querySelectorAll('button'));
    }
    if (selector.startsWith('.')) return all.filter(n => n.classList.contains(selector.slice(1)));
    return [];
  }
  let sessions = ids.map(id => ({ id, title: '研究 ' + id, example: false }));
  const requests = [], confirmations = [], alerts = [];
  const state = { confirm: true, reject: false, deletes: 0 };
  function view(id) { return { id, backend:pdf ? 'api' : 'offline', phase:'ready', workspace:null, model:'fixed', example:false,
    resources:{llm_requests:0,tool_attempts:0,limits:{llm_requests:12,tool_calls:40}},
    planning:pdf ? {id:'plan',hash:'f'.repeat(64),revision:1,facts:[],questions:[],steps:[],issues:[],evidence:[{
      id:'paper1',path:'papers/paper.pdf',format:'pdf',start_page:1,end_page:2,sha256:'d'.repeat(64),share_with_model:true,
      interpretation:{items:[{statement:'仅限所选合成分布。',page:1,quote:'synthetic field distribution'}],unanswered:['未提供方差。']}}]} : null,
    last_answer:'PRIVATE_CHAT_' + id }; }
  const context = { URLSearchParams, crypto:{randomUUID:()=>'test-key'}, location:{hash:'#access=token&session='+ids[0],href:'http://127.0.0.1/'},
    history:{replaceState(){}}, setTimeout:()=>1, clearTimeout(){},
    document:{body,getElementById:id=>elements.get(id)||null,createElement:tag=>new Element(tag),createTextNode:text=>{const n=new Element('#text');n.textContent=text;return n;},querySelectorAll:query,querySelector:()=>formatGrid},
    window:{confirm:text=>{confirmations.push(text);return state.confirm;},open(){}},
    fetch:async (url,options={})=>{
      requests.push({url,options}); let data, status=200;
      if (url==='/ui/sessions') data={sessions};
      else if (url.startsWith('/v1/sessions/') && url.endsWith('/messages')) data={answer:'已处理选定片段。'};
      else if (url.endsWith('/delete')) {
        state.deletes++; const id=url.split('/')[3];
        assert.equal(JSON.parse(options.body).confirm,id);assert.equal(options.headers.Authorization,'Bearer token');
        if (state.reject) {status=409;data={detail:'会话正在处理'};} else {sessions=sessions.filter(s=>s.id!==id);data={deleted:id};}
      } else if (url.startsWith('/ui/sessions/')) data=view(url.split('/')[3]);
      else throw Error('Unexpected request '+url);
      return {ok:status===200,status,json:async()=>data};
    } };
  vm.runInNewContext(fs.readFileSync(path.join(assets,'app.js'),'utf8'),context);
  const settle=async()=>{for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));}; await settle();
  const rows=()=>elements.get('sessionList').children.filter(n=>n.classList.contains('session-row'));
  return {state,requests,confirmations,elements,rows,settle};
}

(async()=>{
  let h=await harness(['a','b']); h.state.confirm=false;await h.rows()[0].children[1].click();
  assert.equal(h.state.deletes,0);assert.equal(h.rows().length,2);
  h=await harness(['a','b']);await h.rows()[1].children[1].click();
  assert.equal(h.state.deletes,1);assert.equal(h.rows().length,1);assert.match(h.elements.get('messages').textContent,/PRIVATE_CHAT_a/);
  h=await harness(['a','b']);h.elements.get('messageText').value='old unfinished input';await h.rows()[0].children[1].click();
  assert.equal(h.rows().length,1);assert.match(h.elements.get('messages').textContent,/PRIVATE_CHAT_b/);
  assert.doesNotMatch(h.elements.get('messages').textContent,/PRIVATE_CHAT_a/);assert.equal(h.elements.get('messageText').value,'');
  assert.equal(h.rows()[0].children[0].attrs['aria-current'],'true');
  h=await harness(['a']);await h.rows()[0].children[1].click();
  assert.equal(h.rows().length,0);assert.match(h.elements.get('messages').textContent,/尚无研究会话/);
  assert.doesNotMatch(h.elements.get('messages').textContent,/PRIVATE_CHAT_a/);assert.equal(h.requests.filter(r=>r.url==='/demo.json').length,0);
  h=await harness(['a']);h.state.reject=true;await h.rows()[0].children[1].click();
  assert.equal(h.rows().length,1);assert.equal(h.rows()[0].children[1].disabled,false);assert.match(h.elements.get('toast').textContent,/会话正在处理/);
  h=await harness(['a'],true);
  assert.match(h.elements.get('sourceList').textContent,/PDF第 1–2 页/);assert.match(h.elements.get('sourceList').textContent,/仅限所选合成分布/);
  const understand=h.elements.get('sourceList').descendants().find(n=>n.textContent==='查看已保存的论文解读 →');
  await understand.click();await h.settle();assert.equal(JSON.parse(h.requests.filter(r=>r.url.endsWith('/messages')).at(-1).options.body).text,'/plan evidence understand paper1');
  h.elements.get('sourcePath').value='papers/paper.pdf';h.elements.get('endLine').value='40';
  h.elements.get('sourcePath').listeners.input();assert.equal(h.elements.get('startRangeLabel').textContent,'起始PDF页');
  h.elements.get('startLine').value='1';h.elements.get('evidenceForm').listeners.submit({preventDefault(){}});await h.settle();
  const add=JSON.parse(h.requests.filter(r=>r.url.endsWith('/messages')).at(-1).options.body).text;
  assert.equal(JSON.parse(add.slice('/plan evidence add '.length)).end_page,3);
  console.log(JSON.stringify({passed:true,checks:7,mode:'mock_dom_actual_shipped_script_not_browser_visual_qa'}));
})().catch(error=>{console.error(error);process.exitCode=1;});
