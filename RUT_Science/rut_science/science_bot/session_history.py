"""Delete one app-owned session; keep tombstones and scrub HTTP replay caches."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading

from ..util import write_json


def valid_id(identity):
    if not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{32}',identity):
        raise ValueError('Invalid session identifier')
    return identity


def initialize(service):
    service.session_locks={}
    service.session_active={}
    service.deleted_path=service.folder/'.deleted_sessions.json'
    deleted=json.loads(service.deleted_path.read_text(encoding='utf-8')) if service.deleted_path.exists() else []
    if not isinstance(deleted,list):raise ValueError('Invalid deleted-session index')
    service.deleted_sessions={valid_id(i) for i in deleted}


def session_mutex(service,identity):
    valid_id(identity)
    with service.lock:
        return service.session_locks.setdefault(identity,threading.RLock())


@contextmanager
def access(service,identity):
    if identity is None:
        yield
        return
    valid_id(identity)
    with service.lock:
        if identity in service.deleted_sessions:raise ValueError('该会话已删除，请选择其他研究或新建会话。')
        service.session_active[identity]=service.session_active.get(identity,0)+1
    try:
        yield
    finally:
        with service.lock:
            service.session_active[identity]-=1
            if not service.session_active[identity]:service.session_active.pop(identity)


def _reparse(path):
    info=path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,'st_file_attributes',0) & getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024))


def checked_target(base,identity):
    """Verify the exact absolute subtree before any recursive removal on Windows."""
    valid_id(identity)
    base=Path(base).absolute(); target=base/identity
    if base.resolve()!=base or target.resolve()!=target or target.parent!=base:
        raise ValueError('会话路径已重定向，未执行删除。')
    if not target.exists():return target
    if not target.is_dir() or _reparse(target):raise ValueError('会话目录无效，未执行删除。')
    def failed(error):raise error
    for root,folders,files in os.walk(target,followlinks=False,onerror=failed):
        for name in folders+files:
            if _reparse(Path(root)/name):raise ValueError('会话含链接或目录联接，未执行删除。')
    return target


def delete(service,identity):
    valid_id(identity)
    mutex=session_mutex(service,identity)
    if not mutex.acquire(blocking=False):raise ValueError('该会话正在处理请求，请等待完成后再删除。')
    try:
        with service.lock:
            if service.session_active.get(identity):raise ValueError('该会话正在处理请求，请等待完成后再删除。')
            worker=service.workers.get(identity)
            if worker and worker.is_alive():raise ValueError('该会话正在运行，请先停止任务后再删除。')
            target=checked_target(service.folder,identity)
            already=identity in service.deleted_sessions
            if not target.exists() and not already:raise ValueError('会话不存在，请刷新历史列表。')
            if target.exists() and not already:
                meta=target/'session.json'
                if not meta.is_file() or json.loads(meta.read_text(encoding='utf-8')).get('id')!=identity:
                    raise ValueError('目录不是当前应用的会话，未执行删除。')
            if target.exists():
                from ..planning_agent import session_lock
                with session_lock(target):pass  # Reject a live terminal/other-process writer before removing any record.
            cached=service.sessions.get(identity)
            lock=getattr(cached,'lock',None)
            if lock and not lock.acquire(blocking=False):raise ValueError('该会话正在处理，请稍后再删除。')
            try:
                # Legacy requests did not record their session owner. Scrub their
                # cached payloads too, retaining hashes/status so retries cannot
                # silently repeat old model/tool operations. Other sessions'
                # actual records and newly scoped replay results stay intact.
                requests={}
                for key,row in service.requests.items():
                    if row.get('session_id')==identity or not row.get('session_id'):
                        requests[key]={'hash':row['hash'],'session_id':row.get('session_id'),
                            'status':'history_deleted','http_status':410,
                            'result':{'error':'HistoryDeleted','detail':'该历史请求的缓存已清理，请查看当前会话状态。'}}
                    else:requests[key]=row
                write_json(service.requests_path,requests)
                service.requests=requests
                deleted=service.deleted_sessions|{identity}
                write_json(service.deleted_path,sorted(deleted))
                service.deleted_sessions=deleted
                service.sessions.pop(identity,None);service.workers.pop(identity,None)
                # Repeat validation immediately before recursive deletion. A
                # failed cleanup stays tombstoned; repeating this operation can
                # finish it without restoring or recreating the old session.
                checked_target(service.folder,identity)
                if target.exists():shutil.rmtree(target)
            finally:
                if lock:lock.release()
        return {'deleted':identity,'already_deleted':already}
    finally:
        mutex.release()
