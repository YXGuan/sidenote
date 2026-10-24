#!/usr/bin/env python3
"""Exercise Research in the built extension, with synthetic vault/model fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "research-partner"))
from research_notes import knowledge, kura_analysis, recommendations
from research_notes.native import mirror_annotation
from research_notes.server import make_server, pairing_key
from research_notes.store import Vault


def main():
    with tempfile.TemporaryDirectory(prefix="research-extension-test-") as temporary:
        vault = Vault(Path(temporary) / "vault")
        vault.initialize("demo-reader")
        vault.configure(auto_categorize=False)
        for name, title, text, topic in [
            ("networks", "Online communities", "Network structure shapes information diffusion.", "computational social science"),
            ("agents", "Agent-based simulations", "Simulations can model social interaction.", "computational social science"),
            ("bread", "Bread baking", "Yeast helps dough rise.", "cooking"),
        ]:
            url = "https://example.org/demo/" + name
            doc = vault.capture(url, {"title": title, "authors": ["Demo Author"], "abstract": text})
            if name == "networks":
                vault.update(doc["id"], metadata={"doi": "10.1234/synthetic-networks"})
            vault.update(doc["id"], tags=[topic])
            mirror_annotation(vault, {"id": "demo-" + name, "uri": url, "user": "acct:demo-reader@hypothes.is",
                "created": "2026-10-01T00:00:00Z", "text": "An invented reader comment." + (" I love this excellent and useful paper!" if name == "networks" else ""),
                "target": [{"selector": [{"type": "TextQuoteSelector", "exact": text}]}]})
            if name == "networks":
                note = vault.root / "library" / (doc["id"] + ".md")
                note.write_text(note.read_text() + "\nSynthetic personal note about networks.\n")
        original_kura = kura_analysis.run
        original_kura_state = kura_analysis.state
        def kura_fixture(records):
            ids = [r["id"] for r in records]
            leaves = [{"id": f"leaf-{i}", "name": f"Synthetic subject {i + 1}", "description": "Synthetic cluster fixture.",
                "parent_id": "family", "children": [], "root_id": "family", "level": 1,
                "chat_ids": [key], "count": 1, "x": i * .2, "y": (i % 2) * .4} for i, key in enumerate(ids)]
            root = {"id": "family", "name": "Synthetic research family", "description": "Synthetic model fixture, not real analysis.",
                "parent_id": None, "children": [c["id"] for c in leaves], "root_id": "family", "level": 0,
                "chat_ids": ids, "count": len(ids), "x": .3, "y": .2}
            # Reproduce a legacy repeated chain beneath a real branching family.
            wrappers = [leaves[0] | {"id": f"repeated-{i}", "parent_id": "family" if i == 0 else f"repeated-{i - 1}",
                "children": [f"repeated-{i + 1}" if i < 2 else leaves[0]["id"]], "level": i + 1} for i in range(3)]
            root["children"][0] = "repeated-0"
            leaves[0].update(parent_id="repeated-2", level=4)
            return {"clusters": [root] + wrappers + leaves, "summaries": {key: "Synthetic evidence summary." for key in ids}}
        original_ask, original_synthesize = knowledge.ask, knowledge.synthesize
        original_recommendations = recommendations.refresh
        recommendation_calls = []
        def recommendation_api(url, **kwargs):
            recommendation_calls.append(kwargs.get("data"))
            if "/paper/batch" in url:
                return [{"paperId": f"{1:040x}"}]
            assert kwargs["data"] == {"positivePaperIds": [f"{1:040x}"], "negativePaperIds": []}
            return {"recommendedPapers": [{"paperId": f"{i + 2:040x}",
                "title": f"Synthetic recommendation {i + 1}: community networks",
                "authors": [{"name": "Demo Researcher"}], "year": 2026 - i % 5,
                "abstract": "Invented recommendation fixture. No scholarly API was called.",
                "citationCount": i * 3} for i in range(45)]}
        observed = []
        def model(prompt, schema, **kwargs):
            observed.append(kwargs)
            if "answer" in schema["properties"]:
                return {"answer": "Synthetic model fixture: networks connect people. [Evidence](https://hypothes.is/a/demo-networks)",
                        "library_ids": ["demo-networks"], "web_sources": []}
            citation = [{"evidence_id": "demo-networks", "quote": "Network structure shapes information diffusion."}]
            claim = {"kind": "overview", "text": "Synthetic synthesis fixture: network structure affects diffusion.", "evidence": citation}
            return {"claims": [claim, {"kind": "question", "text": "Synthetic question: when does structure matter?", "evidence": citation}],
                    "concepts": [{"title": "Information diffusion", "aliases": ["Information spread"], "claims": [claim]}],
                    "relationships": [{"source": "computational social science", "target": "Information diffusion", "relation": "studies",
                        "explanation": "Synthetic connection fixture: the saved reading discusses diffusion.", "basis": "inferred", "evidence": citation}]}
        with patch.object(knowledge, "ask", side_effect=lambda *a, **kw: original_ask(*a, **kw, runner=model)), \
             patch.object(knowledge, "synthesize", side_effect=lambda *a, **kw: original_synthesize(*a, **kw, runner=model)), \
             patch.object(recommendations, "refresh", side_effect=lambda *a, **kw: original_recommendations(*a, **kw, get=recommendation_api)), \
             patch.object(kura_analysis, "run", side_effect=lambda *a, **kw: original_kura(*a, **kw, pipeline=kura_fixture)), \
             patch.object(kura_analysis, "state", side_effect=lambda *a, **kw: original_kura_state(*a, **kw) | {"runtime_ready": True}):
            server = make_server(vault, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            config = Path(temporary) / "config.json"
            config.write_text(json.dumps({"port": server.server_port, "key": pairing_key(vault)}))
            try:
                result = subprocess.run(["node", str(ROOT / "test-research.mjs"), str(config)], cwd=ROOT, timeout=120)
                if result.returncode == 0:
                    assert any(call.get("web") is True for call in observed), "Answer path must permit web research"
                    assert len(recommendation_calls) == 2, "Opening or reloading Recommendations must not query the provider"
                    assert "invented reader comment" not in json.dumps(recommendation_calls)
                    assert "personal note" not in json.dumps(recommendation_calls)
                return result.returncode
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
