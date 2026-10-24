"""Cited concept pages and their NetworkX neighborhoods.

The vault remains authoritative. Model output is an untrusted proposed analysis;
only validated quotations and known concept endpoints enter a saved generation.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
from uuid import uuid4

from .intelligence import codex_json, codex_model
from .knowledge import POLICY, PATTERN, STR, STRINGS, corpus, digest, object_schema, question, slug, tokens
from .store import atomic_write, encoded, now, read_json

VERSION = 2
SECTIONS = {"overview": "Overview", "idea": "Key ideas", "disagreement": "Disagreements", "question": "Open questions"}


def identity(title):
    return " ".join(re.findall(r"\w+", title.casefold()))


def citations(claim):
    # Read old generations without rewriting or discarding them.
    return claim.get("evidence", [{"evidence_id": claim.get("evidence_id"), "quote": claim.get("quote", "")}])


def _valid(evidence, known):
    return bool(evidence) and all(isinstance(e, dict) and isinstance(e.get("evidence_id"), str) and e["evidence_id"] in known and
        isinstance(e.get("quote"), str) and bool(e["quote"].strip()) and
        e["quote"] in known[e["evidence_id"]]["text"] for e in evidence)


def _read(vault, records):
    state = read_json(vault.root / "knowledge/state.json", {})
    if not state:
        return {"pages": [], "stale": False, "pattern": PATTERN, "log": [], "evidence": records}
    # Legacy contradictions had only one citation. Keep their original data and
    # present them as ideas awaiting review, never as established disagreements.
    if state.get("schema_version", 1) < VERSION:
        for page in state["pages"]:
            page["claims"] = [dict(c, kind={"claim": "idea", "contradiction": "idea"}.get(c["kind"], c["kind"]),
                                    evidence=citations(c)) for c in page.get("claims", [])]
            page["needs_synthesis"] = bool(page["claims"])
    return state | {"stale": state.get("source_hash") != digest(records), "pattern": PATTERN, "evidence": records}


def wiki(vault):
    return _read(vault, corpus(vault))


def _pages(records):
    sources, topics = {}, {}
    for record in records:
        sources.setdefault(record["document_id"], []).append(record)
        for title in record["topics"] or ["Uncategorized"]:
            topics.setdefault(identity(title), {"title": title, "ids": set(), "aliases": set()})["ids"].add(record["id"])
            topics[identity(title)]["aliases"].add(title)
    pages = [{"id": "source-" + key, "title": items[0]["title"], "kind": "source", "aliases": [],
              "evidence_ids": [r["id"] for r in items], "claims": [], "relationships": [], "provider": "local"}
             for key, items in sources.items()]
    pages += [{"id": "topic-" + slug(item["title"]), "title": item["title"], "kind": "topic",
               "aliases": sorted(item["aliases"] - {item["title"]}), "evidence_ids": sorted(item["ids"]),
               "claims": [], "relationships": [], "provider": "local"} for item in topics.values()]
    return pages


def _fingerprint(ids, known):
    return digest([known[e] for e in sorted(ids)])


def _related(pages):
    for page in pages:
        ids = set(page["evidence_ids"])
        page["related"] = [p["id"] for p in pages if p["id"] != page["id"] and ids.intersection(p["evidence_ids"])]


def _markdown(page, known, pages):
    def escape(text):
        return re.sub(r"([\\`*_{}\[\]<>#])", r"\\\1", text)
    lines = ["# " + escape(page["title"]), "", "From saved reading; highlights do not imply agreement.", ""]
    for kind, heading in SECTIONS.items():
        lines += ["## " + heading, ""]
        claims = [c for c in page["claims"] if c["kind"] == kind]
        if not claims:
            lines += ["No cited synthesis yet." if kind in ("overview", "idea") else "None identified in the current synthesis.", ""]
        for claim in claims:
            lines += [escape(claim["text"]), ""]
            for ref in citations(claim):
                item = known[ref["evidence_id"]]
                lines += [f"[{escape(item['title'])}]({item['url']})", "", "> " + escape(ref["quote"]).replace("\n", "\n> "), ""]
    lines += ["## Saved evidence", ""]
    if page["kind"] != "source":
        # Topic exports link to complete source notebooks; do not duplicate the
        # entire corpus into every broad concept's Markdown/state payload.
        documents = {known[e]["document_id"]: known[e] for e in page["evidence_ids"]}
        lines += [f"- [{escape(item['title'])}](source-{key}.md)" for key, item in documents.items()]
    for eid in page["evidence_ids"]:
        if page["kind"] != "source":
            continue
        item = known[eid]
        lines += [f"### [{escape(item['title'])}]({item['url']})", ""]
        if item["kind"] == "annotations":
            lines += ["**Source highlight**", "", escape(item.get("highlight", "")), "", "**Reader comment**", "", escape(item.get("comment", "")), ""]
        else:
            lines += ["**Source metadata**", "", escape(item.get("source_text", item["text"])), "",
                      "**Personal note**", "", escape(item.get("personal_note", "")), ""]
    titles = {p["id"]: p["title"] for p in pages}
    lines += ["## Related pages (shared evidence)", ""]
    lines += [f"- [{escape(titles[i])}]({i}.md)" for i in page["related"]]
    return "\n".join(lines)


def _save(vault, pages, records, previous, action):
    known = {r["id"]: r for r in records}
    _related(pages)
    for page in pages:
        page["markdown"] = _markdown(page, known, pages)
    state = {"schema_version": VERSION, "generation": uuid4().hex, "source_hash": digest(records),
             "generated_at": now(), "pages": pages, "log": previous.get("log", []) + [{"at": now(), "action": action}]}
    if previous.get("generation"):
        # Keep the exact prior canonical generation, excluding response-only fields.
        prior = read_json(vault.root / "knowledge/state.json", {})
        atomic_write(vault.root / "knowledge" / ("revision-" + prior["generation"] + ".json"), encoded(prior))
    atomic_write(vault.root / "knowledge/state.json", encoded(state))
    export_wiki(vault, state)
    return state | {"stale": False, "pattern": PATTERN, "evidence": records}


def export_wiki(vault, state=None):
    state = state or wiki(vault)
    folder = vault.root / "wiki"
    folder.mkdir(parents=True, exist_ok=True)
    index = ["# Library wiki", "", "Derived concept pages. Personal writing stays in library/.", ""]
    for page in state["pages"]:
        atomic_write(folder / (page["id"] + ".md"), page["markdown"])
        index.append(f"- [{page['title']}]({page['id']}.md)")
    atomic_write(folder / "index.md", "\n".join(index) + "\n")
    atomic_write(folder / "log.md", "# Wiki change log\n\n" + "\n".join(f"## [{e['at']}] {e['action']}" for e in state.get("log", [])) + "\n")
    return str(folder)


def build_wiki(vault):
    with vault.lock():
        records = corpus(vault)
        previous = _read(vault, records)
        if previous.get("schema_version") == VERSION and not previous["stale"]:
            export_wiki(vault, previous)
            return previous
        pages, known = _pages(records), {r["id"]: r for r in records}
        old = {p["id"]: p for p in previous["pages"]}
        # Discovered concepts survive updates while any of their evidence remains.
        for prior in previous["pages"]:
            if prior["kind"] == "concept" and any(e in known for e in prior["evidence_ids"]):
                pages.append(dict(prior, evidence_ids=[e for e in prior["evidence_ids"] if e in known]))
        for page in pages:
            prior = old.get(page["id"], {})
            page["claims"] = [c for c in prior.get("claims", []) if _valid(citations(c), known)]
            page["relationships"] = [r for r in prior.get("relationships", []) if _valid(r["evidence"], known)]
            page["provider"] = prior.get("provider", "local")
            page["aliases"] = sorted(set(page.get("aliases", []) + prior.get("aliases", [])))
            current_hash = _fingerprint(page["evidence_ids"], known)
            page["needs_synthesis"] = bool(prior.get("claims")) and (prior.get("needs_synthesis", False) or prior.get("evidence_hash") != current_hash)
            for key in ("model", "coverage", "synthesized_at", "evidence_hash"):
                if key in prior:
                    page[key] = prior[key]
        ids = {p["id"] for p in pages}
        for page in pages:
            page["relationships"] = [r for r in page["relationships"] if r["source"] in ids and r["target"] in ids]
        return _save(vault, pages, records, previous, "ingest | refresh saved evidence and concepts")


REFERENCE = object_schema({"evidence_id": STR, "quote": STR})
REFERENCES = {"type": "array", "minItems": 1, "maxItems": 6, "items": REFERENCE}
CLAIM = object_schema({"kind": {"type": "string", "enum": list(SECTIONS)}, "text": STR, "evidence": REFERENCES})
CLAIMS = {"type": "array", "maxItems": 12, "items": CLAIM}
ANALYSIS_SCHEMA = object_schema({"claims": CLAIMS,
    "concepts": {"type": "array", "maxItems": 5, "items": object_schema({"title": STR, "aliases": STRINGS, "claims": CLAIMS})},
    "relationships": {"type": "array", "maxItems": 12, "items": object_schema({"source": STR, "target": STR,
        "relation": STR, "explanation": STR, "basis": {"type": "string", "enum": ["source-stated", "inferred"]}, "evidence": REFERENCES})}})


def _text(value, limit):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def _validate(result, known):
    if not isinstance(result, dict) or set(result) != {"claims", "concepts", "relationships"}:
        raise ValueError("The model did not return a complete concept analysis")
    if len(encoded(result)) > 100000:
        raise ValueError("The concept analysis is too long; retry with a more concise synthesis")
    def refs(evidence, disagreement=False):
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= 6 or not _valid(evidence, known):
            raise ValueError("Supporting quotes must exactly match saved evidence")
        if any(set(e) != {"evidence_id", "quote"} or not _text(e["quote"], 1500) for e in evidence):
            raise ValueError("Invalid supporting quote")
        if disagreement and len({known[e["evidence_id"]]["document_id"] for e in evidence}) < 2:
            raise ValueError("A disagreement requires evidence from at least two different sources")
    def claims(items):
        if not isinstance(items, list) or not 1 <= len(items) <= 12:
            raise ValueError("A concept needs 1–12 cited statements")
        if not any(c.get("kind") == "overview" for c in items if isinstance(c, dict)):
            raise ValueError("A concept needs a cited overview")
        for c in items:
            if not isinstance(c, dict) or set(c) != {"kind", "text", "evidence"} or c["kind"] not in SECTIONS or not _text(c["text"], 3000):
                raise ValueError("Invalid concept statement")
            refs(c["evidence"], c["kind"] == "disagreement")
    claims(result["claims"])
    if not isinstance(result["concepts"], list) or len(result["concepts"]) > 5:
        raise ValueError("Invalid discovered concepts")
    for concept in result["concepts"]:
        if not isinstance(concept, dict) or set(concept) != {"title", "aliases", "claims"} or not _text(concept["title"], 160):
            raise ValueError("Invalid discovered concept")
        if not identity(concept["title"]) or not isinstance(concept["aliases"], list) or len(concept["aliases"]) > 10 or any(not _text(a, 160) or not identity(a) for a in concept["aliases"]):
            raise ValueError("Invalid concept aliases")
        claims(concept["claims"])
    if not isinstance(result["relationships"], list) or len(result["relationships"]) > 12:
        raise ValueError("Invalid concept relationships")
    for rel in result["relationships"]:
        if not isinstance(rel, dict) or set(rel) != {"source", "target", "relation", "explanation", "basis", "evidence"} or any(not _text(rel[k], n) for k, n in (("source", 160), ("target", 160), ("relation", 80), ("explanation", 3000))) or rel["basis"] not in ("source-stated", "inferred"):
            raise ValueError("Invalid concept relationship")
        refs(rel["evidence"])


def _batches(records):
    # Process every record, including long personal notes, without truncating the
    # library to a model prompt. Later passes receive the previous cited synopsis.
    batch, size = [], 0
    for record in records:
        parts = [("highlight", record.get("highlight", "")), ("reader comment", record.get("comment", ""))] if record["kind"] == "annotations" else [
            ("source metadata", record.get("source_text", record["text"])), ("personal note", record.get("personal_note", ""))]
        for kind, text in parts:
            for start in range(0, len(text), 8000):
                item = {k: record[k] for k in ("id", "document_id", "title", "reaction")}
                item.update(part_kind=kind, text=text[start:start + 8000])
                length = len(encoded(item))
                if batch and size + length > 60000:
                    yield batch
                    batch, size = [], 0
                batch.append(item)
                size += length
    if batch:
        yield batch


def synthesize(vault, page_id, *, approved=False, runner=codex_json, progress=lambda _s: None):
    if approved is not True:
        raise ValueError("Choose Synthesize to send this concept's saved evidence to your signed-in model")
    state = wiki(vault)
    if state["stale"]:
        raise ValueError("Update the wiki before synthesizing changed sources")
    page = next((p for p in state["pages"] if p["id"] == page_id and p["kind"] != "source"), None)
    if not page:
        raise ValueError("Choose an existing topic or concept page")
    records = state["evidence"]
    selected = [r for r in records if r["id"] in page["evidence_ids"]]
    known = {r["id"]: r for r in selected}
    batches = list(_batches(selected))
    if not batches:
        raise ValueError("This concept has no saved text to synthesize")
    result = None
    for index, batch in enumerate(batches):
        progress({"stage": "Reading evidence and connecting ideas", "done": index, "total": len(batches)})
        result = runner(POLICY + "\nWrite readable concept wiki pages about the requested subject. Return a concise overview, key ideas, "
            "disagreements between different sources, and open questions anchored in the saved evidence. Use kind overview, idea, disagreement, question. "
            "Each statement needs 1–6 evidence references with evidence_id and an exact quote of at most 1500 characters. Each page needs an overview. "
            "Disagreements require quotes from at least two different documents and must explain the incompatible positions; do not manufacture disagreement. "
            "Discover up to five specific related concepts, with aliases and their own cited statements. Avoid duplicating the requested subject. "
            "Return up to twelve useful directed concept relationships with a short verb phrase, explanation, citations, and basis source-stated or inferred. "
            "Relationship endpoints must be the requested subject or titles/aliases of concepts in your response. Similarity alone is not causation or support. "
            "Distinguish source assertions, reader comments, personal notes, and explicit dislikes. Do not infer reader agreement. "
            "Do not browse or introduce outside facts. Prose is plain text, not Markdown. "
            "When a previous pass is supplied, integrate it with the new evidence, retaining its useful citations and disagreements. "
            "Previous analysis is derived, not independent evidence. Empty disagreement/question sections are allowed.\nDATA:\n" +
            json.dumps({"subject": page["title"], "evidence": batch, "previous_pass": result,
                        "pass": index + 1, "total_passes": len(batches)}, ensure_ascii=False), ANALYSIS_SCHEMA)
        _validate(result, known)
        # Resolve only within the proposed analysis before any generation writes.
        names = {identity(page["title"])} | {identity(a) for a in page.get("aliases", [])}
        for concept in result["concepts"]:
            names.update(identity(t) for t in [concept["title"]] + concept["aliases"])
        if any(identity(r["source"]) not in names or identity(r["target"]) not in names for r in result["relationships"]):
            raise ValueError("A relationship names an unknown concept")
    with vault.lock():
        current = read_json(vault.root / "knowledge/state.json", {})
        if digest(corpus(vault)) != state["source_hash"] or current.get("generation") != state["generation"]:
            raise ValueError("Sources or wiki changed during synthesis; update and retry")
        pages = deepcopy(state["pages"])
        root = next(p for p in pages if p["id"] == page_id)
        by_name = {}
        for p in sorted(pages, key=lambda p: p["id"] != page_id):
            if p["kind"] != "source":
                for title in [p["title"]] + p.get("aliases", []):
                    by_name.setdefault(identity(title), p)
        touched = [(root, result["claims"])]
        for concept in result["concepts"]:
            candidates = {by_name[identity(t)]["id"] for t in [concept["title"]] + concept["aliases"] if identity(t) in by_name}
            if len(candidates) > 1:
                raise ValueError("Concept aliases ambiguously name multiple existing pages")
            target = next((p for p in pages if p["id"] in candidates), None)
            if target is None:
                target = {"id": "concept-" + slug(concept["title"]), "kind": "concept", "title": concept["title"],
                          "aliases": [], "evidence_ids": [], "claims": [], "relationships": [], "provider": "local"}
                pages.append(target)
            target["aliases"] = sorted(set(target.get("aliases", []) + concept["aliases"] + [concept["title"]]) - {target["title"]})
            for title in [target["title"]] + target["aliases"]:
                by_name[identity(title)] = target
            if target["id"] == page_id or any(p["id"] == target["id"] for p, _ in touched):
                raise ValueError("The analysis returned duplicate concept pages")
            touched.append((target, concept["claims"]))
        coverage = {"records": len(selected), "sources": len({r["document_id"] for r in selected}), "passes": len(batches)}
        for target, claims in touched:
            evidence_ids = sorted({e["evidence_id"] for c in claims for e in c["evidence"]})
            # A pre-existing broad page may have more evidence than the current
            # analysis. Preserve it, and flag the narrower synthesis for review.
            target["evidence_ids"] = sorted(set(target["evidence_ids"]) | set(evidence_ids))
            partial = any(e not in known for e in target["evidence_ids"])
            target.update(claims=claims, provider="codex-exec", model=codex_model(), synthesized_at=now(),
                          needs_synthesis=partial, coverage=coverage,
                          evidence_hash=_fingerprint(target["evidence_ids"], {r["id"]: r for r in records}))
        relationships = []
        for rel in result["relationships"]:
            source, target = by_name[identity(rel["source"])]["id"], by_name[identity(rel["target"])]["id"]
            if source == target:
                raise ValueError("A relationship must connect two different concepts")
            key = slug(source + "|" + rel["relation"] + "|" + target)
            relationships.append(rel | {"id": "relation-" + key, "source": source, "target": target})
        root["relationships"] = relationships
        progress({"stage": "Concept pages ready", "done": len(batches), "total": len(batches)})
        return _save(vault, pages, records, current, "synthesis | " + page["title"])


def lint_wiki(vault):
    state = wiki(vault)
    known, ids = {r["id"]: r for r in state["evidence"]}, {p["id"] for p in state["pages"]}
    issues = [{"kind": "stale", "message": "Saved evidence changed; update the wiki."}] if state["stale"] else []
    for page in state["pages"]:
        if any(e not in known for e in page["evidence_ids"]):
            issues.append({"kind": "missing-evidence", "message": page["title"]})
        for claim in page.get("claims", []):
            if not _valid(citations(claim), known):
                issues.append({"kind": "changed-quote", "message": page["title"]})
        for rel in page.get("relationships", []):
            if rel["source"] not in ids or rel["target"] not in ids or not _valid(rel["evidence"], known):
                issues.append({"kind": "broken-relationship", "message": page["title"]})
        if any(i not in ids for i in page.get("related", [])):
            issues.append({"kind": "broken-link", "message": page["title"]})
    return {"issues": issues, "pages": len(state["pages"]), "stale": state["stale"]}


def graph(vault, *, query="", focus="", depth=1, limit=80, overview=False):
    import networkx as nx
    from rank_bm25 import BM25Plus
    if type(limit) is not int or not 10 <= limit <= 1000 or type(depth) is not int or not 1 <= depth <= 3:
        raise ValueError("Choose 1–3 connection steps and a graph limit of 10–1000")
    if not isinstance(focus, str) or len(focus) > 200 or type(overview) is not bool:
        raise ValueError("Invalid graph focus")
    records = corpus(vault)
    known = {r["id"]: r for r in records}
    state = _read(vault, records)
    network = nx.MultiDiGraph()
    topic_names = {identity(t): p for p in _pages(records) if p["kind"] == "topic" for t in [p["title"]] + p["aliases"]}
    def edge(source, target, relation, evidence, *, basis="metadata", explanation="", key=None):
        key = key or "metadata-" + slug(source + "|" + relation + "|" + target)
        # Repeated annotations contribute to the same metadata relationship.
        prior = network.get_edge_data(source, target, key, {})
        refs = {e["evidence_id"]: e for e in prior.get("evidence", []) + evidence}
        network.add_edge(source, target, key=key, id=key, relation=relation, basis=basis,
                         explanation=explanation, evidence=list(refs.values()))
    for item in records:
        sid = "source-" + item["document_id"]
        network.add_node(sid, label=item["title"], kind="source", url=item["source_url"], page_id=sid,
                         search_text=network.nodes.get(sid, {}).get("search_text", "") + " " + item["text"])
        ref = {"evidence_id": item["id"], "quote": ""}
        if item["kind"] == "annotations":
            aid = "annotation-" + item["id"]
            network.add_node(aid, label=item.get("highlight") or item.get("comment") or "Annotation", kind="annotation", url=item["url"], search_text=item["text"])
            edge(sid, aid, "contains highlight", [ref])
        for topic in item["topics"]:
            canonical = topic_names[identity(topic)]
            tid = canonical["id"]
            network.add_node(tid, label=canonical["title"], kind="topic", page_id=tid, search_text=" ".join([canonical["title"]] + canonical["aliases"]))
            edge(sid, tid, "filed under", [ref])
        for author in item["authors"]:
            aid = "author-" + slug(author)
            network.add_node(aid, label=author, kind="author", search_text=author)
            edge(aid, sid, "authored", [{"evidence_id": "source:" + item["document_id"], "quote": ""}])
    for page in state["pages"]:
        if page["kind"] == "source" or not any(e in known for e in page["evidence_ids"]):
            continue
        network.add_node(page["id"], label=page["title"], kind=page["kind"], page_id=page["id"],
                         aliases=page.get("aliases", []), search_text=" ".join([page["title"]] + page.get("aliases", [])))
        for eid in page["evidence_ids"]:
            if eid in known:
                source = "source-" + known[eid]["document_id"]
                if not network.has_edge(source, page["id"]):
                    edge(source, page["id"], "discusses", [{"evidence_id": eid, "quote": ""}])
        if state["stale"] or page.get("needs_synthesis"):
            continue
        for rel in page.get("relationships", []):
            if _valid(rel["evidence"], known):
                edge(rel["source"], rel["target"], rel["relation"], rel["evidence"], basis=rel["basis"], explanation=rel["explanation"], key=rel["id"])
    # All relation endpoints have validated pages; node additions may precede
    # their page in iteration, so rank only once construction is complete.
    all_nodes = list(network)
    matches = []
    if query:
        query = question(query)
        query_tokens = tokens(query)
        documents = [tokens(network.nodes[n].get("search_text", network.nodes[n]["label"])) for n in all_nodes]
        scores = BM25Plus(documents, delta=0).get_scores(query_tokens) if documents and any(documents) else []
        ranked = [(n, float(score) + (1000 if identity(query) in {identity(t) for t in [network.nodes[n]["label"]] + network.nodes[n].get("aliases", [])} else 0))
                  for n, score, document in zip(all_nodes, scores, documents) if set(query_tokens).intersection(document)]
        matches = [n for n, _s in sorted(ranked, key=lambda pair: (-pair[1], pair[0]))]
    semantic_degree = {n: sum(d["basis"] != "metadata" for *_ends, d in network.edges(n, data=True)) +
                          sum(d["basis"] != "metadata" for *_ends, d in network.in_edges(n, data=True)) for n in network}
    if focus and focus not in network:
        raise ValueError("This graph item is no longer available. Search for another concept or source.")
    if not focus and not overview:
        candidates = matches if query else sorted(network, key=lambda n: (
            -semantic_degree[n], network.nodes[n]["kind"] not in ("topic", "concept"), -network.degree(n), n))
        focus = candidates[0] if candidates else ""
    undirected = network.to_undirected()
    neighborhood = nx.ego_graph(undirected, focus, radius=depth) if focus else undirected if overview else undirected.subgraph([])
    # BFS truncation retains the selected item and a connecting path to each
    # visible node instead of dropping low-degree but essential evidence nodes.
    nodes = [focus] + [b for _a, b in nx.bfs_edges(neighborhood, focus)] if focus else sorted(neighborhood)
    visible = nodes[:limit]
    result = network.subgraph(visible)
    def node(n):
        return {k: v for k, v in network.nodes[n].items() if k != "search_text"} | {"id": n, "degree": network.degree(n)}
    edges = []
    for source, target, data in result.edges(data=True):
        edges.append(dict(data, source=source, target=target, evidence_id=data["evidence"][0]["evidence_id"],
            evidence=[ref | {k: known[ref["evidence_id"]].get(k, "") for k in ("title", "url", "highlight", "comment", "personal_note", "source_text", "reaction", "kind")}
                      for ref in data["evidence"] if ref["evidence_id"] in known]))
    return {"nodes": [node(n) for n in visible], "edges": edges, "focus": focus, "depth": depth,
            "matches": [node(n) for n in matches], "total_nodes": len(neighborhood), "library_nodes": len(network),
            "truncated": len(neighborhood) > limit, "stale": state["stale"],
            "notice": "Source-stated and inferred connections include saved passages. Quote matching does not verify logical support. Metadata links describe filing and authorship."}
