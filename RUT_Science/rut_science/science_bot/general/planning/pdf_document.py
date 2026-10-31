"""Read an explicitly selected PDF range in a bounded, isolated parser process."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

MAX_FILE_BYTES=64*1024*1024
MAX_PAGES=256
MAX_TEXT_BYTES=2*1024*1024


def page_text(pages):
    return '\n\n'.join('[PDF page '+str(p['page'])+']\n'+p['text'] for p in pages)


def parse_bytes(raw,**selection):
    if importlib.util.find_spec('pypdf') is None:
        raise ValueError('PDF解析依赖未安装；请重新运行 scripts/setup.ps1 安装当前 science-bot 依赖。')
    if len(raw)>MAX_FILE_BYTES:raise ValueError('PDF超过64 MiB，请先压缩文件。')
    if not raw.startswith(b'%PDF-'):raise ValueError('所选文件不是有效PDF。')
    request={'data':base64.b64encode(raw).decode('ascii'),**selection}
    try:
        completed=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('pdf_worker.py'))],
            input=json.dumps(request),capture_output=True,text=True,encoding='utf-8',timeout=90)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PDF解析超过90秒，请检查文件或分段选择。') from exc
    if completed.returncode or len(completed.stdout.encode('utf-8'))>8*1024*1024:
        raise ValueError('PDF解析失败，请检查文件或减少页数。')
    try:result=json.loads(completed.stdout)
    except ValueError as exc:raise ValueError('PDF解析器未返回有效结果。') from exc
    if 'error' in result:raise ValueError(result['error'])
    return result


def extract(workspace,arguments):
    from ..registry import _relative
    start,end=arguments.get('start_page',1),arguments.get('end_page')
    if end is not None and not 1<=end-start+1<=MAX_PAGES:raise ValueError('请选择有效页码范围（最多256页），或省略页码读取全文。')
    relative=_relative(workspace,arguments['path']);path=workspace.resolve_file(relative)
    if path.suffix.lower()!='.pdf':raise ValueError('页码选择仅适用于PDF。')
    with path.open('rb') as stream:raw=stream.read(MAX_FILE_BYTES+1)
    result=parse_bytes(raw,start_page=start,end_page=end)
    pages=result['pages'];text=page_text(pages)
    if not any(p['text'].strip() for p in pages):raise ValueError('PDF没有可提取正文，请先OCR。')
    if len(text.encode('utf-8'))>MAX_TEXT_BYTES:raise ValueError('PDF提取文字超过2 MiB，请分段选择；未截断或上传。')
    start,end=pages[0]['page'],pages[-1]['page']
    return {'path':relative,'sha256':hashlib.sha256(raw).hexdigest(),'text':text,
        'start_line':1,'end_line':len(text.splitlines()),'format':'pdf','start_page':start,'end_page':end,
        'page_count':result['page_count'],'pages':pages,'extractor':result['extractor']}
