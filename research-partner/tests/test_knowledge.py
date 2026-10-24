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
from research_notes import knowledge as k
from research_notes.native import mirror_annotation
from research_notes.server import make_server, pairing_key
from research_notes.store import Vault, atomic_write, encoded, restore_snapshot


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.vault = Vault(Path(self.temp.name) / "vault")
        self.vault.initialize("reader")
        self.vault.configure(auto_categorize=False)
        self.doc = self.vault.capture("https://example.org/networks", {
            "title": "Online communities", "authors": ["Ada Reader"],
            "abstract": "Social network analysis studies ties between people."})
        self.vault.update(self.doc["id"], tags=["computational social science"], reaction="bad")
        self.annotation = {"id": "social-1", "uri": self.doc["url"], "user": "acct:reader@hypothes.is",
            "created": "2026-10-01T00:00:00Z", "text": "I disagree with this interpretation.",
            "target": [{"selector": [{"type": "TextQuoteSelector", "exact": "Network structure shapes information diffusion."}]}]}
        mirror_annotation(self.vault, self.annotation)
        self.vault.capture("https://example.org/cooking", {"title": "How to bake bread", "abstract": "Flour, yeast and water."})

    def test_natural_query_returns_actual_annotations_and_search_is_vault_scoped(self):
        result = k.search(self.vault, "give me all annotations related to computational social science", kind="annotations")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["results"][0]["id"], "social-1")
        self.assertIn("disagree", result["results"][0]["comment"])
        self.assertEqual(result["results"][0]["url"], "https://hypothes.is/a/social-1")
        self.assertEqual(k.search(self.vault, "diffusion")["results"][0]["document_id"], self.doc["id"])
        self.assertEqual(k.search(self.vault, "quantum gravity")["total"], 0)
        other = Vault(Path(self.temp.name) / "other")
        other.initialize("other")
        self.assertEqual(k.search(other, "social")["total"], 0)

    def test_expansion_sends_only_question_and_pagination_never_truncates_to_prompt_size(self):
        observed = []
        def runner(prompt, _schema):
            observed.append(prompt)
            return {"terms": ["social network analysis"]}
        result = k.search(self.vault, "how people connect", expand=True, runner=runner)
        self.assertEqual(result["total"], 1)
        self.assertNotIn("I disagree", observed[0])
        for i in range(55):
            item = self.annotation | {"id": f"annotation-{i}"}
            atomic_write(self.vault.path("raw", item["id"]), encoded(item))
        first = k.search(self.vault, "network", kind="annotations")
        second = k.search(self.vault, "network", kind="annotations", offset=50)
        self.assertEqual(first["total"], 56)
        self.assertEqual(len(first["results"]), 50)
        self.assertEqual(len(second["results"]), 6)
        self.assertFalse({r["id"] for r in first["results"]} & {r["id"] for r in second["results"]})
        with self.assertRaises(ValueError): k.search(self.vault, "social", terms=[{}])

    def test_ask_web_boundary_and_unknown_citations_are_rejected(self):
        observed = {}
        def runner(prompt, schema, **kwargs):
            observed.update(prompt=prompt, kwargs=kwargs)
            return {"answer": "Evidence says networks matter.", "library_ids": ["social-1"], "web_sources": []}
        result = k.ask(self.vault, "network structure", approved=True, runner=runner)
        self.assertTrue(observed["kwargs"]["web"])
        self.assertIn("I disagree", observed["prompt"])
        self.assertEqual(result["used_library"][0]["id"], "social-1")
        self.assertEqual(result["used_library"][0]["reaction"], "bad")
        k.ask(self.vault, "network structure", approved=True, web=False, runner=runner)
        self.assertFalse(observed["kwargs"]["web"])
        with self.assertRaises(ValueError): k.ask(self.vault, "social", approved="true", runner=runner)
        with self.assertRaises(ValueError):
            k.ask(self.vault, "social", approved=True, runner=lambda *_a, **_kw: {"answer": "bad", "library_ids": ["invented"], "web_sources": []})
        with self.assertRaises(ValueError):
            k.ask(self.vault, "social", web=False, approved=True, runner=lambda *_a, **_kw: {"answer": "bad", "library_ids": [], "web_sources": [{"title": "Web", "url": "https://example.org"}]})

    def topic(self):
        return next(p for p in k.build_wiki(self.vault)["pages"] if p["title"] == "computational social science")

    def claim(self):
        return {"kind": "overview", "text": "The source connects network structure and diffusion.",
                "evidence": [{"evidence_id": "social-1", "quote": "Network structure shapes information diffusion."}]}

    def analysis(self, claims=None):
        return {"claims": claims if claims is not None else [self.claim()], "concepts": [], "relationships": []}

    def connected_analysis(self):
        citation = self.claim()["evidence"]
        return self.analysis() | {"concepts": [
            {"title": "Network structure", "aliases": ["Network topology"], "claims": [self.claim()]},
            {"title": "Information diffusion", "aliases": [], "claims": [self.claim()]},
        ], "relationships": [
            {"source": "computational social science", "target": "Network topology", "relation": "studies",
             "explanation": "Network structure is a subject of the saved reading.", "basis": "inferred", "evidence": citation},
            {"source": "Network structure", "target": "Information diffusion", "relation": "shapes",
             "explanation": "The saved highlight connects structure to diffusion.", "basis": "source-stated", "evidence": citation},
        ]}

    def test_wiki_roundtrip_preserves_raw_notes_and_synthesis_and_exports_markdown(self):
        personal = self.vault.root / "library" / (self.doc["id"] + ".md")
        personal.write_text(personal.read_text() + "\nPrivate personal observation\n")
        raw = self.vault.path("raw", "social-1").read_bytes()
        topic = self.topic()
        before = k.wiki(self.vault)
        result = k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.analysis())
        compiled = next(p for p in result["pages"] if p["id"] == topic["id"])
        self.assertIn("## Overview", compiled["markdown"])
        self.assertEqual(self.vault.path("raw", "social-1").read_bytes(), raw)
        self.assertIn("Private personal observation", personal.read_text())
        self.assertEqual(self.vault.documents()[self.doc["id"]]["reaction"], "bad")
        self.assertEqual(k.lint_wiki(self.vault)["issues"], [])
        unchanged = k.build_wiki(self.vault)
        self.assertEqual(unchanged["generation"], result["generation"])
        self.assertTrue((self.vault.root / "wiki/index.md").exists())
        self.assertTrue((self.vault.root / "knowledge" / ("revision-" + before["generation"] + ".json")).exists())
        restored = restore_snapshot(self.vault.snapshot(), Path(self.temp.name) / "restored")
        self.assertEqual(k.wiki(restored)["pages"], result["pages"])
        k.export_wiki(restored)
        self.assertTrue((restored.root / "wiki" / (topic["id"] + ".md")).exists())

    def test_changed_evidence_marks_stale_and_removes_unverifiable_claims(self):
        topic = self.topic()
        k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.analysis())
        changed = self.annotation | {"target": [], "text": "A revised comment about networks."}
        mirror_annotation(self.vault, changed)
        self.assertTrue(k.wiki(self.vault)["stale"])
        self.assertTrue(k.lint_wiki(self.vault)["issues"])
        with self.assertRaises(ValueError): k.synthesize(self.vault, topic["id"], approved=True)
        rebuilt = k.build_wiki(self.vault)
        self.assertFalse(next(p for p in rebuilt["pages"] if p["id"] == topic["id"])["claims"])

    def test_bad_model_quote_and_concurrent_edits_do_not_commit(self):
        topic = self.topic()
        before = k.wiki(self.vault)["generation"]
        with self.assertRaises(ValueError):
            k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.analysis([self.claim() | {"evidence": [{"evidence_id": "social-1", "quote": "An invented quotation"}]}]))
        self.assertEqual(k.wiki(self.vault)["generation"], before)
        def race(*_a):
            self.vault.update(self.doc["id"], title="A changed title")
            return self.analysis()
        with self.assertRaises(ValueError): k.synthesize(self.vault, topic["id"], approved=True, runner=race)
        self.assertEqual(k.wiki(self.vault)["generation"], before)

    def test_current_wiki_synthesis_is_additional_ask_context(self):
        topic = self.topic()
        k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.analysis())
        observed = []
        def runner(prompt, *_a, **_kw):
            observed.append(prompt)
            return {"answer": "An answer", "library_ids": [], "web_sources": []}
        k.ask(self.vault, "network", approved=True, runner=runner)
        self.assertIn(self.claim()["text"], observed[0])
        self.vault.update(self.doc["id"], title="New title")
        k.ask(self.vault, "network", approved=True, runner=runner)
        self.assertNotIn(self.claim()["text"], observed[1])
        k.build_wiki(self.vault)
        k.ask(self.vault, "network", approved=True, runner=runner)
        self.assertNotIn(self.claim()["text"], observed[2])

    def test_networkx_graph_has_typed_traceable_edges_and_filters_neighbors(self):
        graph = k.graph(self.vault, query="computational social science")
        self.assertEqual({n["kind"] for n in graph["nodes"]}, {"source", "topic"})
        self.assertTrue(all(e["evidence_id"] for e in graph["edges"]))
        full = k.graph(self.vault, overview=True)
        self.assertIn("annotation", {n["kind"] for n in full["nodes"]})
        self.assertIn("author", {n["kind"] for n in full["nodes"]})

    def test_concepts_and_graph_share_citations_aliases_and_directed_connections(self):
        topic = self.topic()
        result = k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.connected_analysis())
        concept = next(p for p in result["pages"] if p["title"] == "Network structure")
        self.assertEqual(concept["kind"], "concept")
        self.assertEqual(concept["aliases"], ["Network topology"])
        graph = k.graph(self.vault, focus=concept["id"])
        self.assertEqual(graph["focus"], concept["id"])
        self.assertIn(topic["id"], {n["id"] for n in graph["nodes"]})
        edge = next(e for e in graph["edges"] if e["relation"] == "shapes")
        self.assertEqual(edge["source"], concept["id"])
        self.assertEqual(edge["basis"], "source-stated")
        self.assertEqual(edge["evidence"][0]["quote"], self.claim()["evidence"][0]["quote"])
        self.assertEqual(edge["evidence"][0]["comment"], self.annotation["text"])
        self.assertEqual(edge["evidence"][0]["reaction"], "bad")
        self.assertEqual(k.graph(self.vault, query="Network topology")["focus"], concept["id"])
        source = k.graph(self.vault, query="information diffusion")
        self.assertTrue(source["matches"])
        self.assertEqual(k.graph(self.vault, query="quantum gravity")["nodes"], [])
        generation = k.build_wiki(self.vault)["generation"]
        self.assertEqual(result["generation"], generation)
        again = k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.connected_analysis())
        self.assertEqual(sum(p["title"] == "Network structure" for p in again["pages"]), 1)

    def test_disagreements_require_two_distinct_sources_and_unknown_endpoints_never_commit(self):
        topic = self.topic()
        before = k.wiki(self.vault)["generation"]
        disagreement = self.claim() | {"kind": "disagreement"}
        with self.assertRaisesRegex(ValueError, "two different sources"):
            k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.analysis([self.claim(), disagreement]))
        analysis = self.connected_analysis()
        analysis["relationships"][0]["target"] = "Invented endpoint"
        with self.assertRaisesRegex(ValueError, "unknown concept"):
            k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: analysis)
        self.assertEqual(k.wiki(self.vault)["generation"], before)
        second = self.vault.capture("https://example.org/critique", {"title": "A different explanation", "abstract": "Homophily may explain apparent contagion."})
        self.vault.update(second["id"], tags=[topic["title"]])
        k.build_wiki(self.vault)
        disagreement["evidence"] = disagreement["evidence"] + [{"evidence_id": "source:" + second["id"], "quote": "Homophily may explain apparent contagion."}]
        result = k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.analysis([self.claim(), disagreement]))
        self.assertEqual(len(next(p for p in result["pages"] if p["id"] == topic["id"])["claims"][1]["evidence"]), 2)

    def test_unrelated_updates_preserve_current_synthesis_but_changed_evidence_hides_graph_relations(self):
        topic = self.topic()
        k.synthesize(self.vault, topic["id"], approved=True, runner=lambda *_a: self.connected_analysis())
        self.vault.capture("https://example.org/unrelated", {"title": "An unrelated topic"})
        rebuilt = k.build_wiki(self.vault)
        page = next(p for p in rebuilt["pages"] if p["id"] == topic["id"])
        self.assertFalse(page["needs_synthesis"])
        self.assertTrue(any(e["basis"] != "metadata" for e in k.graph(self.vault, focus=topic["id"])["edges"]))
        mirror_annotation(self.vault, self.annotation | {"text": "A revised interpretation."})
        self.assertFalse(any(e["basis"] != "metadata" for e in k.graph(self.vault, focus=topic["id"])["edges"]))
        rebuilt = k.build_wiki(self.vault)
        self.assertTrue(next(p for p in rebuilt["pages"] if p["id"] == topic["id"])["needs_synthesis"])
        self.assertFalse(any(e["basis"] != "metadata" for e in k.graph(self.vault, focus=topic["id"])["edges"]))

    def test_large_topics_process_all_text_in_cited_passes(self):
        topic = self.topic()
        long_text = "A long saved passage about networks. " * 6000
        personal = self.vault.root / "library" / (self.doc["id"] + ".md")
        personal.write_text(personal.read_text() + "\n" + long_text)
        k.build_wiki(self.vault)
        observed = []
        def runner(prompt, _schema):
            observed.append(json.loads(prompt.split("\nDATA:\n")[1]))
            return self.analysis()
        result = k.synthesize(self.vault, topic["id"], approved=True, runner=runner)
        self.assertGreater(len(observed), 1)
        supplied = "".join(part["text"] for batch in observed for part in batch["evidence"])
        self.assertIn(long_text, supplied)
        self.assertIsNotNone(observed[1]["previous_pass"])
        page = next(p for p in result["pages"] if p["id"] == topic["id"])
        self.assertEqual(page["coverage"]["passes"], len(observed))

    def test_legacy_generation_is_preserved_and_single_quote_contradictions_need_review(self):
        topic = self.topic()
        path = self.vault.root / "knowledge/state.json"
        state = json.loads(path.read_text())
        state["schema_version"] = 1
        prior = next(p for p in state["pages"] if p["id"] == topic["id"])
        prior["claims"] = [{"kind": "contradiction", "text": "Legacy interpretation", **self.claim()["evidence"][0]}]
        atomic_write(path, encoded(state))
        read = next(p for p in k.wiki(self.vault)["pages"] if p["id"] == topic["id"])
        self.assertEqual(read["claims"][0]["kind"], "idea")
        self.assertTrue(read["needs_synthesis"])
        upgraded = k.build_wiki(self.vault)
        self.assertEqual(upgraded["schema_version"], 2)
        self.assertEqual(json.loads((path.parent / ("revision-" + state["generation"] + ".json")).read_text()), state)

    def test_graph_expansion_keeps_selected_item_and_validates_controls(self):
        topic = self.topic()
        first = k.graph(self.vault, focus=topic["id"])
        second = k.graph(self.vault, focus=topic["id"], depth=2)
        self.assertGreater(len(second["nodes"]), len(first["nodes"]))
        self.assertIn(topic["id"], {n["id"] for n in second["nodes"]})
        with self.assertRaises(ValueError): k.graph(self.vault, focus="missing")
        with self.assertRaises(ValueError): k.graph(self.vault, depth=4)
        with self.assertRaises(ValueError): k.graph(self.vault, limit=True)

    def test_bridge_research_requires_pairing_and_runs_background_jobs(self):
        server = make_server(self.vault, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        def request(method, route, body=None, auth=True):
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            headers = {"Authorization": "Bearer " + pairing_key(self.vault)} if auth else {}
            if body is not None: headers["Content-Type"] = "application/json"
            connection.request(method, route, json.dumps(body) if body is not None else None, headers)
            response = connection.getresponse()
            status, data = response.status, json.loads(response.read())
            connection.close()
            return status, data
        self.assertEqual(request("GET", "/api/wiki", auth=False)[0], 401)
        self.assertEqual(request("POST", "/api/research", {"operation": "ask", "query": "social", "approved": "true"})[0], 400)
        self.assertEqual(request("GET", "/api/research")[1]["job"]["state"], "idle")
        status, payload = request("POST", "/api/research", {"operation": "find", "query": "social", "expand": False})
        self.assertEqual(status, 202)
        for _ in range(100):
            job = request("GET", "/api/research")[1]["job"]
            if job["state"] not in ("queued", "running"): break
            time.sleep(.01)
        self.assertEqual(job["id"], payload["job"]["id"])
        self.assertEqual(job["state"], "completed")
        self.assertEqual(job["result"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
