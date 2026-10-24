#!/usr/bin/env python3
"""Small synthetic sanity check, not a production-quality accuracy estimate.

The optional embedding experiment requires already-cached model weights. It never
opens a vault or downloads weights. Codex sends only the invented examples below.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.local_classifier import TOPICS, local_classify, link_type
from research_notes.organization import codex_classify, validate_batch

EXAMPLES = [
    ("Machine learning for computational social science", "https://arxiv.org/abs/2601.12345", "paper", {"computer science", "social science"}),
    ("Investing with index funds", "https://example.org/blog/investing", "blog", {"finance"}),
    ("Basketball tactics", "https://www.youtube.com/watch?v=synthetic", "video", {"sports"}),
    ("Clinical research on mental health", "https://pubmed.ncbi.nlm.nih.gov/12345/", "paper", {"health"}),
    ("Python API documentation", "https://docs.example.org/python", "documentation", {"technology"}),
    ("Climate physics and carbon emissions", "https://arxiv.org/abs/2601.54321", "paper", {"science"}),
    ("A new model", "https://example.org/item", "unknown", set()),
    ("A lifelong learning practice", "https://example.org/podcast/learning", "podcast", {"education"}),
]


def embeddings(pages, model_name):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise RuntimeError("Install sentence-transformers in a separate environment and cache its weights first") from None
    model = SentenceTransformer(model_name, local_files_only=True, trust_remote_code=False, device="cpu")
    names = list(TOPICS)
    descriptions = [name + ": " + ", ".join(TOPICS[name]) for name in names]
    category_vectors = model.encode(descriptions)
    document_vectors = model.encode([page["title"] for page in pages])
    scores = model.similarity(document_vectors, category_vectors)
    results = []
    for page, row in zip(pages, scores):
        # Experimental threshold: cosine similarity is not a calibrated confidence.
        topics = [name for name, score in zip(names, row) if float(score) >= 0.35][:8]
        kind = link_type(page)
        if kind == "paper" and "research" not in topics:
            topics.insert(0, "research")
        results.append({"document_id":page["document_id"],"tags":topics,"link_type":kind,"topics":topics,"subtopics":[]})
    return {"pages":results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("local", "codex", "sentence-transformers"), default="local")
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    args = parser.parse_args()
    pages = [{"document_id":str(i),"title":title,"url":url,"metadata":{},"page_notes":[],"personal_notes":""} for i,(title,url,_,_) in enumerate(EXAMPLES)]
    start = time.perf_counter()
    try:
        result = embeddings(pages,args.embedding_model) if args.provider == "sentence-transformers" else (codex_classify(pages,{}) if args.provider == "codex" else local_classify(pages))
        values = validate_batch(result, [page["document_id"] for page in pages])
    except (RuntimeError, OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    correct_types = tp = fp = fn = 0
    for i, (_, _, kind, expected) in enumerate(EXAMPLES):
        item = values[str(i)]["classification"]
        predicted = set(item["topics"])
        correct_types += item["link_type"] == kind
        tp += len(predicted & expected)
        fp += len(predicted - expected)
        fn += len(expected - predicted)
    print(json.dumps({"provider":args.provider,"dataset":"8 invented English examples; no user data", "examples":len(pages),"type_exact_match":correct_types / len(pages),"topic_micro_f1":2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0,"elapsed_seconds":round(time.perf_counter()-start,3),"limitations":"Smoke test only. Examples share vocabulary with the baseline rules; no quality or latency conclusion on real research follows."},indent=2))


if __name__ == "__main__":
    main()
