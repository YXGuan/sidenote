"""Whole-vault Kura runs. Raw evidence and reader edits are always read-only."""
from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4

from .store import atomic_write, encoded, now, quote_text, read_json

ROOT = Path(__file__).resolve().parents[1]
PIN = "956d95ac6a19c841c59eefe692f3341dfc2ba410"
EMBEDDING = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
VERSION = 1


def evidence(vault):
    records = []
    for doc in sorted(vault.documents().values(), key=lambda d: d["id"]):
        base = {"document_id": doc["id"], "title": doc["title"], "source_url": doc["url"],
                "page_reaction": doc["reaction"]}
        for annotation in sorted(doc["annotations"], key=lambda a: a["id"]):
            # Include even empty/tag-only annotations: no hidden sample or truncation.
            highlight, comment = quote_text(annotation), annotation.get("text", "")
            records.append(base | {"id": "annotation:" + annotation["id"], "kind": "annotation",
                "url": "https://hypothes.is/a/" + annotation["id"], "highlight": highlight,
                "comment": comment, "text": "", "tags": annotation.get("tags", []),
                "created": annotation.get("created", ""), "updated": annotation.get("updated", ""),
                "reaction": doc.get("annotation_states", {}).get(annotation["id"], {}).get("reaction")})
        personal = vault.personal_notes(doc["id"])
        if personal.strip():
            records.append(base | {"id": "note:" + doc["id"], "kind": "note", "url": doc["url"],
                "highlight": "", "comment": "", "text": personal, "tags": doc["tags"],
                "created": doc["created_at"], "updated": "", "reaction": None})
    return records


def fingerprint(records):
    return hashlib.sha256(encoded(records)).hexdigest()


def compact_hierarchy(clusters):
    """Remove single-child wrappers without changing evidence or saved records.

    Keep the most specific topic, and alias removed IDs so existing links work.
    Equal labels alone are not duplicates: separate subjects can share a name.
    """
    by_id = {c["id"]: c for c in clusters}
    children = {key: [] for key in by_id}
    for cluster in clusters:
        if cluster["parent_id"] in children:
            children[cluster["parent_id"]].append(cluster)
    aliases = {}
    for key, group in children.items():
        if len(group) == 1 and set(by_id[key]["chat_ids"]) == set(group[0]["chat_ids"]):
            aliases[key] = group[0]["id"]
    for key in aliases:
        target, visited = aliases[key], {key}
        while target in aliases:
            if target in visited:
                raise ValueError("Kura returned an invalid hierarchy")
            visited.add(target)
            target = aliases[target]
        aliases[key] = target
    result = []
    for cluster in clusters:
        if cluster["id"] in aliases:
            continue
        parent = cluster["parent_id"]
        while parent in aliases:
            parent = by_id[parent]["parent_id"]
        result.append(cluster | {"parent_id": parent, "children": []})
    retained = {c["id"]: c for c in result}
    for cluster in result:
        if cluster["parent_id"]:
            retained[cluster["parent_id"]]["children"].append(cluster["id"])
        level, ancestor = 0, cluster
        while ancestor["parent_id"]:
            level += 1
            ancestor = retained[ancestor["parent_id"]]
        cluster.update(level=level, root_id=ancestor["id"])
    return result, aliases


def state(vault):
    saved = read_json(vault.root / "knowledge/kura.json", {})
    if saved:
        clusters, aliases = compact_hierarchy(saved.get("clusters", []))
        saved = saved | {"clusters": clusters, "cluster_aliases": aliases}
    records = evidence(vault)
    counts = {kind: sum(r["kind"] == kind for r in records) for kind in ("annotation", "note")}
    return saved | {"available": bool(saved), "stale": bool(saved) and saved.get("source_hash") != fingerprint(records),
        "current_counts": counts, "runtime_ready": (ROOT / ".local-tools/kura/bin/python").exists()}


def members(vault, cluster_id, *, offset=0, limit=30):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Invalid Kura evidence page")
    saved = read_json(vault.root / "knowledge/kura.json", {})
    cluster = next((c for c in saved.get("clusters", []) if c["id"] == cluster_id), None)
    if cluster is None:
        raise ValueError("Kura cluster not found")
    records = evidence(vault)
    if saved.get("source_hash") != fingerprint(records):
        raise ValueError("Your notes have changed. Update Kura before browsing its evidence.")
    by_id = {r["id"]: r for r in records}
    ids = cluster["chat_ids"]
    summaries = saved.get("summaries", {})
    return {"total": len(ids), "offset": offset, "limit": limit,
        "results": [by_id[key] | {"summary": summaries.get(key, "")} for key in ids[offset:offset + limit]]}


def validate(result, records):
    """Reject lost, duplicated, cyclic, or invented evidence before committing."""
    known = {r["id"] for r in records}
    clusters = result.get("clusters") if isinstance(result, dict) else None
    if not isinstance(clusters, list) or (known and not clusters):
        raise ValueError("Kura returned no clusters")
    by_id = {c["id"]: c for c in clusters}
    if len(by_id) != len(clusters):
        raise ValueError("Kura returned duplicate clusters")
    leaves = []
    parent_ids = {c["parent_id"] for c in clusters if c["parent_id"]}
    import math
    for cluster in clusters:
        ids = cluster.get("chat_ids", [])
        if not isinstance(ids, list) or len(set(ids)) != len(ids) or not set(ids) <= known:
            raise ValueError("Kura returned invalid evidence IDs")
        if not ids or cluster.get("count") != len(ids):
            raise ValueError("Kura returned an invalid cluster count")
        if any(type(cluster.get(k)) not in (int, float) or not math.isfinite(cluster[k]) for k in ("x", "y")):
            raise ValueError("Kura returned invalid map positions")
        for key in ("name", "description"):
            if not isinstance(cluster.get(key), str) or not cluster[key].strip() or len(cluster[key]) > 3000:
                raise ValueError("Kura returned an invalid cluster label")
        visited, current = set(), cluster
        while current["parent_id"]:
            if current["id"] in visited or current["parent_id"] not in by_id:
                raise ValueError("Kura returned an invalid hierarchy")
            visited.add(current["id"])
            parent = by_id[current["parent_id"]]
            if not set(current["chat_ids"]) <= set(parent["chat_ids"]):
                raise ValueError("Kura hierarchy lost evidence")
            current = parent
        expected_children = sorted(c["id"] for c in clusters if c["parent_id"] == cluster["id"])
        if (sorted(cluster.get("children", [])) != expected_children or cluster.get("root_id") != current["id"]
                or cluster.get("level") != len(visited)):
            raise ValueError("Kura returned inconsistent hierarchy metadata")
        if cluster["id"] not in parent_ids:
            leaves.extend(ids)
        else:
            children = [c for c in clusters if c["parent_id"] == cluster["id"]]
            child_ids = [i for c in children for i in c["chat_ids"]]
            if len(set(child_ids)) != len(child_ids) or set(child_ids) != set(ids):
                raise ValueError("Kura parent membership differs from its children")
    if set(leaves) != known or len(leaves) != len(known):
        raise ValueError("Kura did not cover every annotation and note exactly once")
    if set(result.get("summaries", {})) != known:
        raise ValueError("Kura did not summarize every annotation and note")
    if any(not isinstance(text, str) or not text.strip() for text in result["summaries"].values()):
        raise ValueError("Kura returned an invalid evidence summary")
    return result


def run(vault, *, approved=False, progress=lambda _p: None, pipeline=None):
    if approved is not True:
        raise ValueError("Authorize sending all annotations and personal notes to your signed-in model to run Kura")
    lock_path = vault.root / ".local/kura-run.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another Kura run is already in progress") from None
        records = evidence(vault)
        source_hash = fingerprint(records)
        previous = read_json(vault.root / "knowledge/kura.json", {})
        from .intelligence import codex_model
        if (previous.get("source_hash") == source_hash and previous.get("version") == VERSION
                and previous.get("model") == codex_model()):
            return state(vault)
        if not records:
            result = {"clusters": [], "summaries": {}}
        elif pipeline:
            result = pipeline(records)
        else:
            runtime = ROOT / ".local-tools/kura/bin/python"
            checkout = ROOT / "upstream/kura"
            if not runtime.exists() or not checkout.exists():
                raise RuntimeError("Install the optional Kura runtime with ./research-partner/setup-kura")
            head = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
            if head != PIN:
                raise RuntimeError("Kura revision differs from the pinned runtime; run ./research-partner/setup-kura")
            with tempfile.TemporaryDirectory(prefix="kura-", dir=vault.root / ".local") as temporary:
                directory = Path(temporary)
                atomic_write(directory / "input.json", encoded(records))
                env = {k: v for k, v in os.environ.items() if k not in
                       ("HYPOTHESIS_TOKEN", "NOTES_BRIDGE_TOKEN", "S2_API_KEY", "OPENALEX_API_KEY", "OPENAI_API_KEY")}
                env["PYTHONPATH"] = str(ROOT)
                process = subprocess.Popen([str(runtime), "-m", "research_notes.kura_pipeline", str(directory),
                    str(vault.root / "knowledge/kura-cache.json")], env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                try:
                    while process.poll() is None:
                        progress(read_json(directory / "progress.json", {"stage": "Starting Kura"}))
                        time.sleep(0.5)
                    output = read_json(directory / "output.json", {})
                    if process.returncode or "error" in output:
                        raise RuntimeError(output.get("error", "Kura failed; check its runtime and model login. Previous results are intact."))
                    result = output
                finally:
                    if process.poll() is None:
                        import signal
                        os.killpg(process.pid, signal.SIGTERM)
                        process.wait()
        validate(result, records)
        saved = result | {"version": VERSION, "generation": uuid4().hex, "source_hash": source_hash,
            "generated_at": now(), "upstream": "https://github.com/jxnl/kura", "upstream_commit": PIN,
            "model": codex_model(),
            "embedding": EMBEDDING, "embedding_revision": EMBEDDING_REVISION, "projection": "PCA",
            "counts": {kind: sum(r["kind"] == kind for r in records) for kind in ("annotation", "note")},
            "documents": len({r["document_id"] for r in records})}
        with vault.lock():
            if fingerprint(evidence(vault)) != source_hash:
                raise ValueError("Notes changed during Kura analysis. Run again to reuse checkpoints and include the changes.")
            if previous:
                atomic_write(vault.root / ("knowledge/kura-revision-" + uuid4().hex + ".json"), encoded(previous))
            atomic_write(vault.root / "knowledge/kura.json", encoded(saved))
        return state(vault)
