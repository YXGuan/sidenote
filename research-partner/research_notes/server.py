"""Authenticated loopback bridge for the local Hypothesis extension."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import re
import secrets
import threading
from uuid import uuid4
from urllib.parse import parse_qs, urlsplit

from .hypothesis import sync
from .intelligence import accept_tags, analyze, fingerprint
from .maintenance import Maintenance, save_settings, settings as maintenance_settings
from .store import atomic_write, document_id


def pairing_key(vault):
    path = vault.root / ".local/bridge-token"
    with vault.lock():
        if not path.exists():
            atomic_write(path, secrets.token_urlsafe(32) + "\n")
        return path.read_text().strip()


def public_document(vault, doc):
    analysis = dict(doc["analysis"])
    if analysis:
        analysis["stale"] = analysis.get("input_hash") != fingerprint(doc, vault.personal_notes(doc["id"]))
    states = json.loads(json.dumps(doc["annotation_states"]))
    from .native import annotation_digest
    for annotation in doc["annotations"]:
        state = states.get(annotation["id"], {})
        if state.get("analysis"):
            state["analysis"]["stale"] = state["analysis"].get("input_hash") != annotation_digest(annotation)
    return {k: doc[k] for k in ("id", "url", "title", "tags", "page_tags", "manual_tags", "auto_tags", "classification", "classification_source", "classification_manual", "summary", "activity", "groups", "created_at", "updated_at", "reaction", "metadata", "annotations", "automatic_collections", "collection_signals")} | {"analysis": analysis, "annotation_states": states, "excluded_auto_tags": doc["overrides"].get("excluded_auto_tags", [])}


def library_document(vault, doc):
    from .store import quote_text
    fields = ("id", "url", "title", "manual_tags", "auto_tags", "classification", "classification_source", "summary", "activity", "groups", "reaction", "created_at", "updated_at", "metadata", "automatic_collections", "collection_signals")
    result = {key: doc[key] for key in fields}
    result.update(tags=doc["manual_tags"], custom_title=doc["overrides"].get("title", ""), annotation_ids=[a["id"] for a in doc["annotations"]])
    result["annotation_activity"] = {}
    for annotation in doc["annotations"]:
        day = annotation.get("created", "")[:10]
        if day:
            result["annotation_activity"][day] = result["annotation_activity"].get(day, 0) + 1
    result["search_text"] = "\n".join([vault.personal_notes(doc["id"])] + [a.get("text", "") + "\n" + quote_text(a) for a in doc["annotations"]])
    return result


def make_server(vault, port=8765):
    token = pairing_key(vault)
    job = {"state": "idle", "total": 0, "done": 0, "applied": 0, "failed": 0}
    job_lock = threading.Lock()
    maintenance = Maintenance(vault)
    research_job = {"state": "idle"}
    recommendation_job = {"state": "idle"}

    def run_recommendations():
        from .recommendations import refresh
        with job_lock:
            recommendation_job["state"] = "running"
        try:
            refresh(vault, approved=True)
            with job_lock:
                recommendation_job.update(state="completed")
        except ValueError as error:
            with job_lock:
                recommendation_job.update(state="failed", error=str(error))
        except Exception:
            with job_lock:
                recommendation_job.update(state="failed", error="Recommendations could not be refreshed. Semantic Scholar may be busy or rate limited; retry later or configure its API key in Settings. Previous results are retained.")

    def run_research(body):
        from . import knowledge
        with job_lock:
            research_job["state"] = "running"
        try:
            operation = body.get("operation")
            if operation == "find":
                result = knowledge.search(vault, body.get("query"), kind=body.get("kind", "links"),
                    offset=body.get("offset", 0), expand=body.get("expand") is True,
                    terms=body.get("terms"))
            elif operation == "ask":
                result = knowledge.ask(vault, body.get("query"), web=body.get("web", True), approved=body.get("approved") is True)
            elif operation == "build-wiki":
                result = knowledge.build_wiki(vault)
            elif operation == "synthesize":
                def report_wiki(status):
                    with job_lock:
                        research_job["progress"] = status
                result = knowledge.synthesize(vault, body.get("page_id"), approved=body.get("approved") is True, progress=report_wiki)
            elif operation == "kura":
                from .kura_analysis import run
                def report_kura(status):
                    with job_lock:
                        research_job["progress"] = status
                result = run(vault, approved=body.get("approved") is True, progress=report_kura)
                result = {k: v for k, v in result.items() if k != "summaries"}
            else:
                result = knowledge.lint_wiki(vault)
            with job_lock:
                research_job.update(state="completed", result=result)
        except (ValueError, RuntimeError) as error:
            with job_lock:
                research_job.update(state="failed", error=str(error))
        except Exception:
            with job_lock:
                research_job.update(state="failed", error="Research failed; check dependencies and model login. Saved notes are intact.")

    def report_job(status):
        with job_lock:
            job.update(status)

    def run_organization(force, provider=None, approved=False):
        from .organization import organize_library
        try:
            organize_library(vault, force=force, provider=provider, approved=approved, progress=report_job)
        except Exception:
            report_job({"state": "failed", "error": "Organization stopped; saved notes are intact. Retry after checking Codex login."})

    class Handler(BaseHTTPRequestHandler):
        server_version = "ResearchNotes/0.1"

        def log_message(self, *args):
            # URLs, titles, and errors can contain private research context.
            pass

        def origin_allowed(self):
            origin = self.headers.get("Origin")
            return origin is None or bool(re.fullmatch(r"chrome-extension://[a-p]{32}", origin))

        def local_request(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}" and self.origin_allowed()

        def authenticated(self):
            provided = self.headers.get("Authorization", "")
            return self.local_request() and hmac.compare_digest(provided.encode(), ("Bearer " + token).encode())

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            if origin and self.origin_allowed():
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            if not self.local_request():
                self.send_json(403, {"error": "Origin or Host rejected"})
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", "null"))
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self):
            if not self.local_request():
                self.send_json(403, {"error": "Origin or Host rejected"})
                return
            route = urlsplit(self.path)
            if route.path == "/health":
                self.send_json(200, {"ok": True, "service": "research-notes"})
                return
            if not self.authenticated():
                self.send_json(401, {"error": "Pair this extension using the key from ./notes pair"})
                return
            try:
                if route.path == "/api/account":
                    token = vault.token()
                    if not token:
                        self.send_json(409, {"error": "Configure your Hypothesis account with ./research-partner/notes configure, then retry login."})
                        return
                    self.send_json(200, {"access_token": token})
                elif route.path == "/api/document":
                    params = parse_qs(route.query)
                    key = document_id(params.get("url", [""])[0])
                    doc = vault.documents(include_removed=True).get(key)
                    self.send_json(200, {"document": public_document(vault, doc) if doc else None})
                elif route.path == "/api/library":
                    self.send_json(200, {"documents": [library_document(vault, doc) for doc in vault.documents().values()], "groups": vault.groups()})
                elif route.path == "/api/recommendations":
                    from .recommendations import state
                    result = state(vault)
                    with job_lock:
                        result["job"] = dict(recommendation_job)
                    self.send_json(200, result)
                elif route.path == "/api/research":
                    with job_lock:
                        self.send_json(200, {"job": dict(research_job)})
                elif route.path == "/api/wiki":
                    from .knowledge import wiki
                    self.send_json(200, wiki(vault))
                elif route.path == "/api/graph":
                    from .knowledge import graph
                    params = parse_qs(route.query)
                    self.send_json(200, graph(vault, query=params.get("query", [""])[0],
                        focus=params.get("focus", [""])[0], depth=int(params.get("depth", ["1"])[0]),
                        overview=params.get("overview", ["false"])[0] == "true"))
                elif route.path == "/api/kura":
                    from .kura_analysis import state, members
                    params = parse_qs(route.query)
                    if "cluster_id" in params:
                        self.send_json(200, members(vault, params["cluster_id"][0],
                            offset=int(params.get("offset", ["0"])[0])))
                    else:
                        result = state(vault)
                        self.send_json(200, {k: v for k, v in result.items() if k != "summaries"})
                elif route.path == "/api/groups":
                    self.send_json(200, {"groups": vault.groups()})
                elif route.path == "/api/saved-urls":
                    self.send_json(200, {"urls": vault.saved_urls()})
                elif route.path == "/api/organization":
                    from .organization import settings
                    with job_lock:
                        self.send_json(200, {"job": dict(job), "enrichment": maintenance.status()["enrichment"], "backup": maintenance.status()["backup"], "settings": settings(vault)})
                elif route.path == "/api/settings":
                    self.send_json(200, maintenance_settings(vault) | maintenance.status())
                elif route.path == "/api/status":
                    from .store import read_json
                    self.send_json(200, {"user": vault.config().get("user"), "authenticated_sync_available": bool(vault.token()), "documents": len(vault.documents()), "last_sync": read_json(vault.root / ".local/last-sync.json")})
                else:
                    self.send_json(404, {"error": "Route not found"})
            except (ValueError, KeyError, TypeError) as error:
                self.send_json(400, {"error": str(error)})

        def do_POST(self):
            if not self.authenticated():
                self.send_json(401, {"error": "Local bridge key or origin is invalid"})
                return
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self.send_json(415, {"error": "Use application/json"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 262144:
                    self.send_json(413, {"error": "Invalid request size"})
                    return
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError("Expected an object")
                if self.path == "/api/recommendations":
                    if body.get("approved") is not True:
                        raise ValueError("Choose Refresh recommendations to send paper identifiers and unresolved paper titles to Semantic Scholar")
                    with job_lock:
                        if recommendation_job["state"] in ("queued", "running"):
                            self.send_json(409, {"error": "Recommendations are already refreshing"})
                            return
                        recommendation_job.clear()
                        recommendation_job.update(state="queued")
                        status = dict(recommendation_job)
                    threading.Thread(target=run_recommendations, daemon=True).start()
                    self.send_json(202, {"job": status})
                    return
                elif self.path == "/api/research":
                    operation = body.get("operation")
                    if operation not in ("find", "ask", "build-wiki", "synthesize", "lint", "kura"):
                        raise ValueError("Unknown research operation")
                    if operation in ("ask", "synthesize", "kura") and body.get("approved") is not True:
                        raise ValueError("Authorize sending selected context to the model for this request")
                    with job_lock:
                        if research_job["state"] in ("queued", "running"):
                            self.send_json(409, {"error": "Another research request is running. Wait for it to finish."})
                            return
                        research_job.clear()
                        research_job.update(id=uuid4().hex, state="queued", operation=operation)
                        status = dict(research_job)
                    threading.Thread(target=run_research, args=(body,), daemon=True).start()
                    self.send_json(202, {"job": status})
                    return
                elif self.path == "/api/capture":
                    doc = vault.capture(body.get("url"), body.get("metadata", {}), visit=body.get("visit") is True)
                elif self.path == "/api/visit":
                    self.send_json(200, {"tracked": vault.visit_saved_page(body.get("url"))})
                    return
                elif self.path in ("/api/remove", "/api/restore"):
                    key = document_id(body.get("url"))
                    removed = self.path == "/api/remove"
                    vault.set_removed(key, removed)
                    self.send_json(200, {"removed": key} if removed else {"document": public_document(vault, vault.documents()[key])})
                    return
                elif self.path == "/api/enrich":
                    from .scholarly import enrich_document
                    doc = enrich_document(vault, body.get("document_id"), force=body.get("force") is True)
                elif self.path == "/api/enrich-library":
                    status = maintenance.start_job("enrichment", force=body.get("force") is True)
                    self.send_json(202, {"enrichment": status})
                    return
                elif self.path == "/api/settings":
                    result = save_settings(vault, body.get("preferences", {}), body.get("api_keys", {}))
                    maintenance.changed()
                    self.send_json(200, result | maintenance.status())
                    return
                elif self.path == "/api/backup":
                    self.send_json(202, {"backup": maintenance.start_job("backup")})
                    return
                elif self.path == "/api/groups":
                    self.send_json(200, {"groups": vault.create_group(body.get("name"))})
                    return
                elif self.path == "/api/organize":
                    from .organization import classifier
                    provider = body.get("provider")
                    approved = body.get("approved") is True
                    classifier(vault, provider, approved)
                    force = body.get("force", False)
                    if not isinstance(force, bool):
                        raise ValueError("force must be true or false")
                    with job_lock:
                        start = job["state"] not in ("running", "queued")
                        if start:
                            job.clear()
                            job.update(state="queued", total=0, done=0, applied=0, failed=0)
                        status = dict(job)
                    if start:
                        threading.Thread(target=run_organization, args=(force, provider, approved), daemon=True).start()
                    self.send_json(202, {"job": status})
                    return
                elif self.path == "/api/annotation":
                    from .native import mirror_annotation
                    doc = mirror_annotation(vault, body.get("annotation"), body.get("document"))
                elif self.path == "/api/suggest":
                    from .native import suggest_for_draft
                    self.send_json(200, {"analysis": suggest_for_draft(vault, body.get("annotation"))})
                    return
                elif self.path == "/api/annotation-reaction":
                    from .native import update_annotation_state
                    doc = update_annotation_state(vault, body.get("annotation_id"), reaction=body.get("reaction"))
                elif self.path == "/api/analyze-annotation":
                    from .native import analyze_annotation
                    doc = analyze_annotation(vault, body.get("annotation_id"))
                elif self.path == "/api/suggest-page":
                    from .native import suggest_for_page
                    doc = suggest_for_page(vault, body.get("document_id"), force=body.get("force") is True)
                elif self.path == "/api/update":
                    values = body.get("values")
                    if not isinstance(values, dict):
                        raise ValueError("Expected edit values")
                    doc = vault.update(body.get("document_id"), **values)
                elif self.path == "/api/analyze":
                    key = body.get("document_id")
                    analyze(vault, key)
                    doc = vault.documents()[key]
                elif self.path == "/api/accept-tags":
                    doc = accept_tags(vault, body.get("document_id"), body.get("tags"))
                elif self.path == "/api/sync":
                    # The caller must choose scope explicitly; no truthy strings.
                    if not isinstance(body.get("public_only"), bool):
                        raise ValueError("Choose public_only true or false")
                    status = sync(vault, public_only=body["public_only"])
                    maintenance.changed()
                    self.send_json(200, {"sync": status})
                    return
                else:
                    self.send_json(404, {"error": "Route not found"})
                    return
                self.send_json(200, {"document": public_document(vault, doc)})
                if self.path in ("/api/capture", "/api/annotation", "/api/update"):
                    maintenance.changed()
            except (ValueError, KeyError, TypeError) as error:
                self.send_json(400, {"error": str(error)})
            except (RuntimeError, OSError):
                self.send_json(502, {"error": "Operation failed. Check connectivity or Codex login, then retry; existing backups are retained."})

    class ResearchServer(ThreadingHTTPServer):
        def serve_forever(self, poll_interval=0.5):
            maintenance.start()
            super().serve_forever(poll_interval)

        def server_close(self):
            maintenance.close()
            super().server_close()
    server = ResearchServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
