"""Zotero compatibility with invented references and disposable vaults only."""
from http.client import HTTPConnection
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.cli import main
from research_notes.server import library_document, make_server, pairing_key
from research_notes.store import PERSONAL_MARKER, Vault, atomic_write, document_id, encoded, restore_snapshot
from research_notes.zotero import connection_settings, export_library, import_desktop, import_file, import_online, local_get, save_connection, web_get


def reference(**changes):
    return {"id": "https://www.zotero.org/users/123/items/TEST0001", "type": "article-journal",
            "title": "Synthetic learning study — café", "URL": "https://example.org/study",
            "DOI": "10.1234/synthetic", "author": [{"given": "Ada", "family": "Reader"}, {"literal": "Example Institute"}],
            "issued": {"date-parts": [[2024, 5, 12]]}, "container-title": "Invented Studies",
            "volume": "7", "issue": "2", "page": "10-18", **changes}


RIS = """TY  - JOUR
ID  - 1
TI  - Synthetic learning study — café
UR  - https://example.org/study
DO  - 10.1234/synthetic
AU  - Reader, Ada
PY  - 2024/05/12/
T2  - Invented Studies
KW  - learning
N1  - <p>First &amp; second<br/>Next line</p><script>hidden()</script>
ER  -
"""


class ZoteroTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Vault(Path(self.temp.name) / "vault")
        self.vault.initialize("synthetic_reader")

    def test_ris_repeat_import_preserves_raw_manual_edits_personal_notes_and_removed_items(self):
        self.assertEqual(import_file(self.vault, RIS)["created"], 1)
        key = document_id("https://example.org/study")
        self.vault.update(key, title="My title", tags=["curated"], reaction="bad", metadata={"authors": ["Corrected Author"], "doi": ""})
        path = self.vault.root / "library" / (key + ".md")
        with path.open("a") as handle:
            handle.write("A personal note.\n")
        stamp = self.vault.records("metadata")[key]["modified_at"]
        self.assertEqual(import_file(self.vault, RIS)["unchanged"], 1)
        self.assertEqual(self.vault.records("metadata")[key]["modified_at"], stamp)
        self.assertEqual(len(self.vault.records("imports")), 1)
        import_file(self.vault, RIS.replace("learning study", "updated study"))
        doc = self.vault.documents()[key]
        self.assertEqual(doc["title"], "My title")
        self.assertEqual(doc["reaction"], "bad")
        self.assertEqual(doc["manual_tags"], ["curated"])
        self.assertEqual(doc["reference_tags"], ["learning"])
        self.assertEqual(doc["metadata"]["authors"], ["Corrected Author"])
        self.assertEqual(doc["metadata"]["doi"], "")
        self.assertIn("A personal note.", self.vault.personal_notes(key))
        self.assertEqual(doc["annotations"], [])
        self.assertEqual(self.vault.records("raw"), {})
        self.vault.set_removed(key, True)
        import_file(self.vault, RIS)
        self.assertEqual(self.vault.documents(), {})
        self.assertEqual(export_library(self.vault)["references"], 0)

    def test_csl_structured_names_dates_and_extra_citation_fields_survive_export(self):
        item = reference()
        import_file(self.vault, json.dumps([item]), "csl-json")
        exported = json.loads(export_library(self.vault, format="csl-json")["content"])[0]
        for field in ("title", "author", "issued", "volume", "issue", "page", "DOI", "type"):
            self.assertEqual(exported[field], item[field])
        self.assertTrue(exported["id"].startswith("urn:sidenote:"))
        doc = next(iter(self.vault.documents().values()))
        self.vault.update(doc["id"], metadata={"authors": ["Manual Author"], "published": "2025", "doi": ""})
        exported = json.loads(export_library(self.vault, format="csl-json")["content"])[0]
        self.assertEqual(exported["author"], [{"literal": "Manual Author"}])
        self.assertEqual(exported["issued"], {"date-parts": [[2025]]})
        self.assertNotIn("DOI", exported)

    def test_doi_matches_existing_browser_capture_and_url_changes_keep_identity(self):
        self.vault.capture("https://publisher.example/paper", {"title": "Existing", "doi": "10.1234/synthetic"})
        item = reference()
        result = import_file(self.vault, json.dumps([item]), "csl-json")
        self.assertEqual(result["created"], 0)
        item.update(URL="https://example.org/new", DOI="10.1234/corrected")
        import_file(self.vault, json.dumps([item]), "csl-json")
        self.assertEqual(len(self.vault.documents()), 1)
        self.assertEqual(next(iter(self.vault.documents().values()))["url"], "https://publisher.example/paper")

    def test_unrelated_numeric_ids_do_not_merge_and_offline_books_have_stable_ids(self):
        items = [reference(id=1), reference(id=1, title="Another study", DOI="10.1234/another", URL="")]
        import_file(self.vault, json.dumps(items), "csl-json")
        self.assertEqual(len(self.vault.documents()), 2)
        book = reference(id=2, type="book", DOI="", URL="", ISBN="9780000000000")
        payload = json.dumps([book])
        import_file(self.vault, payload, "csl-json")
        self.assertEqual(import_file(self.vault, payload, "csl-json")["unchanged"], 1)
        self.assertTrue(any(doc["url"].startswith("urn:sidenote:reference:") for doc in self.vault.documents().values()))
        exported = export_library(self.vault, format="csl-json")["content"]
        import_file(self.vault, exported, "csl-json")
        self.assertEqual(len(self.vault.documents()), 3)

    def test_notes_roundtrip_escape_html_and_cannot_inject_ris_records(self):
        import_file(self.vault, RIS)
        doc = next(iter(self.vault.documents().values()))
        self.assertEqual(doc["reference_notes"], ["First & second\nNext line"])
        self.assertIn("First & second", library_document(self.vault, doc)["search_text"])
        self.assertIn("Imported reference notes", (self.vault.root / "library" / (doc["id"] + ".md")).read_text())
        atomic_write(self.vault.path("raw", "synthetic-annotation"), encoded({"id": "synthetic-annotation", "uri": doc["url"], "created": "2024-01-01T00:00:00Z", "text": "Comment <img src=x onerror=bad()>", "target": [{"selector": [{"type": "TextQuoteSelector", "exact": "Quoted evidence"}]}]}))
        self.vault.render()
        with (self.vault.root / "library" / (doc["id"] + ".md")).open("a") as handle:
            handle.write("Personal <thought>\nTY  - JOUR\n")
        no_notes = export_library(self.vault)["content"]
        self.assertNotIn("N1  -", no_notes)
        exported = export_library(self.vault, include_notes=True)["content"]
        self.assertIn("&lt;img", exported)
        self.assertEqual(exported.count("\nTY  -"), 0)
        self.assertIn("Quoted evidence", exported)
        other = Vault(Path(self.temp.name) / "other")
        other.initialize("another_reader")
        import_file(other, exported)
        notes = next(iter(other.documents().values()))["reference_notes"]
        self.assertIn("First & second\nNext line", notes)
        self.assertIn("Personal <thought>\nTY  - JOUR", notes)
        self.assertFalse(other.records("raw"))

    def test_invalid_batch_writes_nothing_and_rejects_paths_and_nonweb_urls(self):
        for payload, format in (("TY  - JOUR\nTI  - Missing end", "ris"),
                                (json.dumps([reference(), {"title": "No type"}]), "csl-json"),
                                (json.dumps([reference(URL="file:///tmp/private.pdf")]), "csl-json"),
                                (json.dumps([reference(URL="https://user:password@example.org")]), "csl-json"),
                                (json.dumps([reference(author="Ada")]), "csl-json")):
            with self.assertRaises(ValueError):
                import_file(self.vault, payload, format)
            self.assertFalse(self.vault.documents())
            self.assertFalse(self.vault.records("imports"))
        with self.assertRaises(ValueError):
            export_library(self.vault, document_ids=["../../escape"])

    def test_snapshot_restores_import_evidence_and_notes(self):
        import_file(self.vault, RIS)
        restored = restore_snapshot(self.vault.snapshot(), Path(self.temp.name) / "restored")
        for collection in ("imports", "references", "metadata"):
            self.assertEqual(restored.records(collection), self.vault.records(collection))
        self.assertEqual(export_library(restored, include_notes=True), export_library(self.vault, include_notes=True))

    def test_desktop_reads_paginated_library_and_child_notes_without_mutating_remote(self):
        rows = [{"data": {"key": "PAPER", "itemType": "journalArticle", "title": "Synthetic paper", "DOI": "10.1234/paper", "creators": [{"creatorType": "author", "firstName": "Ada", "lastName": "Reader"}], "tags": [{"tag": "topic"}]}}]
        rows += [{"data": {"key": f"N{i}", "itemType": "note", "parentItem": "PAPER", "note": f"<p>Note {i}</p>"}} for i in range(100)]
        rows += [{"data": {"key": "PDF", "itemType": "attachment", "parentItem": "PAPER"}},
                 {"data": {"key": "ANN", "itemType": "annotation", "parentItem": "PDF", "annotationText": "A PDF highlight", "annotationComment": "A reader comment"}}]
        calls = []
        def get(path, server_id):
            calls.append((path, server_id))
            start = int(parse_qs(urlsplit(path).query)["start"][0])
            return rows[start:start + 100], {"Zotero-Server-ID": "synthetic-db", "Last-Modified-Version": "42"}
        result = import_desktop(self.vault, get=get)
        self.assertEqual(result["created"], 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1], "synthetic-db")
        doc = next(iter(self.vault.documents().values()))
        self.assertEqual(len(doc["reference_notes"]), 101)
        self.assertIn("A PDF highlight\nA reader comment", doc["reference_notes"])
        self.assertEqual(doc["reference_tags"], ["topic"])
        self.assertEqual(import_desktop(self.vault, get=get)["unchanged"], 1)

    def test_desktop_library_changes_or_network_failure_do_not_write_partial_import(self):
        calls = []
        def get(path, server_id):
            calls.append(path)
            return [{"data": {"key": str(i), "itemType": "book", "title": str(i)}} for i in range(100)], {"Last-Modified-Version": str(len(calls))}
        with self.assertRaisesRegex(ValueError, "changed during import"):
            import_desktop(self.vault, get=get)
        self.assertFalse(self.vault.documents())
        self.assertFalse(self.vault.records("imports"))
        with patch("research_notes.zotero.build_opener") as opener:
            opener.return_value.open.side_effect = OSError("synthetic connectivity error")
            with self.assertRaisesRegex(ValueError, "Open Zotero"):
                local_get("users/0/items")

    def test_direct_import_handles_untitled_items_and_unusable_url_fields(self):
        rows = [{"data": {"key": "UNTITLED", "itemType": "book", "url": "file:///tmp/example.pdf"}}]
        result = import_desktop(self.vault, get=lambda path, server_id: (rows, {}))
        self.assertEqual(result["created"], 1)
        doc = next(iter(self.vault.documents().values()))
        self.assertEqual(doc["title"], "Untitled Zotero item UNTITLED")
        self.assertTrue(doc["url"].startswith("urn:sidenote:"))
        self.assertIn("file:///tmp/example.pdf", json.dumps(self.vault.records("imports")))

    def test_cli_uses_requested_vault_and_does_not_overwrite_export(self):
        input_path = Path(self.temp.name) / "input.ris"
        output_path = Path(self.temp.name) / "output.ris"
        input_path.write_text(RIS)
        with patch("sys.stdout", new_callable=io.StringIO), patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["--vault", str(self.vault.root), "zotero", "import", str(input_path)]), 0)
            self.assertEqual(main(["--vault", str(self.vault.root), "zotero", "export", str(output_path), "--include-notes"]), 0)
            self.assertEqual(main(["--vault", str(self.vault.root), "zotero", "export", str(output_path)]), 1)
        self.assertIn("N1  -", output_path.read_text())

    def test_online_credentials_are_local_write_only_and_excluded_from_backups(self):
        result = save_connection(self.vault, {"library_type": "users", "library_id": "12345", "api_key": "synthetic-zotero-key"})
        self.assertTrue(result["api_key"]["configured"])
        self.assertNotIn("synthetic-zotero-key", json.dumps(result))
        self.assertNotIn("synthetic-zotero-key", json.dumps(self.vault.config()))
        self.assertNotIn("synthetic-zotero-key", self.vault.snapshot().read_text())
        self.assertEqual(self.vault.env_file.stat().st_mode & 0o777, 0o600)
        save_connection(self.vault, {"library_type": "users", "library_id": "12345"})
        self.assertEqual(self.vault.secret("ZOTERO_API_KEY"), "synthetic-zotero-key")
        for values in ({"library_type": "users", "library_id": "../bad", "api_key": "replacement"},
                       {"library_type": "users", "library_id": "12345", "api_key": "bad\nvalue"}):
            with self.assertRaises(ValueError):
                save_connection(self.vault, values)
            self.assertEqual(self.vault.secret("ZOTERO_API_KEY"), "synthetic-zotero-key")
        save_connection(self.vault, {"library_type": "users", "library_id": "12345", "api_key": None})
        self.assertFalse(connection_settings(self.vault)["api_key"]["configured"])

    def test_online_library_uses_saved_id_and_key_and_matches_synced_desktop_items(self):
        save_connection(self.vault, {"library_type": "users", "library_id": "12345", "api_key": "synthetic-zotero-key"})
        rows = [{"key": "TEST0001", "library": {"type": "user", "id": 12345}, "data": {"key": "TEST0001", "itemType": "book", "title": "Offline book"}}]
        calls = []
        def get(path, key):
            calls.append((path, key))
            return rows, {"Last-Modified-Version": "5"}
        import_desktop(self.vault, get=lambda path, server_id: (rows, {"Zotero-Server-ID": "db", "Last-Modified-Version": "2"}))
        self.assertEqual(import_online(self.vault, get=get)["created"], 0)
        self.assertEqual(len(self.vault.documents()), 1)
        self.assertTrue(calls[0][0].startswith("users/12345/items?"))
        self.assertEqual(calls[0][1], "synthetic-zotero-key")
        save_connection(self.vault, {"library_type": "groups", "library_id": "456"})
        rows[0]["library"] = {"type": "group", "id": 456}
        import_online(self.vault, get=get)
        self.assertTrue(calls[-1][0].startswith("groups/456/items?"))
        self.assertEqual(len(self.vault.documents()), 2)

    def test_online_network_uses_official_https_header_auth_and_honors_rate_limits(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'[]'
        response.headers = {"Last-Modified-Version": "2", "Backoff": "1"}
        with patch("research_notes.zotero.build_opener") as build:
            opener = build.return_value
            opener.open.side_effect = [HTTPError("https://api.zotero.org", 429, "busy", {"Retry-After": "2"}, None), response]
            delays = []
            self.assertEqual(web_get("users/123/items", "synthetic-key", sleep=delays.append)[0], [])
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.zotero.org/users/123/items")
            self.assertEqual(request.get_header("Zotero-api-key"), "synthetic-key")
            self.assertNotIn("synthetic-key", request.full_url)
            self.assertEqual(delays, [2, 1])
            opener.open.side_effect = HTTPError("https://api.zotero.org", 403, "private error", {}, None)
            with self.assertRaisesRegex(ValueError, "denied access") as error:
                web_get("users/123/items", "synthetic-key")
            self.assertNotIn("synthetic-key", str(error.exception))

    def test_bridge_requires_pairing_imports_large_files_and_exports_selection(self):
        server = make_server(self.vault, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def request(path, body=None, auth=True, method="POST"):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            headers = {"Content-Type": "application/json"}
            if auth:
                headers["Authorization"] = "Bearer " + pairing_key(self.vault)
            connection.request(method, path, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result
        def wait_job():
            for _ in range(100):
                status, result = request("/api/zotero/import", method="GET")
                if result["job"]["state"] not in ("queued", "running"):
                    self.assertEqual(result["job"]["state"], "completed")
                    return result["job"]
                time.sleep(0.01)
            self.fail("Zotero import did not complete")
        try:
            for path in ("import", "desktop", "online", "export"):
                self.assertEqual(request("/api/references/" + path, {}, auth=False)[0], 401)
            payload = {"format": "ris", "content": RIS.replace("TI  -", "N1  - " + "x" * 270000 + "\nTI  -")}
            self.assertEqual(request("/api/references/import", payload)[0], 200)
            key = next(iter(self.vault.documents()))
            status, result = request("/api/references/export", {"document_ids": [key], "include_notes": True})
            self.assertEqual(status, 200)
            self.assertIn("N1  -", result["content"])
            self.assertEqual(request("/api/references/export", {"include_notes": "false"})[0], 400)
            with patch("research_notes.zotero.import_desktop", return_value={"references": 0}) as imported:
                self.assertEqual(request("/api/references/desktop", {})[0], 202)
                self.assertEqual(wait_job()["result"], {"references": 0})
                imported.assert_called_once_with(self.vault)
            self.assertEqual(request("/api/zotero", {}, auth=False)[0], 401)
            status, settings = request("/api/zotero", {"library_type": "users", "library_id": "12345", "api_key": "synthetic-zotero-key"})
            self.assertEqual(status, 200)
            self.assertNotIn("synthetic-zotero-key", json.dumps(settings))
            with patch("research_notes.zotero.import_online", return_value={"references": 0}) as online:
                self.assertEqual(request("/api/references/online", {})[0], 202)
                wait_job()
                online.assert_called_once_with(self.vault)
            self.assertEqual(request("/api/zotero/import", auth=False, method="GET")[0], 401)
            started, release = threading.Event(), threading.Event()
            def delayed(vault):
                started.set()
                release.wait(5)
                return {"references": 0}
            with patch("research_notes.zotero.import_online", side_effect=delayed):
                request("/api/references/online", {})
                self.assertTrue(started.wait(5))
                self.assertEqual(request("/api/references/desktop", {})[0], 409)
                release.set()
                wait_job()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
