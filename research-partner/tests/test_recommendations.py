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
from research_notes import recommendations as r
from research_notes.native import mirror_annotation
from research_notes.server import make_server, pairing_key
from research_notes.store import Vault


def pid(number):
    return f"{number:040x}"


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Vault(Path(self.temp.name) / "vault")
        self.vault.initialize("reader")
        self.vault.configure(auto_categorize=False)
        self.doc = self.liked("https://arxiv.org/abs/2401.12345v2", "A careful study of community networks")

    def liked(self, url, title, **metadata):
        doc = self.vault.capture(url, {"title": title, **metadata})
        mirror_annotation(self.vault, {"id": "comment-" + doc["id"], "uri": url,
            "created": "2026-10-24T00:00:00Z",
            "user": "acct:reader@hypothes.is", "text": "I love this excellent and helpful work! Private note marker.",
            "target": [{"selector": [{"type": "TextQuoteSelector", "exact": "Private source highlight marker"}]}]})
        return doc

    def transport(self, url, **kwargs):
        if "/paper/batch" in url:
            return [{"paperId": pid(1)} for _ in kwargs["data"]["ids"]]
        return {"recommendedPapers": [
            {"paperId": pid(1), "title": "Seed returned by the API"},
            {"paperId": pid(2), "title": "New paper on community structure", "year": 2026,
             "authors": [{"name": "Ada Reader"}], "externalIds": {"DOI": "10.1234/new"},
             "openAccessPdf": {"url": "javascript:alert(1)"}},
            {"paperId": pid(2), "title": "Duplicate recommendation"}]}

    def test_full_collection_deduplicates_resolved_seeds_and_never_sends_notes(self):
        self.liked("https://doi.org/10.1234/alias", "Another page for the same paper")
        self.liked("https://example.org/blog", "A wonderful recipe")
        negative = self.liked("https://arxiv.org/abs/2401.23456", "A paper I now dislike")
        self.vault.update(negative["id"], reaction="bad")
        self.vault.capture("https://arxiv.org/abs/2401.34567", {"title": "Highlight-only paper"})
        calls = []
        def get(url, **kwargs):
            calls.append((url, kwargs))
            return self.transport(url, **kwargs)
        result = r.refresh(self.vault, approved=True, get=get)
        self.assertEqual(result["eligible_count"], 2)
        self.assertEqual(result["used_seed_count"], 1)
        self.assertEqual(result["skipped_count"], 1)
        self.assertEqual(calls[0][1]["data"]["ids"], [r._identifier(s["identity"]) for s in r.inventory(self.vault)[1]])
        self.assertEqual(calls[-1][1]["data"], {"positivePaperIds": [pid(1)], "negativePaperIds": []})
        self.assertNotIn("Private", json.dumps(calls))
        self.assertEqual([p["paper_id"] for p in result["papers"]], [pid(2)])
        self.assertEqual(result["papers"][0]["pdf_url"], "")
        self.assertFalse(result["stale"])
        self.assertEqual((self.vault.root / r.CACHE).stat().st_mode & 0o777, 0o600)

    def test_no_network_on_get_or_empty_collection_and_strict_refresh_authorization(self):
        self.assertFalse(r.state(self.vault)["generated_at"])
        with self.assertRaises(ValueError):
            r.refresh(self.vault, approved="true", get=lambda *_a, **_k: self.fail("unauthorized network"))
        self.vault.update(self.doc["id"], reaction="bad")
        result = r.refresh(self.vault, approved=True, get=lambda *_a, **_k: self.fail("empty request"))
        self.assertEqual(result["papers"], [])
        self.assertEqual(result["used_seed_count"], 0)

    def test_unresolved_seeds_are_visible_and_not_guessed(self):
        calls = []
        def get(url, **kwargs):
            calls.append(url)
            return [None]
        result = r.refresh(self.vault, approved=True, get=get)
        self.assertEqual(result["unresolved_count"], 1)
        self.assertEqual(result["seeds"][0]["status"], "unresolved")
        self.assertEqual(len(calls), 1)

    def test_papers_without_identifiers_use_conservative_title_matching(self):
        self.vault.update(self.doc["id"], reaction="bad")
        self.liked("https://openreview.net/forum?id=demo", "A careful study of language model evaluation")
        def get(url, **kwargs):
            if "/paper/search" in url:
                return {"data": [{"paperId": pid(3), "title": "A careful study of language model evaluation"}]}
            self.assertEqual(kwargs["data"]["positivePaperIds"], [pid(3)])
            return {"recommendedPapers": []}
        self.assertEqual(r.refresh(self.vault, approved=True, get=get)["used_seed_count"], 1)

    def test_all_501_seeds_are_resolved_in_bounded_batches_without_truncation(self):
        docs = {str(i): {"id": str(i), "title": f"Paper {i}", "url": f"https://doi.org/10.1234/{i}",
                         "metadata": {}, "automatic_collections": ["liked-auto"]} for i in range(501)}
        batches = []
        def get(url, **kwargs):
            if "/paper/batch" in url:
                ids = kwargs["data"]["ids"]
                batches.append(len(ids))
                return [{"paperId": pid(int(identifier.split('/')[-1]) + 1)} for identifier in ids]
            self.assertEqual(len(kwargs["data"]["positivePaperIds"]), 501)
            return {"recommendedPapers": []}
        with patch.object(self.vault, "documents", return_value=docs):
            self.assertEqual(r.refresh(self.vault, approved=True, get=get)["used_seed_count"], 501)
        self.assertEqual(batches, [500, 1])

    def test_failed_or_malformed_refresh_preserves_cache_and_source_records(self):
        r.refresh(self.vault, approved=True, get=self.transport)
        before = (self.vault.root / r.CACHE).read_bytes()
        raw = self.vault.records("raw")
        for response in ({}, [None, None]):
            with self.assertRaises(ValueError):
                r.refresh(self.vault, approved=True, get=lambda *_a, **_k: response)
            self.assertEqual((self.vault.root / r.CACHE).read_bytes(), before)
        self.assertEqual(self.vault.records("raw"), raw)

    def test_changes_mark_stale_and_newly_saved_results_disappear_without_network(self):
        r.refresh(self.vault, approved=True, get=self.transport)
        self.vault.capture("https://doi.org/10.1234/new", {"title": "Now saved"})
        self.assertEqual(r.state(self.vault)["papers"], [])
        self.vault.update(self.doc["id"], reaction="bad")
        self.assertTrue(r.state(self.vault)["stale"])
        self.assertEqual(r.state(self.vault)["eligible_count"], 0)
        other = Vault(Path(self.temp.name) / "other")
        other.initialize("another-reader")
        self.assertEqual(r.state(other)["papers"], [])

    def test_concurrent_seed_edit_never_commits_obsolete_results(self):
        def get(url, **kwargs):
            if "/recommendations/" in url:
                self.vault.update(self.doc["id"], reaction="bad")
            return self.transport(url, **kwargs)
        with self.assertRaisesRegex(ValueError, "changed"):
            r.refresh(self.vault, approved=True, get=get)
        self.assertFalse((self.vault.root / r.CACHE).exists())

    def test_bridge_requires_pairing_and_starts_only_an_explicit_refresh(self):
        server = make_server(self.vault, port=0)
        self.addCleanup(server.server_close)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        def request(method, body=None, authenticated=True):
            connection = HTTPConnection("127.0.0.1", server.server_port)
            headers = {"Content-Type": "application/json"}
            if authenticated:
                headers["Authorization"] = "Bearer " + pairing_key(self.vault)
            connection.request(method, "/api/recommendations", json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            result = response.status, json.loads(response.read())
            connection.close()
            return result
        with patch.object(r, "refresh", return_value={}) as refresh:
            self.assertEqual(request("GET", authenticated=False)[0], 401)
            self.assertEqual(request("GET")[0], 200)
            self.assertFalse(refresh.called)
            self.assertEqual(request("POST", {})[0], 400)
            self.assertEqual(request("POST", {"approved": True})[0], 202)
            for _ in range(100):
                if request("GET")[1]["job"]["state"] == "completed":
                    break
                time.sleep(.01)
            refresh.assert_called_once_with(self.vault, approved=True)


if __name__ == "__main__":
    unittest.main()
