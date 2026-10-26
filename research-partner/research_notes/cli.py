"""Command line interface for setup, exports, local edits, and suggestions."""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

from . import __version__
from .hypothesis import sync
from .intelligence import accept_tags, analyze, codex_binary, codex_model
from .metadata import enrich
from .schedule import agent_definition, install, uninstall
from .server import make_server, pairing_key
from .store import Vault, read_json, restore_snapshot


def parser():
    root = argparse.ArgumentParser(description="Your Hypothesis annotations in a local, Git-friendly knowledge vault")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--vault", default=os.environ.get("NOTES_HOME") or str(Path(__file__).resolve().parents[1] / "vault"))
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a vault; no network requests")
    init.add_argument("--user", default="luke_ai")
    init.add_argument("--git", action="store_true", help="Initialize a separate local Git repository for the vault")
    commands.add_parser("configure", help="Enter a developer token through a hidden local prompt")
    doctor = commands.add_parser("doctor", help="Show readiness without printing credentials")
    doctor.add_argument("--json", action="store_true")
    fetch = commands.add_parser("sync", help="Export all accessible annotations; retain previous records")
    fetch.add_argument("--public-only", action="store_true")
    fetch.add_argument("--analyze", action="store_true", help="Send changed notes to headless Codex for tag/stance suggestions")
    listing = commands.add_parser("list", help="List document IDs for editing")
    listing.add_argument("--json", action="store_true")
    references = commands.add_parser("zotero", help="Import Zotero references or export a Zotero-compatible file")
    reference_commands = references.add_subparsers(dest="zotero_action", required=True)
    reference_import = reference_commands.add_parser("import", help="Import a UTF-8 RIS or CSL JSON file")
    reference_import.add_argument("file")
    reference_import.add_argument("--format", choices=("ris", "csl-json"))
    reference_commands.add_parser("desktop", help="Read references and notes from the running Zotero desktop app")
    reference_commands.add_parser("online", help="Read your configured Zotero online library")
    connection = reference_commands.add_parser("configure", help="Configure online access using a hidden API key prompt")
    connection.add_argument("--library-type", choices=("users", "groups"), default="users")
    connection.add_argument("--library-id", required=True)
    reference_export = reference_commands.add_parser("export", help="Write references for Zotero File → Import")
    reference_export.add_argument("file")
    reference_export.add_argument("--format", choices=("ris", "csl-json"), default="ris")
    reference_export.add_argument("--include-notes", action="store_true", help="Include highlights, comments and personal notes in RIS")
    reference_export.add_argument("--document", action="append", dest="document_ids", help="Export only this document ID (repeatable)")
    search = commands.add_parser("search", help="Search the local Markdown library")
    search.add_argument("query")
    find = commands.add_parser("find", help="Natural-language library search with BM25 and optional model query expansion")
    find.add_argument("query")
    find.add_argument("--kind", choices=("links", "annotations"), default="links")
    find.add_argument("--expand", action="store_true", help="Send only the search question to the model for synonyms")
    find.add_argument("--offset", type=int, default=0)
    ask = commands.add_parser("ask", help="Answer with library context and optional web research")
    ask.add_argument("query")
    ask.add_argument("--no-web", action="store_true")
    ask.add_argument("--allow-private-context", action="store_true")
    wiki = commands.add_parser("wiki", help="Build, inspect, lint, or synthesize the derived Markdown wiki")
    wiki.add_argument("action", choices=("build", "show", "lint", "export", "synthesize"))
    wiki.add_argument("--page")
    wiki.add_argument("--allow-private-context", action="store_true")
    graph = commands.add_parser("graph", help="Export the NetworkX knowledge graph as JSON")
    graph.add_argument("--query", default="")
    graph.add_argument("--focus", default="", help="Start from a graph node ID")
    graph.add_argument("--depth", type=int, choices=(1, 2, 3), default=1)
    graph.add_argument("--overview", action="store_true", help="Show the whole-library overview instead of a neighborhood")
    kura = commands.add_parser("kura", help="Cluster all annotations and personal notes with Kura")
    kura.add_argument("action", choices=("run", "show"))
    kura.add_argument("--allow-private-context", action="store_true", help="Send all annotation and note text to your signed-in model")
    title = commands.add_parser("title", help="Set a local title; an empty title restores the source title")
    title.add_argument("document_id")
    title.add_argument("title")
    reaction = commands.add_parser("react", help="Set your explicit reaction")
    reaction.add_argument("document_id")
    reaction.add_argument("reaction", choices=("like", "bad", "dislike", "clear"))
    tag = commands.add_parser("tag", help="Set locally curated tags")
    tag.add_argument("document_id")
    tag.add_argument("tags", nargs="*")
    ai = commands.add_parser("analyze", help="Suggest tags and infer stance through codex exec")
    ai.add_argument("document_id", nargs="?")
    ai.add_argument("--all", action="store_true")
    ai.add_argument("--force", action="store_true")
    accept = commands.add_parser("accept-tags", help="Accept AI tag suggestions locally")
    accept.add_argument("document_id")
    accept.add_argument("tags", nargs="*")
    meta = commands.add_parser("enrich", help="Fetch embedded citation metadata, optionally filling gaps from Crossref/Zotero")
    meta.add_argument("document_id")
    meta.add_argument("--no-crossref", action="store_true")
    meta.add_argument("--zotero-url")
    scholarly = commands.add_parser("enrich-research", help="Resolve research against OpenAlex and Semantic Scholar")
    scholarly.add_argument("document_id", nargs="?")
    scholarly.add_argument("--force", action="store_true")
    cache = commands.add_parser("cache-openalex", help="Save full OpenAlex API records and refresh topics/keywords for already indexed items")
    cache.add_argument("--force", action="store_true", help="Refresh even when a full local API record is less than seven days old")
    commands.add_parser("render", help="Rebuild Markdown while preserving personal notes")
    commands.add_parser("backup", help="Snapshot source records, metadata, edits, AI suggestions, and personal notes")
    restore = commands.add_parser("restore", help="Verify and restore a snapshot to an empty directory")
    restore.add_argument("snapshot")
    restore.add_argument("--to", required=True)
    serve = commands.add_parser("serve", help="Run the authenticated browser bridge on loopback")
    serve.add_argument("--port", type=int, default=8765)
    service = commands.add_parser("service", help="Manage the persistent macOS local storage service")
    service_action = service.add_mutually_exclusive_group()
    service_action.add_argument("--install", action="store_true", help="Start now and automatically at login; restart after exits")
    service_action.add_argument("--uninstall", action="store_true", help="Stop and remove the background service")
    service_action.add_argument("--status", action="store_true", help="Show whether the background service is running (default)")
    commands.add_parser("pair", help="Print the local browser pairing key; do not share it")
    preferences = commands.add_parser("categorization", help="Configure automatic categorization (local by default)")
    preferences.add_argument("--provider", choices=("local", "codex"))
    preferences.add_argument("--automatic", choices=("on", "off"))
    preferences.add_argument("--allow-private-context", action="store_true", help="Authorize ongoing Codex categorization of saved page context")
    organize = commands.add_parser("organize", help="Create automatic link-type, topic and subtopic groups")
    organize.add_argument("--provider", choices=("local", "codex"), help="Override the configured classifier for this run")
    organize.add_argument("--force", action="store_true", help="Refresh even unchanged page classifications")
    organize.add_argument("--allow-private-context", action="store_true", help="Authorize sending saved titles, URLs, metadata and selected notes to your signed-in Codex service")
    schedule = commands.add_parser("schedule", help="Preview or install a per-user daily macOS sync")
    schedule.add_argument("--hour", type=int, default=3)
    schedule.add_argument("--minute", type=int, default=0)
    schedule.add_argument("--public-only", action="store_true")
    schedule.add_argument("--analyze", action="store_true")
    action = schedule.add_mutually_exclusive_group()
    action.add_argument("--install", action="store_true")
    action.add_argument("--uninstall", action="store_true")
    return root


def print_json(value):
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main(argv=None):
    args = parser().parse_args(argv)
    vault = Vault(args.vault)
    try:
        if args.command == "init":
            vault.initialize(args.user)
            if args.git:
                git = shutil.which("git")
                if not git:
                    raise RuntimeError("Git is not installed")
                if not (vault.root / ".git").exists():
                    subprocess.run([git, "init", "--quiet", str(vault.root)], check=True)
            print(f"Vault ready: {vault.root}\nUser: {args.user}\nLocal categorization runs automatically after imports.\nNext: ./notes sync --public-only (or ./notes configure for private annotations)")
        elif args.command == "zotero":
            from .zotero import MAX_BYTES, export_library, import_desktop, import_file, import_online, save_connection, validate_connection
            if args.zotero_action == "import":
                path = Path(args.file).expanduser()
                if path.stat().st_size > MAX_BYTES:
                    raise ValueError("Reference file must be at most 10 MB")
                format = args.format or ("ris" if path.suffix.lower() == ".ris" else "csl-json")
                print_json(import_file(vault, path.read_text(encoding="utf-8-sig"), format))
            elif args.zotero_action == "desktop":
                print_json(import_desktop(vault))
            elif args.zotero_action == "online":
                print_json(import_online(vault))
            elif args.zotero_action == "configure":
                validate_connection(args.library_type, args.library_id)
                key = getpass.getpass("Zotero API key (input hidden; blank keeps saved key): ").strip()
                print_json(save_connection(vault, {"library_type": args.library_type, "library_id": args.library_id, **({"api_key": key} if key else {})}))
            else:
                from .store import atomic_write
                result = export_library(vault, format=args.format, include_notes=args.include_notes, document_ids=args.document_ids)
                path = Path(args.file).expanduser()
                if path.exists():
                    raise ValueError("Export destination already exists; choose a new filename")
                atomic_write(path, result["content"])
                print_json({"file": str(path), "references": result["references"]})
        elif args.command == "configure":
            if not vault.config().get("user"):
                raise ValueError("Initialize this vault first")
            token = getpass.getpass("Hypothesis developer token (input hidden): ").strip()
            if not token or len(token) > 4096 or any(c.isspace() for c in token):
                raise ValueError("Invalid developer token")
            from .hypothesis import HypothesisClient
            client = HypothesisClient(vault.config()["user"], token)
            profile = client.get("https://hypothes.is/api/profile", token=token)
            if profile.get("userid") != client.account:
                raise ValueError("Token does not match this vault's user")
            vault.configure(hypothesis_token=token)
            print(f"Token verified and saved in {vault.env_file} (mode 600; excluded from Git and snapshots).")
        elif args.command == "doctor":
            from .schedule import label_for
            from .service import status as bridge_status
            last_sync = read_json(vault.root / ".local/last-sync.json")
            if last_sync:
                last_sync = {k: v for k, v in last_sync.items() if k != "latest_ids"}
            values = {"vault": str(vault.root), "user": vault.config().get("user"), "python": sys.version.split()[0], "codex_available": bool(codex_binary()), "codex_binary": codex_binary(), "codex_model": codex_model(), "hypothesis_token_configured": bool(vault.token()), "documents": len(vault.documents()), "last_sync": last_sync, "launch_agent": str(Path.home() / "Library/LaunchAgents" / (label_for(vault) + ".plist"))}
            values["storage_service"] = bridge_status(vault)
            print_json(values)
        elif args.command == "sync":
            result = sync(vault, public_only=args.public_only)
            print_json({k: v for k, v in result.items() if k != "latest_ids"})
            if args.analyze:
                for key in vault.documents():
                    analyze(vault, key)
                # Capture the new derived suggestions as well as source data.
                with vault.lock():
                    print(f"Analysis snapshot: {vault.snapshot(result)}")
        elif args.command == "list":
            docs = [{k: d[k] for k in ("id", "title", "url", "tags", "reaction")} for d in vault.documents().values()]
            if args.json:
                print_json(docs)
            else:
                for doc in docs:
                    print(f"{doc['id']}  {doc['title']}")
        elif args.command in ("find", "ask", "wiki", "graph"):
            from . import knowledge
            if args.command == "find":
                result = knowledge.search(vault, args.query, kind=args.kind, offset=args.offset, expand=args.expand)
            elif args.command == "ask":
                result = knowledge.ask(vault, args.query, web=not args.no_web, approved=args.allow_private_context)
            elif args.command == "graph":
                result = knowledge.graph(vault, query=args.query, focus=args.focus, depth=args.depth, overview=args.overview)
            elif args.action == "build":
                result = knowledge.build_wiki(vault)
            elif args.action == "lint":
                result = knowledge.lint_wiki(vault)
            elif args.action == "export":
                result = {"directory": knowledge.export_wiki(vault)}
            elif args.action == "synthesize":
                result = knowledge.synthesize(vault, args.page, approved=args.allow_private_context)
            else:
                result = knowledge.wiki(vault)
            print_json(result)
        elif args.command == "kura":
            from . import kura_analysis
            if args.action == "run":
                last_progress = {}
                def report_kura(status):
                    if status != last_progress:
                        print(json.dumps(status), file=sys.stderr, flush=True)
                        last_progress.clear()
                        last_progress.update(status)
                result = kura_analysis.run(vault, approved=args.allow_private_context,
                    progress=report_kura)
            else:
                result = kura_analysis.state(vault)
            # Avoid printing private summaries and subjects during routine CLI use.
            print_json({k: v for k, v in result.items() if k not in ("clusters", "summaries")})
        elif args.command == "search":
            for file in sorted((vault.root / "library").glob("*.md")):
                content = file.read_text()
                if args.query.casefold() in content.casefold():
                    print(f"{file.stem}  {vault.documents().get(file.stem, {}).get('title', '')}\n  {file}")
        elif args.command in ("title", "react", "tag"):
            if args.command == "title":
                values = {"title": args.title}
            elif args.command == "react":
                values = {"reaction": None if args.reaction == "clear" else args.reaction}
            else:
                values = {"tags": args.tags}
            vault.update(args.document_id, **values)
            print("Saved locally and updated Markdown.")
        elif args.command == "analyze":
            if bool(args.document_id) == bool(args.all):
                raise ValueError("Choose a document ID or --all")
            for key in (list(vault.documents()) if args.all else [args.document_id]):
                print_json({"document_id": key, "analysis": analyze(vault, key, force=args.force)})
        elif args.command == "accept-tags":
            doc = accept_tags(vault, args.document_id, args.tags or None)
            print_json({"tags": doc["tags"]})
        elif args.command == "enrich":
            print_json(enrich(vault, args.document_id, crossref=not args.no_crossref, zotero_url=args.zotero_url))
        elif args.command == "enrich-research":
            from .scholarly import enrich_document, enrich_library
            if args.document_id:
                doc = enrich_document(vault, args.document_id, force=args.force)
                print_json({"document_id": doc["id"], "lookup": doc["metadata"].get("scholarly_lookup"), "openalex_id": doc["metadata"].get("openalex_id"), "semantic_scholar_id": doc["metadata"].get("semantic_scholar_id")})
            else:
                print_json(enrich_library(vault, force=args.force, progress=print_json))
        elif args.command == "cache-openalex":
            from .scholarly import cache_openalex
            print_json(cache_openalex(vault, force=args.force, progress=print_json))
        elif args.command == "render":
            with vault.lock():
                vault.render()
            print("Markdown rebuilt; personal notes preserved.")
        elif args.command == "backup":
            with vault.lock():
                print(vault.snapshot())
        elif args.command == "restore":
            restored = restore_snapshot(args.snapshot, args.to)
            print(f"Verified and restored {len(restored.records('raw'))} annotations to {restored.root}")
        elif args.command == "categorization":
            from .organization import settings
            values = {}
            if args.provider:
                if args.provider == "codex" and not args.allow_private_context and vault.config().get("codex_context_approved") is not True:
                    raise ValueError("Codex receives saved titles, URLs, metadata and selected highlights/comments/personal notes. Use --allow-private-context to authorize ongoing categorization.")
                values.update(classifier=args.provider, codex_context_approved=args.provider == "codex")
            if args.automatic:
                values["auto_categorize"] = args.automatic == "on"
            if values:
                vault.configure(**values)
            print_json(settings(vault))
        elif args.command == "organize":
            from .organization import organize_library
            result = organize_library(vault, force=args.force, provider=args.provider, approved=args.allow_private_context, progress=lambda status: print_json(status))
            return 1 if result["failed"] else 0
        elif args.command == "pair":
            print(pairing_key(vault))
        elif args.command == "serve":
            if not vault.config().get("user"):
                raise ValueError("Initialize this vault first")
            server = make_server(vault, args.port)
            print(f"Browser bridge: http://127.0.0.1:{server.server_port}\nAlready-paired browsers reconnect automatically. Press Ctrl-C to stop.", flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
        elif args.command == "service":
            from . import service
            if args.install:
                print(f"Background storage service installed: {service.install(vault)}")
            elif args.uninstall:
                print(f"Background storage service removed: {service.uninstall(vault)}")
            else:
                print_json(service.status(vault))
        elif args.command == "schedule":
            if not vault.config().get("user"):
                raise ValueError("Initialize this vault first")
            options = {"hour": args.hour, "minute": args.minute, "public_only": args.public_only, "analyze": args.analyze}
            if args.uninstall:
                print(f"Daily sync removed: {uninstall(vault)}")
            elif args.install:
                print(f"Daily sync installed: {install(vault, **options)}")
            else:
                print(plistlib.dumps(agent_definition(vault, **options)).decode())
    except KeyboardInterrupt:
        return 130
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0
