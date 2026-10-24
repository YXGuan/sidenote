from http.client import HTTPConnection
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes import kura_analysis as k
from research_notes.native import mirror_annotation
from research_notes.server import make_server, pairing_key
from research_notes.store import Vault, atomic_write, encoded, restore_snapshot


def fixture(records):
    ids = [r["id"] for r in records]
    return {"clusters": [{"id": "synthetic", "name": "Synthetic research", "description": "Invented test evidence.",
        "parent_id": None, "children": [], "root_id": "synthetic", "level": 0,
        "chat_ids": ids, "count": len(ids), "x": 0., "y": 0.}],
        "summaries": {key: "Synthetic summary" for key in ids}}


def repeated_fixture(records):
    result = fixture(records)
    for index in range(3):
        child = result["clusters"][0]
        parent = child | {"id": f"wrapper-{index}", "parent_id": None,
                          "children": [child["id"]], "level": 0, "root_id": f"wrapper-{index}"}
        child["parent_id"] = parent["id"]
        for cluster in result["clusters"]:
            cluster["level"] += 1
            cluster["root_id"] = parent["id"]
        result["clusters"].insert(0, parent)
    return result


class KuraTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Vault(Path(self.temp.name) / "vault")
        self.vault.initialize("reader")
        self.vault.configure(auto_categorize=False)
        self.doc = self.vault.capture("https://example.org/synthetic", {"title": "Synthetic research"})
        mirror_annotation(self.vault, {"id": "synthetic", "uri": self.doc["url"], "user": "acct:reader@hypothes.is",
            "text": "I disagree with this claim.", "created": "2026-10-01T00:00:00Z",
            "target": [{"selector": [{"type": "TextQuoteSelector", "exact": "Invented source claim."}]}]})
        path = self.vault.root / "library" / (self.doc["id"] + ".md")
        path.write_text(path.read_text() + "\nPersonal synthetic observation.\n")
        self.vault.update(self.doc["id"], reaction="bad")

    def test_repeated_saved_topics_are_compacted_without_reanalysis_or_rewriting(self):
        records = k.evidence(self.vault)
        original = repeated_fixture(records)
        k.validate(original, records)
        result = k.run(self.vault, approved=True, pipeline=lambda _r: original)
        self.assertEqual([c["id"] for c in result["clusters"]], ["synthetic"])
        self.assertEqual(result["clusters"][0]["level"], 0)
        self.assertIsNone(result["clusters"][0]["parent_id"])
        self.assertEqual(result["clusters"][0]["root_id"], "synthetic")
        self.assertEqual(result["cluster_aliases"], {f"wrapper-{i}": "synthetic" for i in range(3)})
        k.validate(result, records)
        saved_path = self.vault.root / "knowledge/kura.json"
        saved_bytes = saved_path.read_bytes()
        self.assertEqual(json.loads(saved_bytes)["clusters"], original["clusters"])
        for cluster in original["clusters"]:
            self.assertEqual(k.members(self.vault, cluster["id"])["total"], len(records))
        self.assertEqual(k.run(self.vault, approved=True,
            pipeline=lambda _r: self.fail("Cleanup called the model"))["generation"], result["generation"])
        self.assertEqual(saved_path.read_bytes(), saved_bytes)

    def test_compaction_preserves_real_branches_even_when_their_labels_match(self):
        records = k.evidence(self.vault)
        result = fixture(records)
        parent = result["clusters"][0]
        parent["children"] = ["child-0", "child-1"]
        for index, record in enumerate(records):
            result["clusters"].append(parent | {"id": f"child-{index}", "parent_id": parent["id"],
                "children": [], "level": 1, "chat_ids": [record["id"]], "count": 1})
        k.validate(result, records)
        compact, aliases = k.compact_hierarchy(result["clusters"])
        self.assertEqual(compact, result["clusters"])
        self.assertEqual(aliases, {})
        k.validate(result | {"clusters": compact}, records)

    def test_whole_vault_roundtrip_read_only_source_staleness_and_snapshot(self):
        raw = self.vault.path("raw", "synthetic").read_bytes()
        notes = self.vault.personal_notes(self.doc["id"])
        records = k.evidence(self.vault)
        self.assertEqual([r["kind"] for r in records], ["annotation", "note"])
        self.assertEqual(records[0]["page_reaction"], "bad")
        self.assertIn("disagree", records[0]["comment"])
        with self.assertRaises(ValueError): k.run(self.vault, pipeline=fixture)
        result = k.run(self.vault, approved=True, pipeline=fixture)
        self.assertFalse(result["stale"])
        self.assertEqual(k.members(self.vault, "synthetic")["total"], 2)
        self.assertEqual(k.run(self.vault, approved=True, pipeline=lambda _r: self.fail("Unchanged input reran"))["generation"], result["generation"])
        self.assertEqual(self.vault.path("raw", "synthetic").read_bytes(), raw)
        self.assertEqual(self.vault.personal_notes(self.doc["id"]), notes)
        restored = restore_snapshot(self.vault.snapshot(), Path(self.temp.name) / "restored")
        self.assertEqual(k.state(restored)["generation"], result["generation"])
        self.vault.update(self.doc["id"], title="Updated synthetic title")
        self.assertTrue(k.state(self.vault)["stale"])
        with self.assertRaises(ValueError): k.members(self.vault, "synthetic")
        k.run(self.vault, approved=True, pipeline=fixture)
        self.assertEqual(len(list((self.vault.root / "knowledge").glob("kura-revision-*"))), 1)

    def test_missing_duplicate_and_cyclic_evidence_and_concurrent_edits_rejected(self):
        records = k.evidence(self.vault)
        for change in (lambda c: c["chat_ids"].pop(), lambda c: c["chat_ids"].append(c["chat_ids"][0]),
                       lambda c: c.update(parent_id="synthetic"), lambda c: c.update(x=float("nan"))):
            bad = fixture(records)
            change(bad["clusters"][0])
            with self.assertRaises(ValueError): k.validate(bad, records)
        before = k.run(self.vault, approved=True, pipeline=fixture)
        self.vault.update(self.doc["id"], title="Changed once")
        def race(records):
            self.vault.update(self.doc["id"], title="Changed twice")
            return fixture(records)
        with self.assertRaises(ValueError): k.run(self.vault, approved=True, pipeline=race)
        self.assertEqual(k.state(self.vault)["generation"], before["generation"])

    def test_empty_vault_and_account_boundary_and_pagination(self):
        other = Vault(Path(self.temp.name) / "other")
        other.initialize("other")
        self.assertEqual(k.evidence(other), [])
        result = k.run(other, approved=True, pipeline=lambda _r: self.fail("Empty vault called model"))
        self.assertEqual(result["clusters"], [])
        result = k.run(self.vault, approved=True, pipeline=fixture)
        a = k.members(self.vault, "synthetic", limit=1)
        b = k.members(self.vault, "synthetic", offset=1, limit=1)
        self.assertNotEqual(a["results"][0]["id"], b["results"][0]["id"])
        with self.assertRaises(ValueError): k.members(other, "synthetic")

    def test_authenticated_bridge_runs_kura_and_rejects_unapproved_context(self):
        server = make_server(self.vault, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(method, route, body=None, auth=True):
            conn = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Authorization": "Bearer " + pairing_key(self.vault)} if auth else {}
            if body is not None: headers["Content-Type"] = "application/json"
            conn.request(method, route, json.dumps(body) if body else None, headers)
            response = conn.getresponse()
            result = response.status, json.loads(response.read())
            conn.close()
            return result
        self.assertEqual(request("GET", "/api/kura", auth=False)[0], 401)
        self.assertEqual(request("POST", "/api/research", {"operation": "kura", "approved": "true"})[0], 400)
        original = k.run
        with patch.object(k, "run", side_effect=lambda *a, **kw: original(*a, **kw, pipeline=fixture)):
            status, _ = request("POST", "/api/research", {"operation": "kura", "approved": True})
            self.assertEqual(status, 202)
            for _ in range(100):
                job = request("GET", "/api/research")[1]["job"]
                if job["state"] in ("completed", "failed"): break
                time.sleep(.01)
            self.assertEqual(job["state"], "completed")
        payload = request("GET", "/api/kura")[1]
        self.assertNotIn("summaries", payload)
        self.assertEqual(payload["counts"], {"annotation": 1, "note": 1})
        self.assertEqual(request("GET", "/api/kura?cluster_id=synthetic")[1]["total"], 2)
        self.assertEqual(request("GET", "/api/kura?cluster_id=synthetic&offset=-1")[0], 400)


if __name__ == "__main__":
    unittest.main()
