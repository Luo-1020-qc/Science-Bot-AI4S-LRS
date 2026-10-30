"""Loopback-only HTTP entry with independent local token and idempotency."""
import argparse
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit, parse_qs
from .contracts import BudgetedResearchSpec
from .session import ScienceSession, ROOT
from .general.conversation import GeneralSession
from .workspace import Workspace
from ..util import canonical, digest, write_json
from . import session_history


class LocalService:
    def __init__(self, folder=None, workspace=None):
        self.workspace = Workspace.open(workspace) if workspace is not None else None
        self.folder = Path(folder).expanduser().resolve() if folder is not None else (self.workspace.sessions_dir if self.workspace else ROOT/"outputs"/"science_bot")
        self.folder.mkdir(parents=True, exist_ok=True)
        token_path = self.folder/".local_token"
        if not token_path.exists():
            token_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        self.token = token_path.read_text(encoding="utf-8").strip()
        self.lock, self.sessions, self.workers = threading.RLock(), {}, {}
        self.requests_path = self.folder/"http_requests.json"
        self.requests = json.loads(self.requests_path.read_text(encoding="utf-8")) if self.requests_path.exists() else {}
        self.request_locks = {}
        session_history.initialize(self)

    def session_access(self, session_id):
        return session_history.access(self,session_id)

    def delete_session(self, session_id):
        return session_history.delete(self,session_id)

    def request_lock(self, key):
        with self.lock:
            return self.request_locks.setdefault(key, threading.RLock())

    def session(self, session_id):
        if not re.fullmatch(r"[a-f0-9]{32}", session_id):
            raise ValueError("Invalid session identifier")
        with self.lock:
            if session_id in self.deleted_sessions:
                raise ValueError('该会话已删除，请选择其他研究或新建会话。')
            if session_id not in self.sessions:
                self.sessions[session_id] = ScienceSession.restore(self.folder/session_id,
                    workspace=self.workspace.root if self.workspace else None)
            return self.sessions[session_id]

    def run(self, session):
        def work():
            try:
                session.run()
            except Exception:
                pass  # Session persists and exposes the typed failure.
        with self.lock:
            old = self.workers.get(session.meta["id"])
            if old and old.is_alive():
                raise ValueError("Session is already running")
            worker = threading.Thread(target=work, daemon=True)
            self.workers[session.meta["id"]] = worker
            worker.start()


def make_server(folder=None, host="127.0.0.1", port=8765, *, workspace=None):
    if host != "127.0.0.1":
        raise ValueError("science Bot API binds only 127.0.0.1")
    service = LocalService(folder, workspace)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, code, result):
            raw = canonical(result).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers(); self.wfile.write(raw)

        def do_GET(self):
            self.handle_request(False)

        def do_POST(self):
            self.handle_request(True)

        def handle_request(self, mutate):
            if not secrets.compare_digest(self.headers.get("Authorization", ""), "Bearer "+service.token):
                # Drain a bounded submitted body before closing. On Windows an
                # unread POST body can turn the intended 401 into a TCP reset.
                try:
                    rejected_length = int(self.headers.get("Content-Length", "0"))
                    if 0 < rejected_length <= 65536:
                        self.connection.settimeout(2)
                        self.rfile.read(rejected_length)
                except (ValueError, OSError):
                    pass
                self.reply(401, {"error": "Local token required"}); return
            key = request_hash = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 65536:
                    raise ValueError("Request body too large")
                body = json.loads(self.rfile.read(length)) if length else {}
                if not isinstance(body, dict):
                    raise ValueError("JSON object required")
                parsed = urlsplit(self.path)
                parts = parsed.path.strip("/").split("/")
                if parts[:2] != ["v1", "sessions"]:
                    self.reply(404, {"error": "Unknown route"}); return
                key = self.headers.get("Idempotency-Key")
                request_hash = digest([self.path, body])
                if mutate and (not key or len(key) > 200):
                    raise ValueError("Idempotency-Key required (max 200 chars)")
                # Serialize identical POSTs without blocking event/status reads
                # or cancellation while another request is waiting on a model.
                with service.request_lock(key) if mutate else nullcontext(), service.session_access(parts[2] if len(parts)>=3 else None):
                    if mutate and key in service.requests:
                        previous = service.requests[key]
                        if previous["hash"] != request_hash:
                            raise ValueError("Idempotency key payload mismatch")
                        if "result" not in previous:
                            raise ValueError("Previous request has unknown completion; inspect the session before retrying")
                        self.reply(previous.get("http_status", 200), previous["result"]); return
                    if mutate:
                        with service.lock:
                            service.requests[key] = {"hash": request_hash, "status": "submitted",
                                                     "session_id": parts[2] if len(parts)>=3 else None}
                            write_json(service.requests_path, service.requests)
                    if len(parts) == 2 and mutate:
                        if set(body)-{"backend", "planner", "model", "spec"}:
                            raise ValueError("Unknown creation field; checkpoint paths are not accepted over HTTP")
                        session = GeneralSession.create(service.folder, backend=body.get("backend", "api"),
                            planner=body.get("planner", "rl"), model=body.get("model", "deepseek-flash"),
                            spec=BudgetedResearchSpec(**body["spec"]) if "spec" in body else None,
                            workspace=service.workspace.root if service.workspace else None)
                        service.sessions[session.meta["id"]] = session
                        result = session.status()
                    elif len(parts) >= 3:
                        session = service.session(parts[2])
                        route = parts[3] if len(parts) == 4 else "status"
                        if not mutate:
                            if route == "events":
                                after = int(parse_qs(parsed.query).get("after", [0])[0])
                                if after < 0:
                                    raise ValueError("Invalid event cursor")
                                result = {"events": session.events(after)}
                            elif route == "report":
                                report = session.research_report() if hasattr(session, "research_report") else session.env.state["report"]
                                if report is None:
                                    raise ValueError("Report not finalized")
                                result = report
                            elif route == "model-output":
                                result = session.model_output(parse_qs(parsed.query).get("call", ["latest"])[0])
                            elif route == "status":
                                result = session.status()
                            else:
                                raise ValueError("Unknown route")
                        elif route == "messages":
                            result = session.message(body.get("text", ""))
                        elif route == "confirm":
                            session.confirm(body.get("draft_hash")); result = session.status()
                        elif route == "resume":
                            if not session.status()["confirmed"]:
                                raise ValueError("Confirm current draft before resuming")
                            service.run(session); result = {"id": session.meta["id"], "accepted": True}
                        elif route == "cancel":
                            session.cancel()
                            old = service.workers.get(session.meta["id"])
                            if (not old or not old.is_alive()) and session.meta.get("engine_version") != "general_v1":
                                session.env.state["phase"] = "cancelled"; session.meta["phase"] = "cancelled"; session.save()
                            result = {"cancel_requested": True}
                        else:
                            raise ValueError("Unknown mutation route")
                    else:
                        raise ValueError("Unknown route")
                    if mutate:
                        with service.lock:
                            service.requests[key] = {"hash": request_hash, "result": result, "http_status": 200,
                                                     "status": "complete", "session_id": session.meta['id']}
                            write_json(service.requests_path, service.requests)
                self.reply(200, result)
            except (ValueError, KeyError, FileNotFoundError, TypeError) as exc:
                self.fail_request(mutate, key, request_hash, 409, {"error": type(exc).__name__, "detail": str(exc)[:160]})
            except Exception as exc:
                self.fail_request(mutate, key, request_hash, 503, {"error": type(exc).__name__})

        def fail_request(self, mutate, key, request_hash, status, result):
            with service.lock:
                previous = service.requests.get(key)
                if mutate and previous and previous["hash"] == request_hash and previous.get("status") == "submitted":
                    service.requests[key] = {"hash": request_hash, "result": result, "http_status": status,
                                             "status": "failed", "session_id": previous.get('session_id')}
                    write_json(service.requests_path, service.requests)
            self.reply(status, result)

    server = ThreadingHTTPServer((host, port), Handler)
    server.service = service
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--workspace", type=Path, help="Bind this server to a project selected by its operator")
    parser.add_argument("--sessions", type=Path)
    args = parser.parse_args(argv)
    server = make_server(args.sessions, args.host, args.port, workspace=args.workspace)
    print(f"science Bot API: http://127.0.0.1:{server.server_port}/v1/sessions", flush=True)
    print(f"Local token file: {server.service.folder / '.local_token'} (token not printed)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
