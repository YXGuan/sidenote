"""Optional real-upstream integration checks; no private vault or model calls."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.kura_analysis import validate
from research_notes.kura_pipeline import chunks, pipeline, summarize


class ChunkTests(unittest.TestCase):
    def test_every_character_of_long_evidence_and_role_is_preserved(self):
        record = {"id": "annotation:long", "kind": "annotation", "title": "Synthetic", "highlight": "a" * 18001,
                  "comment": "disagree " * 2000, "text": "", "reaction": "dislike"}
        parts = chunks([record])
        self.assertEqual("".join(p["text"] for p in parts if p["field"] == "highlight"), record["highlight"])
        self.assertEqual("".join(p["text"] for p in parts if p["field"] == "comment"), record["comment"])
        self.assertTrue(all(p["reaction"] == "dislike" for p in parts))

    def test_incomplete_model_batches_split_and_cached_summaries_cover_every_record(self):
        records = [{"id": f"annotation:{i}", "kind": "annotation", "title": "Synthetic", "highlight": str(i)} for i in range(21)]
        sizes = []
        def runner(prompt, _schema, **_kwargs):
            data = json.loads(prompt.split("\nDATA:\n", 1)[1])
            sizes.append(len(data))
            self.assertTrue(all(item["id"].startswith("p") for item in data))
            self.assertTrue(all("record_id" not in item for item in data))
            chosen = data if len(data) <= 3 else data[:-1]
            return {"items": [{"id": item["id"], "summary": "Subject " + item["text"]} for item in chosen]}
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "cache.json"
            result = summarize(records, cache, lambda _p: None, runner)
            self.assertEqual(set(result), {r["id"] for r in records})
            self.assertEqual(result["annotation:20"], ["Subject 20"])
            self.assertIn(10, sizes)
            self.assertIn(3, sizes)
            self.assertEqual(summarize(records, cache, lambda _p: None,
                lambda *_a, **_kw: self.fail("Cached evidence called the model")), result)


@unittest.skipUnless(importlib.util.find_spec("sklearn"), "Optional isolated Kura dependencies not installed in this interpreter")
class PipelineTests(unittest.TestCase):
    def test_singleton_topics_pass_through_reduction_once_without_new_labels(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "upstream/kura"))
        from kura.cluster import KmeansClusteringModel
        import numpy as np

        class Encoder:
            def encode(self, texts, **_kwargs):
                return np.array([[i + 1, 1, i % 3] for i, _text in enumerate(texts)])

        labels = []
        singleton_ids = []
        original_cluster = KmeansClusteringModel.cluster

        def cluster(model, items):
            if not hasattr(items[0]["item"], "parent_id"):
                return original_cluster(model, items)
            singleton_ids.append(items[0]["item"].id)
            return {0: [items[0]["item"]], 1: [item["item"] for item in items[1:]]}

        def runner(prompt, schema, **_kwargs):
            data = json.loads(prompt.split("\nDATA:\n", 1)[1])
            if "items" in schema["properties"]:
                return {"items": [{"id": item["id"], "summary": "Synthetic " + item["text"]} for item in data]}
            labels.append(data)
            return {"name": f"Synthetic topic {len(labels)}", "description": "Invented subject grouping."}

        records = [{"id": f"annotation:{i}", "kind": "annotation", "title": "Synthetic", "highlight": str(i)} for i in range(64)]
        with tempfile.TemporaryDirectory() as temporary, patch.object(KmeansClusteringModel, "cluster", cluster):
            result = asyncio.run(pipeline(records, Path(temporary) / "cache.json", lambda _p: None,
                runner=runner, encoder=Encoder()))
        k_ids = [c["id"] for c in result["clusters"]]
        self.assertEqual(len(k_ids), len(set(k_ids)))
        self.assertEqual(len(singleton_ids), 1)
        self.assertEqual(k_ids.count(singleton_ids[0]), 1)
        self.assertEqual(sum(c["parent_id"] is None for c in result["clusters"]), 2)
        self.assertTrue(all(len(c["children"]) != 1 for c in result["clusters"]))
        k_roots = [c for c in result["clusters"] if c["parent_id"] is None]
        self.assertEqual(len(labels), len(result["clusters"]))
        self.assertIn(singleton_ids[0], [c["id"] for c in k_roots])
        validate(result, records)

    def test_real_kura_clustering_recursive_hierarchy_cache_and_tiny_libraries(self):
        import numpy as np
        import re
        class Encoder:
            def encode(self, texts, **_kwargs):
                return np.array([[float(re.search(r"\d+", text)[0]) / 160, 1, (i % 7) / 7] for i, text in enumerate(texts)])
        calls = []
        def runner(prompt, schema, **kwargs):
            data = json.loads(prompt.split("\nDATA:\n", 1)[1])
            calls.append(schema)
            if "items" in schema["properties"]:
                return {"items": [{"id": item["id"], "summary": "Synthetic subject " + item["text"]} for item in data]}
            return {"name": "Synthetic topic", "description": "A synthetic subject grouping."}
        with tempfile.TemporaryDirectory() as temporary:
            records = [{"id": f"annotation:{i}", "kind": "annotation", "title": "Synthetic", "highlight": str(i)} for i in range(160)]
            cache = Path(temporary) / "cache.json"
            result = asyncio.run(pipeline(records, cache, lambda _p: None, runner=runner, encoder=Encoder()))
            validate(result, records)
            self.assertGreater(max(c["level"] for c in result["clusters"]), 1)
            first = len([s for s in calls if "items" in s["properties"]])
            again = asyncio.run(pipeline(records, cache, lambda _p: None, runner=runner, encoder=Encoder()))
            self.assertEqual(len([s for s in calls if "items" in s["properties"]]), first)
            self.assertEqual({c["id"] for c in result["clusters"]}, {c["id"] for c in again["clusters"]})
            for size in (1, 2, 8):
                tiny = records[:size]
                validate(asyncio.run(pipeline(tiny, cache, lambda _p: None, runner=runner, encoder=Encoder())), tiny)


if __name__ == "__main__":
    unittest.main()
