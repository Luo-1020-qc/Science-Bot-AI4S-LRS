"""An app-owned, content-addressed PDF library, separate from conversations.

Only explicit binary uploads write here. Library selection never changes a
research workspace or grants the model permission to scan other papers.
"""
from datetime import datetime,timezone
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import tempfile
import threading

from ..planning_agent import session_lock
from ..util import digest,write_json
from .workspace import Workspace
from .general.planning.pdf_document import MAX_FILE_BYTES,parse_bytes

MAX_PAPERS=100
MAX_LIBRARY_BYTES=1024*1024*1024
_MUTEXES={}
_MUTEX_GUARD=threading.Lock()


def root_for(sessions):
    root=Path(sessions).resolve()/'paper_library'
    if root.resolve()!=root:raise ValueError('论文库目录不能是链接或目录联接。')
    return root


def checked(root,name):
    path=root/name
    if path.parent!=root or path.resolve()!=path:raise ValueError('论文库文件路径已重定向。')
    return path


def file_hash(path):
    sha=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):sha.update(block)
    return sha.hexdigest()


@contextmanager
def locked(root):
    with _MUTEX_GUARD:mutex=_MUTEXES.setdefault(str(root),threading.RLock())
    with mutex:
        checked(root,'session.lock')
        with session_lock(root):yield


def filename(value):
    if (not isinstance(value,str) or not 1<=len(value)<=180 or value!=value.strip()
            or re.search(r'[<>:"/\\|?*\x00-\x1f\x7f]',value) or value.endswith(('.', ' '))
            or not value.lower().endswith('.pdf')):
        raise ValueError('请上传名称有效的PDF文件；文件名不能包含路径。')
    return value


def index(root):
    path=checked(root,'index.json');checked(root,'index.json.tmp')
    value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':'paper_library_v1','papers':{}}
    if type(value) is not dict or set(value)!={'version','papers'} or value['version']!='paper_library_v1' or type(value['papers']) is not dict:
        raise ValueError('本地论文库索引无效。')
    if len(value['papers'])>MAX_PAPERS:raise ValueError('论文库数量超过限制。')
    for identity,row in value['papers'].items():
        if (not re.fullmatch(r'[a-f0-9]{64}',identity) or type(row) is not dict
                or set(row)!={'id','filename','sha256','bytes','page_count','uploaded_utc'}
                or row['id']!=identity or row['sha256']!=identity
                or type(row['bytes']) is not int or not 1<=row['bytes']<=MAX_FILE_BYTES
                or type(row['page_count']) is not int or row['page_count']<1 or type(row['uploaded_utc']) is not str):
            raise ValueError('本地论文元数据无效。')
        filename(row['filename']);checked(root,identity+'.pdf')
    return value


def listing(sessions):
    root=root_for(sessions)
    if not root.exists():return {'papers':[],'storage_root':str(root)}
    with locked(root):
        rows=index(root)['papers']
        return {'papers':sorted(rows.values(),key=lambda r:(r['uploaded_utc'],r['id']),reverse=True),'storage_root':str(root)}


def receive(service,name,length,stream,key):
    name=filename(name)
    if type(length) is not int or not 1<=length<=MAX_FILE_BYTES:raise ValueError('上传PDF须为1字节至64 MiB。')
    if not isinstance(key,str) or not 1<=len(key)<=200:raise ValueError('Idempotency-Key required (max 200 chars)')
    root=root_for(service.folder);root.mkdir(exist_ok=True)
    # The staging name is generated locally, never taken from a supplied filename.
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=root,prefix='.upload-',suffix='.pdf',delete=False) as out:
            temp=Path(out.name);remaining=length;sha=hashlib.sha256()
            while remaining:
                data=stream.read(min(65536,remaining))
                if not data:raise ValueError('上传未完成；请重新选择文件上传。')
                out.write(data);sha.update(data);remaining-=len(data)
        identity=sha.hexdigest();request_hash=digest(['paper_upload',name,identity,length])
        with service.request_lock(key):
            with service.lock:
                previous=service.requests.get(key)
            if previous:
                if previous['hash']!=request_hash:raise ValueError('Idempotency key payload mismatch')
                if previous.get('http_status',200)!=200:raise ValueError('上次上传未完成，请使用新的上传请求。')
                if 'result' not in previous:raise ValueError('上次上传完成状态不明，请先检查论文库。')
                return previous['result']
            with service.lock:
                service.requests[key]={'hash':request_hash,'status':'submitted','session_id':None}
                write_json(service.requests_path,service.requests)
            try:
                with locked(root):
                    value=index(root);papers=value['papers'];target=checked(root,identity+'.pdf')
                    if identity in papers:
                        actual=file_hash(target)
                        if actual!=identity:raise ValueError('已保存PDF的哈希不匹配，请检查本地论文库。')
                        row=papers[identity];duplicate=True
                    else:
                        if len(papers)>=MAX_PAPERS or sum(p['bytes'] for p in papers.values())+length>MAX_LIBRARY_BYTES:
                            raise ValueError('论文库达到100篇或1 GiB上限，请先整理本地库。')
                        info=parse_bytes(temp.read_bytes(),inspect=True)
                        row={'id':identity,'filename':name,'sha256':identity,'bytes':length,
                             'page_count':info['page_count'],'uploaded_utc':datetime.now(timezone.utc).isoformat()}
                        if target.exists():
                            actual=file_hash(target)
                            if actual!=identity:raise ValueError('论文库存储文件冲突。')
                        else:temp.replace(target)
                        papers[identity]=row;checked(root,'index.json.tmp');write_json(checked(root,'index.json'),value);duplicate=False
                    Workspace.open(root)
                    result={'paper':row,'duplicate':duplicate,'storage_root':str(root),'shared_with_model':False}
                with service.lock:
                    service.requests[key]={'hash':request_hash,'status':'complete','http_status':200,'result':result,'session_id':None}
                    write_json(service.requests_path,service.requests)
                return result
            except Exception:
                with service.lock:
                    service.requests[key]={'hash':request_hash,'status':'failed','http_status':409,'result':{'error':'UploadFailed'},'session_id':None}
                    write_json(service.requests_path,service.requests)
                raise
    finally:
        if temp is not None and temp.exists():
            if temp.parent==root and temp.resolve()==temp:temp.unlink()


def selection(session,identity):
    if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{64}',identity):raise ValueError('论文库编号无效。')
    root=root_for(session.folder.parent)
    if not root.is_dir():raise ValueError('本地论文库尚未上传PDF。')
    with locked(root):
        row=index(root)['papers'].get(identity)
        if row is None:raise ValueError('论文库编号不存在，请重新选择已上传PDF。')
        return Workspace.open(root,create=False),dict(row)
