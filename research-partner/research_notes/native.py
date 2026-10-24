"""Local operations used by the modified upstream Hypothesis client."""
import hashlib
import json

from .intelligence import codex_analyze, fingerprint, model_input, validate_result
from .metadata import clean_metadata, merge_metadata
from .store import atomic_write, document_id, encoded, normalize_source, now, read_json, safe_id


def annotation_digest(annotation):
    return hashlib.sha256(encoded({k: annotation.get(k) for k in ("id", "uri", "text", "target", "updated")})).hexdigest()


def suggest_for_page(vault, key, runner=None, force=False):
    from .organization import organize_page, settings
    if not force and not settings(vault)["automatic"]:
        return vault.documents()[key]
    return organize_page(vault, key, runner=runner, force=force)


def update_annotation_state(vault, annotation_id, *, reaction):
    safe_id(annotation_id)
    if reaction not in (None, "like", "dislike"):
        raise ValueError("Reaction must be like, dislike, or null")
    with vault.lock():
        annotation = read_json(vault.path("raw", annotation_id))
        if not annotation or annotation.get("user") != f"acct:{vault.config().get('user')}@hypothes.is":
            raise ValueError("Annotation not found in this account's backup")
        state = read_json(vault.path("annotation_state", annotation_id), {})
        state.update(reaction=reaction, updated=now())
        atomic_write(vault.path("annotation_state", annotation_id), encoded(state))
        vault.render()
    return vault.documents(include_removed=True)[document_id(annotation["uri"])]


def analyze_annotation(vault, annotation_id, runner=codex_analyze):
    safe_id(annotation_id)
    annotation = read_json(vault.path("raw", annotation_id))
    if not annotation or annotation.get("user") != f"acct:{vault.config().get('user')}@hypothes.is":
        raise ValueError("Annotation not found in this account's backup")
    digest = annotation_digest(annotation)
    state = read_json(vault.path("annotation_state", annotation_id), {})
    if state.get("analysis", {}).get("input_hash") == digest:
        return vault.documents()[document_id(annotation["uri"])]
    doc = vault.documents()[document_id(annotation["uri"])] | {"annotations": [annotation]}
    result = validate_result(runner(model_input(doc), []), doc)["sentiments"][0]
    result.update(input_hash=digest, generated_at=now(), provider="codex-exec")
    with vault.lock():
        latest = read_json(vault.path("raw", annotation_id))
        if not latest or annotation_digest(latest) != digest:
            raise ValueError("Annotation changed during analysis; retry")
        state = read_json(vault.path("annotation_state", annotation_id), {})
        state.update(analysis=result, updated=now())
        atomic_write(vault.path("annotation_state", annotation_id), encoded(state))
        vault.render()
    return vault.documents()[document_id(annotation["uri"])]


def citation_metadata(document):
    if not isinstance(document, dict):
        return {}
    highwire = document.get("highwire", {})
    dc = document.get("dc", {})
    if not isinstance(highwire, dict) or not isinstance(dc, dict):
        raise ValueError("Invalid document metadata")
    return {"title": highwire.get("title") or document.get("title"), "authors": highwire.get("author") or dc.get("creator"), "institutions": highwire.get("author_institution") or highwire.get("author_affiliation"), "journal": highwire.get("journal_title"), "doi": highwire.get("doi"), "published": highwire.get("publication_date") or highwire.get("date"), "publisher": highwire.get("publisher"), "abstract": " ".join(highwire.get("abstract", []) or dc.get("description", []))}


def mirror_annotation(vault, annotation, document=None):
    if not isinstance(annotation, dict):
        raise ValueError("Expected an annotation")
    safe_id(annotation.get("id"))
    if annotation.get("user") != f"acct:{vault.config().get('user')}@hypothes.is":
        raise ValueError("Only this vault owner's annotations may be mirrored")
    key = document_id(annotation.get("uri"))
    if not isinstance(annotation.get("created"), str) or not isinstance(annotation.get("text", ""), str):
        raise ValueError("Invalid annotation fields")
    # The Hypothesis client flattens document.title; the API exports an array.
    # Store an API-shaped record so subsequent daily imports remain compatible.
    record = json.loads(json.dumps(annotation))
    record = {k: v for k, v in record.items() if not k.startswith("$")}
    if isinstance(record.get("document", {}).get("title"), str):
        record["document"]["title"] = [record["document"]["title"]]
    metadata = clean_metadata(citation_metadata(document or annotation.get("document", {})), annotation["uri"], "hypothesis-client")
    with vault.lock():
        atomic_write(vault.path("raw", annotation["id"]), encoded(record))
        existing = read_json(vault.path("metadata", key), {})
        atomic_write(vault.path("metadata", key), encoded(merge_metadata(existing, metadata)))
        vault.render()
    from .organization import auto_organize_page
    return auto_organize_page(vault, key)


def suggest_for_draft(vault, annotation, runner=codex_analyze):
    if not isinstance(annotation, dict) or not isinstance(annotation.get("text", ""), str):
        raise ValueError("Expected an annotation draft")
    # A draft is analyzed without saving it as a real annotation or uploading it.
    uri = normalize_source(annotation.get("uri"))
    draft = {"id": "draft", "text": annotation.get("text", ""), "tags": annotation.get("tags", []), "target": annotation.get("target", [])}
    title = annotation.get("document", {}).get("title") or uri
    if isinstance(title, list):
        title = title[0] if title else uri
    doc = {"title": title, "url": uri, "tags": draft["tags"], "annotations": [draft]}
    digest = fingerprint(doc)
    cache = vault.root / ".local/draft-analysis" / (digest + ".json")
    cached = read_json(cache)
    if cached:
        return cached
    taxonomy = [t for item in vault.documents().values() for t in item["tags"]]
    result = validate_result(runner(model_input(doc), taxonomy), doc)
    result.update(generated_at=now(), input_hash=digest, provider="codex-exec")
    atomic_write(cache, encoded(result))
    return result
