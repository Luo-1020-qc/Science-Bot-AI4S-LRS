"""Read-only interface projection and escaped, version-bound planning delivery."""
from html import escape
import io
import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .general.planning.blueprint import FIELDS, build_blueprint
from .general.planning.ledger import load, contract_hash
from .general.planning.runtime import _questions, review
from .general.planning.delivery import design_readout, render_design
from .general.planning.evidence import metadata as evidence_metadata, location as evidence_location

STEP_LABELS = {'boundaries': '目标与边界', 'evidence_inventory': '证据清单', 'design': '实验设计',
    'acceptance': '分析与验收', 'human_review': '人工复核', 'preregister': '版本确认',
    'mock_rehearsal': '可选离线演练', 'execute': '实际执行', 'analyze': '结果分析',
    'claim_review': '结论复核', 'report': '报告交付'}
MODE_LABELS = {'implemented': '规划支持', 'mock': '离线模拟', 'manual': '需人工或执行适配'}


def safe(value):
    from .terminal import plain_model_text
    return plain_model_text(str(value))


def plan_view(state, *, example=False):
    assessment = review(state)
    plan = build_blueprint(state)
    readout=design_readout(state)
    facts = [{'field': f, 'label': FIELDS[f]['label'], 'value': row['value'],
              'status': row['status'], 'quote': row['quote']} for f, row in state['facts'].items()]
    issues = []
    for row in assessment['blockers']:
        if row.get('category')=='method_risk' or not any(i['field'] == row['field'] for i in issues):
            issues.append({**row, 'label': FIELDS[row['field']]['label']})
    if readout['synthesis_status']=='current':issues=[r for r in readout['issues'] if r['blocking']]
    questions = _questions(state, assessment)
    pending = state.get('pending')
    if pending:
        questions = [pending]+[q for q in questions if q['field'] != pending['field']][:1]
    from .general.planning.choices import decorate
    questions = decorate(state, questions)
    exported = state.get('last_export')
    steps=([{**r,'id':'experiment_'+str(i),'label':r['title'],'purpose':r['action']+' 输入：'+r['inputs']+'；产物：'+r['output'],
             'owner':'研究者或另行授权的执行器','capability':'manual','capability_label':'设计建议 · 需核实执行条件','executed':False}
            for i,r in enumerate(plan['experiment_steps'],1)] if plan.get('experiment_steps') else
           [{**node,'label':STEP_LABELS[node['id']],'capability_label':MODE_LABELS[node['capability']]} for node in plan['nodes']])
    return {'id': state['id'], 'revision': state['revision'], 'hash': contract_hash(state),
        'title': '算子模型比较 · 先导研究' if example else state['facts'].get('research_question', {}).get('value', '新的研究计划')[:80],
        'example': example, 'status': '规划已确认' if state['approval'] and assessment['ready'] else '可供复核' if assessment['ready'] else '正在澄清',
        'approved': bool(state['approval']) and assessment['ready'], 'ready': assessment['ready'], 'facts': facts,
        'unknown': [{'field': f, 'label': FIELDS[f]['label']} for f in state['unknown']],
        'conflicts': [{'field': f, 'label': FIELDS[f]['label'], 'values': rows} for f, rows in state['conflicts'].items()],
        'issues': issues, 'questions': questions, 'design_readout': readout,
        'evidence': [evidence_metadata(row) for row in state.get('evidence', [])],
        'evidence_actions': state.get('evidence_actions', {}),
        'steps': steps,
        'export': exported, 'export_current': bool(exported and exported['contract_hash'] == contract_hash(state)),
        'execution_authorized': False, 'scientific_claim_verified': False}


def session_view(session):
    state = load(session)
    planning = plan_view(state, example=session.meta.get('interface_example', False)) if state else None
    last_answer=session.meta.get('last_answer')
    if state and isinstance(last_answer,str) and session.meta.get('last_report_kind')=='research_planning':
        last_answer='\n'.join(line for line in last_answer.splitlines() if not line.startswith(('为什么问：','依据：')))
        if (state.get('pending') or {}).get('choice_id') and last_answer.startswith(('正在澄清\n','规划可复核\n')):
            from .general.planning.turn_feedback import last_receipt
            from .general.planning.method_review import notice
            receipt=last_receipt(state)
            last_answer=(receipt['text']+'\n\n'+notice(review(state))) if receipt else None
            from .general.planning.synthesis import brief
            if state.get('plan_synthesis'):last_answer=(last_answer+'\n\n' if last_answer else '')+brief(state)
    return {'id': session.meta['id'], 'backend': session.meta['backend'], 'model': session.meta['model'],
        'phase': session.meta['phase'], 'workspace': str(session.workspace.root) if session.workspace else None,
        'resources': session.resources(), 'planning': planning, 'last_answer': last_answer,
        'example': session.meta.get('interface_example', False)}


def example_view():
    from .interface_demo import example_state
    return {'id': 'e'*32, 'backend': 'offline', 'model': '未调用模型', 'phase': 'needs_input',
        'workspace': None, 'resources': {'llm_requests': 0, 'tool_attempts': 0,
            'limits': {'llm_requests': 12, 'tool_calls': 40}},
        'planning': plan_view(example_state(), example=True), 'last_answer': None, 'example': True}


def export_plan(session):
    """Only consume references created by the existing /plan export command."""
    state = load(session)
    if not state or not state.get('last_export'):
        raise ValueError('请先导出当前规划，再获取交付文件。')
    ref = state['last_export']['json_ref']
    path = session.folder/ref
    if not path.is_file() or path.resolve() != path.absolute() or not path.resolve().is_relative_to(session.folder):
        raise ValueError('交付文件不可用或路径已重定向')
    if path.stat().st_size > 2_000_000:
        raise ValueError('交付文件超出大小限制')
    plan = json.loads(path.read_text(encoding='utf-8'))
    if plan.get('contract_hash') != state['last_export']['contract_hash'] or plan.get('plan_id') != state['id']:
        raise ValueError('交付文件与所选导出版本不匹配')
    from .general.planning.ledger import validate
    from .general.planning.runtime import _plan
    snapshot_path = session.folder/'planning'/state['id']/'snapshots'/(path.stem+'.json')
    if (not snapshot_path.is_file() or snapshot_path.resolve() != snapshot_path.absolute()
            or snapshot_path.stat().st_size > 2_000_000):
        raise ValueError('导出版本的规划快照不可用')
    snapshot = json.loads(snapshot_path.read_text(encoding='utf-8'))
    validate(snapshot)
    if contract_hash(snapshot) != state['last_export']['contract_hash'] or plan != _plan(snapshot):
        raise ValueError('交付文件内容与冻结的导出快照不一致')
    approval = plan.get('approval')
    if approval and not any(d.get('type') == 'human_plan_approval'
            and d.get('contract_hash') == plan['contract_hash'] and d.get('turn') == approval.get('turn')
            for d in state['decisions']):
        raise ValueError('导出确认缺少当前账本中的人类决定记录')
    return state, plan, path


def delivery_html(plan):
    """A portable human-readable artifact; all user/model/source text is escaped."""
    def e(value): return escape(str(value), quote=True)
    facts = plan.get('fact_sources', {})
    confirmed = bool(plan.get('approval'))
    label = '规划已确认' if confirmed else '规划草案 · 待复核'
    rows = ''.join('<tr><th>'+e(FIELDS[f]['label'])+'</th><td>'+e(row['value'])+
                   '<small>'+e('模型提议 · 待确认' if row['status'] == 'proposed' else '用户声明 · 未验证外部事实')+'</small></td></tr>'
                   for f, row in facts.items())
    steps = ''.join('<li><b>'+e(STEP_LABELS.get(n['id'], n['id']))+'</b><p>'+e(n['purpose'])+
        '</p><small>'+e(n['owner'])+' · '+e(MODE_LABELS.get(n['capability'], n['capability']))+
        ' · 尚未执行</small><p class="accept">验收：'+e(n['acceptance'])+'</p></li>' for n in plan['nodes'])
    synthesis=plan.get('plan_synthesis',{})
    if synthesis.get('status')=='current':
        content=synthesis['content']
        rows=('<tr><th>设计建议 · 待复核</th><td>'+e(content['decision'])+'</td></tr>'+rows+
              ''.join('<tr><th>'+e(label)+'</th><td>'+e(value)+'</td></tr>' for label,value in
                  [('推荐路线',content['recommendation']),('设计理由',content['rationale']),
                   ('替代方案','；'.join(content['alternatives'])),('条件假设','；'.join(content['assumptions'])),
                   ('实验对比','\n'.join(r['comparison']+'；单位：'+r['unit']+'；控制：'+r['controls']+'；测量：'+r['measurement'] for r in content['matrix'])),
                   ('分析与不确定性',content['analysis']),('预算安排',content['budget_plan']),('验收和停止',content['stop_rule']),
                   ('未决条件','\n'.join(r['issue']+'；获取办法：'+r['action'] for r in content['open_questions']))]))
        steps=''.join('<li><b>'+e(r['title'])+'</b><p>'+e(r['action'])+'</p><small>设计建议 · 尚未执行</small><p>'+e('输入：'+r['inputs']+'；产物：'+r['output'])+'</p><p class="accept">验收：'+e(r['acceptance'])+'</p></li>' for r in content['steps'])
    elif synthesis.get('status')=='stale':
        rows='<tr><th>实验初稿已过期</th><td>'+e(synthesis['message'])+'</td></tr>'+rows
    issues = ''.join('<li>'+e(FIELDS[r['field']]['label'])+'：'+e(r['detail'])+'</li>'
                     for r in plan['review']['checks'] if r['status'] != 'passed')
    from .general.planning.paper_reading import render as render_reading
    sources = ''.join('<article><h3>'+e(r.get('original_filename',r['path']))+'</h3><small>'+e(evidence_location(r))+
        ' · '+e(r['sha256'])+'</small><pre>'+e(r['text'])+'</pre>'+
        ('<h3>模型解读 · 待复核</h3><pre>'+e(render_reading(r))+'</pre>' if r.get('interpretation') else '')+
        '</article>' for r in plan.get('evidence', []))
    actions = ''.join('<li>'+e(FIELDS[f]['label'])+'：'+e(row['text'])+'（拟议步骤，未执行）</li>'
                      for f, row in plan.get('evidence_actions', {}).items())
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Science Bot · 科研计划交付</title><style>
:root{color-scheme:light}*{box-sizing:border-box}body{margin:0;background:#faf8f9;color:#33262b;font:15px/1.75 "Segoe UI","Microsoft YaHei",sans-serif}
main{max-width:1000px;margin:52px auto;padding:0 32px}header{border-bottom:2px solid #9f003b;padding-bottom:28px}h1{font-size:34px;margin:18px 0 8px}
h2{margin:40px 0 16px;font-size:22px}h3{font-size:16px}.delivery-brand{display:flex;align-items:center;gap:12px;color:#9f003b;font-family:Consolas,monospace}.delivery-brand svg{width:29px;height:29px;flex-shrink:0}.eyebrow,small{color:#75636a}small{display:block;overflow-wrap:anywhere}
.badge{display:inline-block;background:#f6e4eb;color:#78002d;padding:4px 14px;border-radius:20px;font-size:13px}
.notice{background:#f6e4eb;padding:16px 20px;border-left:3px solid #9f003b;margin:24px 0}table{border-collapse:collapse;width:100%;background:white}
th,td{border-bottom:1px solid #e8dce1;padding:16px;text-align:left;vertical-align:top}th{width:190px;font-weight:500;color:#75636a}
ol{padding:0;list-style:none;counter-reset:step;display:grid;grid-template-columns:1fr 1fr;gap:14px}ol li{background:white;padding:22px;break-inside:avoid}
ol b:before{counter-increment:step;content:counter(step,decimal-leading-zero) "  ";color:#9f003b}p{margin:8px 0}.accept{font-size:13px;color:#75636a}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px;font:inherit}footer{border-top:1px solid #e8dce1;margin:40px 0;padding-top:18px;color:#75636a}
@media(max-width:650px){main{padding:0 18px;margin:26px auto}ol{grid-template-columns:1fr}th{width:110px}h1{font-size:27px}}
@media print{body{background:white}main{margin:0;max-width:none}ol li,table{border:1px solid #ddd}h2{break-after:avoid}}</style><main>
<header><div class="delivery-brand"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M16 6v4M4 16v5m24-5v5" stroke="currentColor" stroke-width="2" stroke-linecap="square"/><rect x="6" y="10" width="20" height="16" rx="2" stroke="currentColor" stroke-width="2"/><rect x="10" y="15" width="3" height="3" fill="currentColor"/><rect x="19" y="15" width="3" height="3" fill="currentColor"/><path d="M12 22h8" stroke="currentColor" stroke-width="2"/><rect x="14.5" y="3" width="3" height="3" fill="currentColor"/></svg><span>SCIENCE-BOT / RESEARCH DELIVERY</span></div><h1>一份可以复核的研究计划</h1><span class="badge">'''+e(label)+'''</span>
<small>版本 '''+e(plan.get('revision', '—'))+' · '+e(plan.get('contract_hash', ''))+'''</small></header>
<p class="notice">本交付是规划与责任记录。实验步骤尚未执行，规划确认不等于真实执行授权；用户声明和论文出处不代表科学事实已验证。</p>
<h2>研究问题与边界</h2><table>'''+rows+'''</table><h2>步骤、责任与验收</h2><ol>'''+steps+'''</ol>
<h2>未知、冲突与复核提醒</h2><ul>'''+(issues or '<li>当前声明可供人类复核，外部事实及方法假设仍需核实。</li>')+actions+'''</ul>
<h2>显式选择的来源快照</h2>'''+(sources or '<p>尚未选择论文片段。不能根据论文名字补造证据。</p>')+'''
<footer>由 Science Bot 整理 · 研究者保留方法选择与结论责任 · 可打印或另存为PDF</footer></main></html>'''


def export_bundle(session):
    result = session.message('/plan export')
    if result.get('planning_error'):
        raise ValueError(result['answer'])
    state, plan, path = export_plan(session)
    target = path.with_suffix('.html')
    if target.resolve() != target.absolute():
        raise ValueError('交付目录不能重定向')
    target.write_text(delivery_html(plan), encoding='utf-8')
    return {'markdown': session.folder/state['last_export']['markdown_ref'], 'json': path,
            'html': target, 'hash': plan['contract_hash']}


def show_home(console, view):
    console.print(Panel(Text('Science Bot\n把研究想法，整理成可复核的计划。', style='bold'),
                        title='研究工作台', border_style='green', padding=(1, 3)))
    mode = '离线示例 · 合成内容' if view['example'] else '离线模式' if view['backend'] == 'offline' else 'DeepSeek · API模式'
    console.print(Text(mode+'  ·  '+(view['workspace'] or '尚未绑定项目'), style='dim'))
    console.print(Text('直接描述目标开始规划  /status 看全貌  /report 看交付  /deliver 导出  /help 帮助\n', style='green'))


def show_planning(console, planning):
    if not planning:
        console.print(Panel(Text('从一个问题开始：\n“我想复现一篇论文，但还没确定要验证哪个结论。”\n\n或输入 /plan start <你的目标>。'), title='开始研究', border_style='green'))
        return
    facts = {r['field']: r for r in planning['facts']}
    table = Table.grid(padding=(0, 2));table.add_column(style='dim', width=18);table.add_column()
    for field in ('research_question', 'scope', 'experimental_unit', 'outcomes', 'resources'):
        row = facts.get(field)
        table.add_row(FIELDS[field]['label'], Text(safe(row['value'] if row else '尚待明确')))
    console.print(Panel(table, title=Text(planning['status']+' · 第'+str(planning['revision'])+'版'), border_style='green'))
    issues = planning['issues']
    if issues:
        console.print(Panel(Text('\n'.join('• '+r['label']+'：'+safe(r['detail']) for r in issues[:4])),
                            title='下一步需要澄清', border_style='yellow'))
    console.print(Text('规划确认：'+('已确认' if planning['approved'] else '待复核')+'  ·  实验：尚未执行', style='dim'))


def show_delivery(console, session):
    state = load(session)
    if not state:
        console.print(Panel(Text('先建立研究规划，再查看和导出交付物。'), title='交付中心', border_style='green'))
        return
    view = plan_view(state, example=session.meta.get('interface_example', False))
    show_planning(console, view)
    console.print(Panel(Text(safe(render_design(state))), title='实验设计', border_style='red'))
    table = Table('步骤', '责任', '能力', '状态', border_style='green', show_lines=False)
    for node in view['steps']:
        table.add_row(node['label'], Text(safe(node['owner'])), node['capability_label'], '尚未执行')
    console.print(table)
    console.print(Text('内容版本：'+view['hash'], style='dim'))
    console.print(Text('/deliver 导出 HTML阅读版 + Markdown + JSON。草案也可导出，保留所有缺口。', style='green'))


def terminal_preview_html():
    console = Console(file=io.StringIO(), record=True, width=116, force_terminal=False, highlight=False)
    view = example_view();show_home(console, view);show_planning(console, view['planning'])
    console.print(Panel(Text('1. 确认展示的命题理解：/plan accept hypothesis\n2. 记录先导依据：/plan sampling: 固定预算先导，不宣称功效保证\n3. 查看交付：/report；导出三种格式：/deliver'),
                        title='试用路径 · 全程离线，不执行实验', border_style='green'))
    return console.export_html(inline_styles=True, clear=False)


def browser_preview_html():
    """Self-contained synthetic preview, including when opened from disk."""
    assets = Path(__file__).with_name('workbench_assets')/'dist'
    source = (assets/'index.html').read_text(encoding='utf-8')
    css = (assets/'styles.css').read_text(encoding='utf-8')
    script = (assets/'app.js').read_text(encoding='utf-8')
    data = json.dumps(example_view(), ensure_ascii=False).replace('<', '\\u003c').replace('&', '\\u0026')
    source = source.replace('<link rel="stylesheet" href="/styles.css">', '<style>'+css+'</style>')
    source = source.replace('<script src="/app.js" defer></script>', '')
    source = source.replace('href="/terminal"', 'href="terminal.html"').replace('href="/demo-delivery.html"', 'href="delivery.html"')
    return source.replace('</body>', '<script>globalThis.__SCIENCE_BOT_DEMO__='+data+';\n'+script+'</script></body>')
