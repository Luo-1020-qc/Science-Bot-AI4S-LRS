"""Read an explicitly selected PDF range in a bounded, isolated parser process."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

MAX_FILE_BYTES=16*1024*1024
MAX_PAGES=12
MAX_TEXT_BYTES=18000


def page_text(pages):
    return '\n\n'.join('[PDF page '+str(p['page'])+']\n'+p['text'] for p in pages)


def extract(workspace,arguments):
    from ..registry import _relative
    if importlib.util.find_spec('pypdf') is None:
        raise ValueError('PDF解析依赖未安装；请重新运行 scripts/setup.ps1 安装当前 science-bot 依赖。')
    start,end=arguments['start_page'],arguments['end_page']
    if not 1<=end-start+1<=MAX_PAGES:raise ValueError('每次请选择1至12个连续PDF页。')
    relative=_relative(workspace,arguments['path']);path=workspace.resolve_file(relative)
    if path.suffix.lower()!='.pdf':raise ValueError('页码选择仅适用于PDF。')
    with path.open('rb') as stream:raw=stream.read(MAX_FILE_BYTES+1)
    if len(raw)>MAX_FILE_BYTES:raise ValueError('PDF超过16 MiB，请先选择较小的文件。')
    if not raw.startswith(b'%PDF-'):raise ValueError('所选文件不是有效PDF。')
    request={'data':base64.b64encode(raw).decode('ascii'),'start_page':start,'end_page':end}
    try:
        completed=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('pdf_worker.py'))],
            input=json.dumps(request),capture_output=True,text=True,encoding='utf-8',timeout=20)
    except subprocess.TimeoutExpired as exc:
        raise ValueError('PDF解析超过20秒，请缩小页码范围或先检查文件。') from exc
    if completed.returncode or len(completed.stdout.encode('utf-8'))>100000:
        raise ValueError('PDF解析失败，请检查文件或减少页数。')
    try:result=json.loads(completed.stdout)
    except ValueError as exc:raise ValueError('PDF解析器未返回有效结果。') from exc
    if 'error' in result:raise ValueError(result['error'])
    pages=result['pages'];text=page_text(pages)
    if not text.strip() or len(text.encode('utf-8'))>MAX_TEXT_BYTES:raise ValueError('所选页文字超过18000字节，请分段选择；未截断或上传。')
    return {'path':relative,'sha256':hashlib.sha256(raw).hexdigest(),'text':text,
        'start_line':1,'end_line':len(text.splitlines()),'format':'pdf','start_page':start,'end_page':end,
        'page_count':result['page_count'],'pages':pages,'extractor':result['extractor']}
