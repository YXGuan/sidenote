#!/usr/bin/env python3
"""Experiment on invented sources in a new temporary vault. --model opts into synthesis."""
import argparse
import difflib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes import knowledge
from research_notes.native import mirror_annotation
from research_notes.store import Vault, atomic_write, encoded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", action="store_true", help="Send only invented demonstration sources to the signed-in model")
    args = parser.parse_args()
    folder = args.output or Path(tempfile.mkdtemp(prefix="hypothesis-wiki-demo-"))
    if (folder / "vault").exists():
        raise SystemExit("Choose a new output directory; an existing demo vault is never replaced.")
    vault = Vault(folder / "vault")
    vault.initialize("demo-reader")
    vault.configure(auto_categorize=False)
    samples = [
        ("networks", "Network structure and diffusion", "Network structure shapes information diffusion.", "computational social science"),
        ("agents", "Simulating online communities", "Agent-based simulations can model interactions between people.", "computational social science"),
        ("bread", "Bread baking", "Yeast helps bread dough rise.", "cooking"),
    ]
    for name, title, passage, topic in samples:
        url = "https://example.org/demo/" + name
        doc = vault.capture(url, {"title": title, "authors": ["Demonstration Author"], "abstract": passage})
        vault.update(doc["id"], tags=[topic])
        mirror_annotation(vault, {"id": "demo-" + name, "uri": url, "user": "acct:demo-reader@hypothes.is",
            "created": "2026-10-01T00:00:00Z", "text": "How does this connect to the other sources?",
            "target": [{"selector": [{"type": "TextQuoteSelector", "exact": passage}]}]})
    first = knowledge.build_wiki(vault)
    topic = next(p for p in first["pages"] if p["title"] == "computational social science")
    before = topic["markdown"]
    query = "give me all annotations related to computational social science"
    search = knowledge.search(vault, query, kind="annotations")
    literal = [r["id"] for r in knowledge.corpus(vault) if query.casefold() in r["text"].casefold()]
    if args.model:
        first = knowledge.synthesize(vault, topic["id"], approved=True)
        before = next(p for p in first["pages"] if p["id"] == topic["id"])["markdown"]
    mirror_annotation(vault, {"id": "demo-caution", "uri": "https://example.org/demo/networks", "user": "acct:demo-reader@hypothes.is",
        "created": "2026-10-02T00:00:00Z", "text": "I disagree with treating network position as the only explanation.",
        "target": [{"selector": [{"type": "TextQuoteSelector", "exact": "Individual preferences also affect diffusion."}]}]})
    stale = knowledge.lint_wiki(vault)
    updated = knowledge.build_wiki(vault)
    if args.model:
        updated = knowledge.synthesize(vault, topic["id"], approved=True)
    after = next(p for p in updated["pages"] if p["id"] == topic["id"])["markdown"]
    report = {"data": "Invented demonstration sources only; illustrative URLs are not fetched.",
              "model_called": args.model, "query": query, "literal_query_matches": literal,
              "bm25_annotation_matches": [r["id"] for r in search["results"]],
              "wiki_pages": len(updated["pages"]), "issues_before_update": stale,
              "issues_after_update": knowledge.lint_wiki(vault), "graph": knowledge.graph(vault)}
    atomic_write(folder / "report.json", encoded(report))
    atomic_write(folder / "topic-before.md", before)
    atomic_write(folder / "topic-after.md", after)
    atomic_write(folder / "topic-changes.diff", "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="before", tofile="after")))
    print(json.dumps({"output": str(folder), "literal_matches": len(literal), "bm25_matches": search["total"],
                      "wiki_pages": len(updated["pages"]), "model_called": args.model}, indent=2))


if __name__ == "__main__":
    main()
