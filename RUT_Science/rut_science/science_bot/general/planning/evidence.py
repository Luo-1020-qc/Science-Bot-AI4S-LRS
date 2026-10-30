"""Explicitly selected, bounded workspace excerpts. Never follow document instructions."""
from copy import deepcopy
from pathlib import Path
import hashlib
import re

from ....util import digest
from ..provider import _strict_json
from ..registry import _project_read, _validate

MAX_SOURCES = 6
MAX_EXCERPT_BYTES = 6000
MAX_TOTAL_BYTES = 18000
SPEC = {"type": "object", "properties": {
    "path": {"type": "string", "minLength": 1, "maxLength": 1000},
    "start_line": {"type": "integer", "minimum": 1},
    "end_line": {"type": "integer", "minimum": 1},
    "share_with_model": {"type": "boolean"}},
    "required": ["path", "start_line", "end_line"], "additionalProperties": False}
PDF_SPEC={"type":"object","properties":{
    "path":{"type":"string","minLength":1,"maxLength":1000},
    "start_page":{"type":"integer","minimum":1},"end_page":{"type":"integer","minimum":1},
    "share_with_model":{"type":"boolean"}},"required":["path","start_page","end_page"],"additionalProperties":False}


def location(row):
    return ('PDF第'+str(row['start_page'])+'–'+str(row['end_page'])+'页' if row.get('format')=='pdf'
            else 'L'+str(row['start_line'])+'–L'+str(row['end_line']))


def metadata(row):
    return {k:deepcopy(v) for k,v in row.items() if k not in {'text','pages'}}


def validate_sources(sources):
    if type(sources) is not list or len(sources) > MAX_SOURCES:
        raise ValueError('论文证据数量超出限制')
    ids = set()
    for row in sources:
        pdf=type(row) is dict and row.get('format')=='pdf'
        keys = {'id', 'path', 'sha256', 'text', 'start_line', 'end_line', 'excerpt_sha256',
                'workspace_id', 'workspace_root', 'share_with_model', 'turn', 'status'}
        if pdf:
            keys|={'format','start_page','end_page','page_count','pages','extractor'}
            if 'interpretation' in row:keys.add('interpretation')
        if type(row) is not dict or set(row) != keys:
            raise ValueError('论文证据快照结构无效')
        if any(type(row[key]) is not str for key in ('id', 'path', 'sha256', 'text',
                                                     'excerpt_sha256', 'workspace_id', 'workspace_root', 'status')):
            raise ValueError('论文证据需要文本来源标识')
        if any(not re.fullmatch(r'[a-f0-9]{64}', row[key]) for key in ('sha256', 'excerpt_sha256')):
            raise ValueError('论文证据需要文件和片段哈希')
        if (not re.fullmatch(r'[a-f0-9]{32}', row['workspace_id']) or not Path(row['workspace_root']).is_absolute()
                or not row['path'] or Path(row['path']).is_absolute() or '..' in Path(row['path']).parts
                or type(row['share_with_model']) is not bool or type(row['turn']) is not int
                or row['status'] != 'selected_excerpt_not_verified'):
            raise ValueError('论文证据绑定无效')
        if (type(row['start_line']) is not int or type(row['end_line']) is not int
                or not 1 <= row['end_line']-row['start_line']+1 <= (3000 if pdf else 120) or row['start_line'] < 1):
            raise ValueError('论文证据行范围无效')
        raw = row['text'].encode('utf-8')
        if pdf:
            from .pdf_document import page_text
            if (any(type(row[k]) is not int for k in ('start_page','end_page','page_count'))
                    or not 1<=row['start_page']<=row['end_page']<=row['page_count']
                    or row['end_page']-row['start_page']+1>12 or type(row['pages']) is not list
                    or len(row['pages'])!=row['end_page']-row['start_page']+1 or type(row['extractor']) is not str):
                raise ValueError('PDF页范围或提取器信息无效')
            for number,page in enumerate(row['pages'],row['start_page']):
                if type(page) is not dict or set(page)!={'page','text'} or type(page['page']) is not int or page['page']!=number or type(page['text']) is not str or not page['text'].strip():
                    raise ValueError('PDF原文页结构无效')
            if page_text(row['pages'])!=row['text'] or row['start_line']!=1 or row['end_line']!=len(row['text'].splitlines()):
                raise ValueError('PDF页快照与提取文字不一致')
            if 'interpretation' in row:
                from .paper_reading import validate_reading
                validate_reading(row['interpretation'],row)
        if (not raw.strip() or len(raw) > (MAX_TOTAL_BYTES if pdf else MAX_EXCERPT_BYTES)
                or hashlib.sha256(raw).hexdigest() != row['excerpt_sha256']
                or row['id'] != source_id(row) or row['id'] in ids):
            raise ValueError('论文证据片段内容或身份无效')
        ids.add(row['id'])
    if sum(len(row['text'].encode('utf-8')) for row in sources) > MAX_TOTAL_BYTES:
        raise ValueError('论文证据总量超出限制')


def source_id(row):
    keys=('workspace_id','path','sha256','format','start_page','end_page') if row.get('format')=='pdf' else ('workspace_id','path','sha256','start_line','end_line')
    return digest({key:row[key] for key in keys})[:16]


def citation(row):
    if row.get('format')=='pdf':return f"{row['path']}:P{row['start_page']}-P{row['end_page']}#{row['sha256']}"
    return f"{row['path']}:L{row['start_line']}-L{row['end_line']}#{row['sha256']}"


def select(session, arguments, turn):
    pdf=type(arguments) is dict and Path(arguments.get('path','')).suffix.lower()=='.pdf'
    _validate(arguments, PDF_SPEC if pdf else SPEC)
    if not pdf and arguments['end_line']-arguments['start_line']+1 not in range(1, 121):
        raise ValueError('请选择最多120行的连续片段')
    workspace = session.workspace
    if workspace is None:
        raise ValueError('请先用 -Workspace 绑定包含所选论文的项目；不会读取工作区之外或IDE标签中的文件')
    if pdf:
        from .pdf_document import extract
        row=extract(workspace,arguments)
        if len(row['text'].encode('utf-8'))>min(MAX_TOTAL_BYTES,session.limits['read_bytes']):
            raise ValueError('所选PDF页超过本次上下文预算，请缩小范围；未截断或上传。')
        row.update(workspace_id=workspace.binding['workspace_id'],workspace_root=str(workspace.root),
            excerpt_sha256=hashlib.sha256(row['text'].encode('utf-8')).hexdigest(),
            share_with_model=arguments.get('share_with_model',False),turn=turn,status='selected_excerpt_not_verified')
        row['id']=source_id(row);validate_sources([row]);return row
    if Path(arguments['path']).suffix.lower() not in {'.md', '.txt', '.markdown'}:
        raise ValueError('论文证据支持PDF、UTF-8 Markdown和TXT。')
    # Reuse project reads, including explicit allowlist, excluded paths, link target
    # checks, file size, encoding, line range and context-byte limits.
    cap = min(MAX_EXCERPT_BYTES, session.limits['read_bytes'])
    result = _project_read({key: arguments[key] for key in ('path', 'start_line', 'end_line')},
                           {'workspace': workspace, 'allowed_paths': [arguments['path']],
                            'max_read_bytes': cap, 'remaining_read_bytes': cap})
    row = {key: result[key] for key in ('path', 'sha256', 'text', 'start_line', 'end_line')}
    row.update(workspace_id=workspace.binding['workspace_id'], workspace_root=str(workspace.root),
               excerpt_sha256=hashlib.sha256(row['text'].encode('utf-8')).hexdigest(),
               share_with_model=arguments.get('share_with_model', False), turn=turn,
               status='selected_excerpt_not_verified')
    row['id'] = source_id(row)
    validate_sources([row])
    return row


def command(session, state, payload, turn):
    verb, _, value = payload.strip().partition(' ')
    sources = state.get('evidence', [])
    if verb in {'', 'list'}:
        return render(sources), False
    if verb == 'show':
        row = next((r for r in sources if r['id'] == value.strip()), None)
        if row is None:
            raise ValueError('证据编号不存在；/plan evidence list 查看已选片段')
        lines = row['text'] if row.get('format')=='pdf' else '\n'.join(f'{i}: {line}' for i, line in enumerate(row['text'].splitlines(), row['start_line']))
        return citation(row)+'\n'+lines+'\n这是选定时保存的片段快照，未自动验证论文结论。', False
    if verb=='understand':
        row=next((r for r in sources if r['id']==value.strip()),None)
        if row is None:raise ValueError('请先选择PDF片段，并使用当前证据编号。')
        from .paper_reading import understand,render as render_reading
        reading=understand(session,row,turn)
        if row.get('interpretation')==reading:return render_reading(row),False
        row['interpretation']=reading;validate_sources(sources)
        state['approval']=None
        state['decisions'].append({'turn':turn,'type':'paper_interpretation','source_id':row['id'],
                                  'meaning':'Model interpretation with checked quotations; not scientific facts'})
        return render_reading(row),True
    if verb == 'add':
        row = select(session, _strict_json(value), turn)
        if any({k:v for k,v in old.items() if k!='turn'} == {k:v for k,v in row.items() if k!='turn'} for old in sources):
            return render(sources), False
        # Re-selecting a changed file explicitly refreshes this range. Prior
        # versions remain in immutable ledger snapshots, not in the active list.
        def same_range(old):
            keys=('workspace_id','path','format','start_page','end_page') if row.get('format')=='pdf' else ('workspace_id','path','start_line','end_line')
            return all(old.get(k)==row.get(k) for k in keys)
        updated = [deepcopy(r) for r in sources if not same_range(r)]+[row]
        validate_sources(updated)
        if sum(len(r['text'].encode('utf-8')) for r in updated)>session.limits['read_bytes']:
            raise ValueError('已选论文片段总量超过此会话的文件上下文预算')
        if updated == sources:
            return render(sources), False
        state['evidence'] = updated
        description = '已选论文片段：'+citation(row)
    elif verb == 'remove':
        if value.strip() not in {r['id'] for r in sources}:
            raise ValueError('证据编号不存在')
        state['evidence'] = [deepcopy(r) for r in sources if r['id'] != value.strip()]
        description = '已从当前版本移除所选片段；历史快照仍保留。'
    else:
        raise ValueError('用法：/plan evidence add {"path":"paper.pdf","start_page":1,"end_page":3,"share_with_model":true}；也可 list/show <id>/understand <id>/remove <id>')
    state['approval'] = None
    for field in ('hypothesis', 'scope', 'baseline', 'outcomes', 'analysis', 'acceptance'):
        if field in state['facts']:
            state['stale'][field] = '所选论文证据发生变化，请核对该声明与片段的关系；片段不自动覆盖用户声明'
    state['decisions'].append({'turn': turn, 'type': 'explicit_evidence_selection', 'summary': description})
    return description+'\n'+render(state['evidence']), True


def render(sources):
    lines = ['论文证据：选定时保存的原文快照，未经科学事实验证。']
    for row in sources:
        lines.append(f"- {row['id']} · {citation(row)} · "+('允许用于模型澄清' if row['share_with_model'] else '仅本地展示'))
    if not sources:
        lines.append('尚未选择片段。用 /plan evidence add 指定当前工作区中的文件及行号或PDF页码。')
    lines.append('共享给模型须显式 share_with_model:true；文献内的指令不会扩大文件范围或执行权限。')
    return '\n'.join(lines)
