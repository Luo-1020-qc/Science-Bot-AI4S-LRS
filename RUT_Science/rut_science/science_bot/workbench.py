"""Local browser workbench. Reuses the existing authenticated session service."""
import argparse
import json
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit
import webbrowser

from .api import make_server
from .interface_demo import create_example, example_state
from .presentation import session_view, example_view, export_plan, delivery_html, terminal_preview_html
from .general.planning.runtime import _plan
from ..util import canonical, digest, write_json

ASSETS = Path(__file__).with_name('workbench_assets')/'dist'


def make_workbench(folder=None, host='127.0.0.1', port=8765, *, workspace=None):
    server = make_server(folder, host, port, workspace=workspace)
    base = server.RequestHandlerClass
    service = server.service

    class Handler(base):
        def guard(self):
            allowed = {f'127.0.0.1:{server.server_port}', f'localhost:{server.server_port}'}
            host_header = self.headers.get('Host', '')
            origin = self.headers.get('Origin')
            if (host_header not in allowed or origin and origin != 'http://'+host_header
                    or self.headers.get('Sec-Fetch-Site') == 'cross-site'):
                self.reply(403, {'error': 'Local origin required'}); return False
            return True

        def authorized(self):
            if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+service.token):
                if self.command == 'POST':
                    try:
                        size = int(self.headers.get('Content-Length', '0'))
                        if 0 < size <= 65536:self.rfile.read(size)
                    except (ValueError, OSError):pass
                self.reply(401, {'error': 'Local token required'}); return False
            return True

        def reply(self, code, result):
            self.send_content(canonical(result), 'application/json; charset=utf-8', code=code)

        def send_content(self, content, kind, *, filename=None, document=False, code=200):
            raw = content if isinstance(content, bytes) else content.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src "+("'none'" if document else "'self'")+
                "; style-src 'self' "+("'unsafe-inline'" if document else '')+"; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            if filename:
                self.send_header('Content-Disposition', 'attachment; filename="'+filename+'"')
            self.end_headers();self.wfile.write(raw)

        def do_GET(self):
            if not self.guard(): return
            path = urlsplit(self.path).path
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'application/javascript; charset=utf-8'),
                      '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
            if path in assets:
                name, kind = assets[path]
                self.send_content((ASSETS/name).read_bytes(), kind); return
            if path == '/demo.json':
                self.send_content(canonical(example_view()), 'application/json; charset=utf-8'); return
            if path in {'/demo-delivery.html', '/terminal'}:
                content = terminal_preview_html() if path == '/terminal' else delivery_html(_plan(example_state()))
                self.send_content(content, 'text/html; charset=utf-8', document=True); return
            if not path.startswith('/ui/'):
                return super().do_GET()
            if not self.authorized(): return
            try:
                if path == '/ui/sessions':
                    rows = []
                    for folder in sorted(service.folder.iterdir(), key=lambda p: p.name, reverse=True):
                        if not re.fullmatch(r'[a-f0-9]{32}', folder.name) or not folder.is_dir(): continue
                        if len(rows) >= 100: break
                        if folder.name in service.deleted_sessions:
                            rows.append({'id':folder.name,'title':'删除未完成 · '+folder.name[:8],
                                'backend':'offline','example':False,'deletion_pending':True})
                            continue
                        try:
                            session = service.session(folder.name)
                            view = session_view(session)
                            chat_title=next((m['content'][:80] for m in session.meta.get('messages',[]) if m.get('role')=='user'),'尚未命名的研究')
                            rows.append({'id': view['id'], 'title': (view['planning'] or {}).get('title', chat_title),
                                         'backend': view['backend'], 'example': view['example']})
                        except (ValueError, OSError, KeyError):
                            continue
                    self.reply(200, {'sessions': rows}); return
                match = re.fullmatch(r'/ui/sessions/([a-f0-9]{32})(?:/(delivery\.(?:html|md|json)))?', path)
                if not match: raise ValueError('Unknown workbench route')
                session = service.session(match[1])
                if not match[2]:
                    self.reply(200, session_view(session)); return
                state, plan, json_path = export_plan(session)
                suffix = match[2].rsplit('.', 1)[1]
                filename = 'science-bot-plan-'+json_path.stem+'.'+suffix
                if suffix == 'html':
                    self.send_content(delivery_html(plan), 'text/html; charset=utf-8', filename=filename, document=True)
                elif suffix == 'json':
                    self.send_content(json_path.read_bytes(), 'application/json; charset=utf-8', filename=filename)
                else:
                    source = session.folder/state['last_export']['markdown_ref']
                    if source.resolve() != source.absolute() or not source.is_file() or not source.is_relative_to(session.folder):
                        raise ValueError('Invalid delivery path')
                    self.send_content(source.read_bytes(), 'text/markdown; charset=utf-8', filename=filename)
            except (ValueError, OSError, KeyError) as exc:
                self.reply(409, {'error': type(exc).__name__, 'detail': str(exc)[:160]})

        def do_POST(self):
            if not self.guard(): return
            delete_match=re.fullmatch(r'/ui/sessions/([a-f0-9]{32})/delete',urlsplit(self.path).path)
            if delete_match:
                if not self.authorized():return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 1<=length<=256:raise ValueError('Explicit session deletion confirmation required')
                    body=json.loads(self.rfile.read(length))
                    if body!={'confirm':delete_match[1]}:raise ValueError('删除确认必须对应当前会话。')
                    self.reply(200,service.delete_session(delete_match[1]))
                except (ValueError,OSError,KeyError) as exc:
                    self.reply(409,{'error':type(exc).__name__,'detail':str(exc)[:160]})
                return
            if urlsplit(self.path).path != '/ui/example':
                return super().do_POST()
            if not self.authorized(): return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 100: raise ValueError('Empty example request required')
                body = json.loads(self.rfile.read(length)) if length else {}
                if body != {}: raise ValueError('Example does not accept model, file or execution parameters')
                key = self.headers.get('Idempotency-Key', '')
                if not key or len(key) > 200: raise ValueError('Idempotency-Key required')
                request_hash = digest([self.path, body])
                with service.request_lock(key):
                    if key in service.requests:
                        previous = service.requests[key]
                        if previous['hash'] != request_hash: raise ValueError('Idempotency key payload mismatch')
                        if 'result' not in previous:raise ValueError('Previous example request has unknown completion; inspect saved sessions before retrying')
                        self.reply(previous.get('http_status',200), previous['result']);return
                    with service.lock:
                        service.requests[key] = {'hash': request_hash, 'status': 'submitted'}
                        write_json(service.requests_path, service.requests)
                    session = create_example(service.folder, workspace=service.workspace.root if service.workspace else None)
                    service.sessions[session.meta['id']] = session
                    result = session_view(session)
                    with service.lock:
                        service.requests[key] = {'hash': request_hash, 'result': result, 'http_status': 200,
                                                 'status': 'complete', 'session_id':session.meta['id']}
                        write_json(service.requests_path, service.requests)
                    self.reply(200, result)
            except (ValueError, OSError, KeyError) as exc:
                self.reply(409, {'error': type(exc).__name__, 'detail': str(exc)[:160]})

    server.RequestHandlerClass = Handler
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description='Science Bot 本地研究工作台')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--sessions', type=Path)
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--example', action='store_true')
    parser.add_argument('--backend', choices=['api','offline'], default='api')
    parser.add_argument('--model', default='deepseek-flash')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args(argv)
    try:
        server = make_workbench(args.sessions, port=args.port, workspace=args.workspace)
    except OSError:
        print('本地端口不可用。请检查已有服务，或使用 -Port 指定其他端口。', flush=True)
        return 2
    url = f'http://127.0.0.1:{server.server_port}/'
    fragment = '#access='+server.service.token
    if args.example:
        session = create_example(server.service.folder, workspace=server.service.workspace.root if server.service.workspace else None)
    else:
        from .general.conversation import GeneralSession
        session = GeneralSession.create(server.service.folder, backend=args.backend, model=args.model,
            workspace=server.service.workspace.root if server.service.workspace else None)
    server.service.sessions[session.meta['id']] = session
    fragment += '&session='+session.meta['id']
    print('Science Bot 浏览器工作台：'+url, flush=True)
    print('公开地址展示合成界面；启动器打开的浏览器连接本地会话。Ctrl+C 停止服务。', flush=True)
    if not args.no_browser:
        # The capability stays in a URL fragment, never HTTP access logs or stdout;
        # the app consumes it into memory then immediately clears the address bar.
        webbrowser.open(url+fragment)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__': raise SystemExit(main())
