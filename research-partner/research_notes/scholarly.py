"""Resolve works conservatively; canonical identities are evidence, never LLM output."""
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import re
import time
import threading
import unicodedata
from urllib.parse import quote, unquote, urlencode, urlsplit

from .metadata import merge_metadata, parse_html
from .network import get_json, request
from .store import atomic_write, encoded, now, read_json

_s2_lock = threading.Lock()
_s2_last_request = 0.0


def openalex_key(value):
    match = re.fullmatch(r"(?:https://(?:api\.)?openalex\.org/(?:works/)?)?(W\d+)", str(value), re.I)
    return match[1].upper() if match else None


def arxiv_id(value):
    value = str(value or "").strip()
    if value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if parsed.hostname not in ("arxiv.org", "www.arxiv.org", "export.arxiv.org"):
            return ""
        value = re.sub(r"^/(?:abs|pdf|html)/", "", parsed.path).removesuffix(".pdf")
    value = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    return value if re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})(?:v\d+)?", value) else ""


def fetch_openalex(url, get, headers):
    """Resolve a candidate to the complete singleton response, never a search projection."""
    work = get(url, api_headers=headers, attempts=2)
    key = openalex_key(work.get("id")) if isinstance(work, dict) else None
    if not key:
        raise ValueError("OpenAlex did not return a work ID")
    canonical = "https://api.openalex.org/works/" + key
    if url != canonical:
        work = get(canonical, api_headers=headers, attempts=2)
        if not isinstance(work, dict) or not openalex_key(work.get("id")):
            raise ValueError("OpenAlex did not return a complete work")
    return work


def s2_request(get, url, **kwargs):
    """Share the one-request/second budget across capture and manual workers."""
    global _s2_last_request
    if get is not get_json:
        return get(url, **kwargs)  # Deterministic injected test transport.
    with _s2_lock:
        time.sleep(max(0, 1.05 - (time.monotonic() - _s2_last_request)))
        _s2_last_request = time.monotonic()
        return get(url, **kwargs)


def normalized(text):
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKD", str(text)).casefold()))


def identifiers(url, metadata):
    doi = metadata.get("doi", "")
    parsed = urlsplit(url)
    if not doi and parsed.hostname in ("doi.org", "dx.doi.org", "dl.acm.org", "ieeexplore.ieee.org", "link.springer.com", "onlinelibrary.wiley.com", "science.org", "www.science.org", "nature.com", "www.nature.com", "sciencedirect.com", "www.sciencedirect.com"):
        match = re.search(r"10\.\d{4,9}/[^?#\s]+", unquote(parsed.path))
        if match:
            doi = re.sub(r"/(?:pdf|full|abstract)$", "", match[0], flags=re.I)
    arxiv = arxiv_id(metadata.get("arxiv_id"))
    if not arxiv and parsed.hostname in ("arxiv.org", "www.arxiv.org", "export.arxiv.org"):
        match = re.search(r"/(?:abs|pdf|html)/((?:\d{4}\.\d{4,5}|[a-z.-]+/\d{7})(?:v\d+)?)(?:\.pdf)?", parsed.path, re.I)
        if match:
            arxiv = match[1]
    return {"doi": doi, "arxiv_id": arxiv}


def accepted_work(candidates, title, metadata):
    """Require a unique close title and corroboration for short/fuzzy titles."""
    target = normalized(title)
    if len(target) < 15 or str(title).startswith(("http:", "https:", "urn:")):
        return None
    matches = []
    expected_authors = {normalized(name).split()[-1] for name in metadata.get("authors", []) if normalized(name)}
    for work in candidates:
        if not isinstance(work, dict):
            continue
        candidate = normalized(work.get("title", ""))
        exact = target == candidate
        score = SequenceMatcher(None, target, candidate).ratio()
        authors = work.get("authors") or [item.get("author", {}) for item in work.get("authorships", [])]
        surnames = {normalized(person.get("name") or person.get("display_name", "")).split()[-1] for person in authors if normalized(person.get("name") or person.get("display_name", ""))}
        corroborated = bool(expected_authors & surnames)
        if (exact and (len(target.split()) >= 5 or corroborated)) or (score >= .94 and len(target.split()) >= 5 and corroborated):
            expected_doi = metadata.get("doi", "").lower()
            actual_doi = (work.get("doi") or work.get("externalIds", {}).get("DOI") or "").lower().removeprefix("https://doi.org/")
            if not expected_doi or not actual_doi or expected_doi == actual_doi:
                matches.append(work)
    return matches[0] if len(matches) == 1 else None


def abstract_text(index):
    if not isinstance(index, dict):
        return ""
    positions = {}
    for word, offsets in index.items():
        if isinstance(word, str) and isinstance(offsets, list):
            for offset in offsets:
                if isinstance(offset, int) and 0 <= offset < 10000:
                    positions[offset] = word
    return " ".join(positions[key] for key in sorted(positions))[:14000]


def oa_metadata(work):
    people, institutions = [], []
    for item in work.get("authorships", []):
        author = item.get("author", {})
        affiliations = [{"id": v.get("id"), "name": v.get("display_name")} for v in item.get("institutions", []) if v.get("display_name")]
        institutions.extend(v["name"] for v in affiliations)
        if author.get("display_name"):
            people.append({"name": author["display_name"], "openalex_id": author.get("id"), "orcid": author.get("orcid"), "institutions": affiliations})
    source = (work.get("primary_location") or {}).get("source") or {}
    key = openalex_key(work.get("id"))
    locations = [work.get("primary_location"), work.get("best_oa_location"), *(work.get("locations") or [])]
    arxiv = next((identifier for location in locations if isinstance(location, dict)
                  for field in ("landing_page_url", "pdf_url") if (identifier := arxiv_id(location.get(field)))), "")
    topics = [v for v in (work.get("topics") or []) if isinstance(v, dict) and isinstance(v.get("display_name"), str)]
    keywords = [v for v in (work.get("keywords") or []) if isinstance(v, dict) and isinstance(v.get("display_name"), str)]
    return {"title": work.get("title"), "doi": (work.get("doi") or "").removeprefix("https://doi.org/"), "openalex_id": "https://openalex.org/" + key if key else None,
            "openalex_api_url": "https://api.openalex.org/works/" + key if key else None,
            "openalex_fetched_at": now(), "openalex_topics": topics, "openalex_keywords": keywords,
            "arxiv_id": arxiv, "authors": [p["name"] for p in people], "author_identities": people, "institutions": list(dict.fromkeys(institutions)), "journal": source.get("display_name"), "published": work.get("publication_date"), "abstract": abstract_text(work.get("abstract_inverted_index")), "scholarly_topics": [v["display_name"] for v in topics], "citation_counts": {"openalex": work.get("cited_by_count")}, "citation_counts_as_of": now()}


def s2_metadata(work):
    external = work.get("externalIds") or {}
    people = [{"name": p["name"], "semantic_scholar_id": p.get("authorId"), "institutions": [{"name": v} for v in p.get("affiliations", [])]} for p in work.get("authors", []) if p.get("name")]
    return {"title": work.get("title"), "doi": external.get("DOI"), "arxiv_id": external.get("ArXiv"), "semantic_scholar_id": work.get("paperId"), "authors": [p["name"] for p in people], "author_identities": people, "abstract": work.get("abstract"), "journal": (work.get("journal") or {}).get("name") or work.get("venue"), "published": work.get("publicationDate"), "institutions": list(dict.fromkeys(v["name"] for p in people for v in p["institutions"])), "citation_counts": {"semantic_scholar": work.get("citationCount")}, "citation_counts_as_of": now()}


def merge_scholarly(old, new):
    # Evidence from different resolved works must never share author IDs or counts.
    identity_changed = any(old.get(k) and new.get(k) and str(old[k]).casefold() != str(new[k]).casefold() for k in ("doi", "openalex_id", "semantic_scholar_id"))
    if identity_changed:
        old = {k: v for k, v in old.items() if k not in ("openalex_id", "openalex_api_url", "openalex_fetched_at", "openalex_topics", "openalex_keywords", "semantic_scholar_id", "arxiv_id", "author_identities", "citation_counts", "citation_counts_as_of", "authors", "institutions", "abstract", "scholarly_topics", "scholarly_lookup", "journal")}
    merged = merge_metadata(old, {k: v for k, v in new.items() if v not in (None, "", [], {})})
    # Empty lists from a fresh OpenAlex response must clear old classifications.
    for field in ("openalex_topics", "openalex_keywords", "scholarly_topics"):
        if field in new:
            merged[field] = new[field]
    merged["citation_counts"] = old.get("citation_counts", {}) | {k: v for k, v in new.get("citation_counts", {}).items() if isinstance(v, int) and not isinstance(v, bool) and v >= 0}
    people = [dict(p) for p in old.get("author_identities", [])]
    incoming = new.get("author_identities", [])
    old_counts = Counter(normalized(p["name"]) for p in people)
    new_counts = Counter(normalized(p["name"]) for p in incoming)
    for person in incoming:
        name = normalized(person["name"])
        same = next((p for p in people if normalized(p["name"]) == name), None)
        # This crosswalk is only within the SAME resolved work. Never merge a name globally.
        if same and old_counts[name] == new_counts[name] == 1:
            same.update({k: v for k, v in person.items() if v and k != "institutions"})
            same["institutions"] = same.get("institutions") or person.get("institutions", [])
        else:
            people.append(person)
    merged["author_identities"] = people
    merged["institutions"] = list(dict.fromkeys(old.get("institutions", []) + new.get("institutions", [])))
    if old.get("authors"):
        merged["authors"] = old["authors"]
    return merged


def lookup(doc, vault, get=get_json, *, openalex_records=None):
    metadata = doc["metadata"]
    ids = identifiers(doc["url"], metadata)
    title = metadata.get("title") or doc["title"]
    result = {k: v for k, v in ids.items() if v}
    statuses = {}
    oa_key, s2_key = vault.secret("OPENALEX_API_KEY"), vault.secret("S2_API_KEY")
    oa_headers = {"Authorization": "Bearer " + oa_key} if oa_key else None
    s2_headers = {"x-api-key": s2_key} if s2_key else None
    oa_work = None
    def remember_openalex(work):
        key = openalex_key(work.get("id"))
        if key and openalex_records is not None:
            openalex_records[key] = work
        return oa_metadata(work)
    try:
        if openalex_key(metadata.get("openalex_id")):
            oa_work = fetch_openalex("https://api.openalex.org/works/" + openalex_key(metadata["openalex_id"]), get, oa_headers)
        elif ids["doi"]:
            oa_work = fetch_openalex("https://api.openalex.org/works/" + quote("https://doi.org/" + ids["doi"], safe=""), get, oa_headers)
        else:
            values = get("https://api.openalex.org/works?" + urlencode({"search": title[:500], "per_page": 5}), api_headers=oa_headers, attempts=2)
            oa_work = accepted_work(values.get("results", []), title, metadata)
            if oa_work:
                key = openalex_key(oa_work.get("id"))
                oa_work = fetch_openalex("https://api.openalex.org/works/" + key, get, oa_headers) if key else None
        if oa_work and oa_work.get("id"):
            result = merge_scholarly(result, remember_openalex(oa_work))
            statuses["openalex"] = "matched"
        else:
            statuses["openalex"] = "unresolved"
    except (RuntimeError, OSError, ValueError, KeyError, TypeError):
        statuses["openalex"] = "unavailable"
    fields = "title,authors,authors.affiliations,externalIds,citationCount,abstract,venue,journal,publicationDate"
    try:
        identifier = "DOI:" + (ids["doi"] or result.get("doi", "")) if ids["doi"] or result.get("doi") else ("ARXIV:" + re.sub(r"v\d+$", "", ids["arxiv_id"]) if ids["arxiv_id"] else "")
        parsed = urlsplit(doc["url"])
        if not identifier and parsed.hostname == "pubmed.ncbi.nlm.nih.gov" and re.fullmatch(r"/\d+/?", parsed.path):
            identifier = "PMID:" + parsed.path.strip("/")
        if identifier:
            s2_work = s2_request(get, "https://api.semanticscholar.org/graph/v1/paper/" + quote(identifier, safe="") + "?" + urlencode({"fields": fields}), api_headers=s2_headers, attempts=2)
        else:
            values = s2_request(get, "https://api.semanticscholar.org/graph/v1/paper/search?" + urlencode({"query": title[:500], "limit": 5, "fields": fields}), api_headers=s2_headers, attempts=2)
            s2_work = accepted_work(values.get("data", []), title, metadata | {"doi": result.get("doi") or ids["doi"]})
        if s2_work and s2_work.get("paperId"):
            result = merge_scholarly(result, s2_metadata(s2_work))
            statuses["semantic_scholar"] = "matched"
        else:
            statuses["semantic_scholar"] = "unresolved"
    except (RuntimeError, OSError, ValueError, KeyError, TypeError):
        statuses["semantic_scholar"] = "unavailable"
    # arXiv → Semantic Scholar DOI → OpenAlex, without an ambiguous title search.
    if not oa_work and statuses.get("semantic_scholar") == "matched" and not ids["doi"]:
        try:
            if result.get("doi"):
                work = fetch_openalex("https://api.openalex.org/works/" + quote("https://doi.org/" + result["doi"], safe=""), get, oa_headers)
            else:
                values = get("https://api.openalex.org/works?" + urlencode({"search": result.get("title", title)[:500], "per_page": 5}), api_headers=oa_headers, attempts=2)
                work = accepted_work(values.get("results", []), result.get("title", title), result)
                if work:
                    key = openalex_key(work.get("id"))
                    work = fetch_openalex("https://api.openalex.org/works/" + key, get, oa_headers) if key else None
            if work and work.get("id"):
                result = merge_scholarly(result, remember_openalex(work))
                statuses["openalex"] = "matched"
        except (RuntimeError, OSError, ValueError, KeyError, TypeError):
            statuses["openalex"] = "unavailable"
    result["scholarly_lookup"] = {"checked_at": now(), "providers": statuses}
    result["provenance"] = {key: {"source": "scholarly-index", "providers": [p for p, status in statuses.items() if status == "matched"]} for key in result if key not in ("provenance", "scholarly_lookup")}
    return result


def enrichment_signature(vault, doc):
    return hashlib.sha256(encoded({"url": doc["url"], "title": doc["title"],
        "identifiers": identifiers(doc["url"], doc["metadata"]),
        "providers": [bool(vault.secret(name)) for name in ("OPENALEX_API_KEY", "S2_API_KEY")]})).hexdigest()


def enrichment_due(vault, doc, *, clock=None):
    checked = doc["metadata"].get("scholarly_lookup", {}).get("checked_at")
    providers = doc["metadata"].get("scholarly_lookup", {}).get("providers", {})
    ttl = 7 * 86400 if providers and all(s == "matched" for s in providers.values()) else 3600
    oa_key = openalex_key(doc["metadata"].get("openalex_id"))
    needs_openalex = oa_key and (not vault.path("openalex", oa_key).exists() or "openalex_keywords" not in doc["metadata"])
    signature = doc["metadata"].get("scholarly_lookup", {}).get("input_hash")
    if not checked or needs_openalex or signature and signature != enrichment_signature(vault, doc):
        return True
    try:
        age = ((clock or datetime.now(timezone.utc)) - datetime.fromisoformat(checked.replace("Z", "+00:00"))).total_seconds()
        return not 0 <= age < ttl
    except (ValueError, TypeError):
        return True


def enrich_document(vault, key, *, force=False, get=get_json, fetch_page=True):
    doc = vault.documents().get(key)
    if not doc:
        raise ValueError("Document not found")
    if not force and not enrichment_due(vault, doc):
        return doc
    input_signature = enrichment_signature(vault, doc)
    embedded = {}
    ids = identifiers(doc["url"], doc["metadata"])
    if fetch_page and (not any(ids.values()) or ids["arxiv_id"] and not doc["metadata"].get("abstract")):
        try:
            page_url = "https://arxiv.org/abs/" + ids["arxiv_id"] if ids["arxiv_id"] else doc["url"]
            if urlsplit(page_url).hostname == "aclanthology.org" and urlsplit(page_url).path.endswith(".pdf"):
                page_url = page_url[:-4] + "/"
            body, kind = request(page_url, public_only=True, attempts=1)
            if "html" in kind.lower():
                embedded = parse_html(body.decode("utf-8", errors="replace"), doc["url"])
                doc = doc | {"title": embedded.get("title") or doc["title"], "metadata": merge_metadata(doc["metadata"], embedded)}
        except (RuntimeError, OSError, ValueError):
            pass
    records = {}
    indexed = lookup(doc, vault, get, openalex_records=records)
    result = merge_metadata(embedded, indexed)
    for field in ("openalex_topics", "openalex_keywords", "scholarly_topics"):
        if field in indexed:
            result[field] = indexed[field]
    with vault.lock():
        latest = vault.documents().get(key)
        if not latest or enrichment_signature(vault, latest) != input_signature:
            raise ValueError("Source changed during research lookup; retry")
        for record_key, record in records.items():
            cached_path = vault.path("openalex", record_key)
            atomic_write(cached_path, encoded(record))
            cached_path.touch()  # Track successful fetches even when API content is unchanged.
        path = vault.path("metadata", key)
        current = read_json(path, {})
        stamp = now()
        merged = merge_scholarly(current, result)
        if result.get("authors"):
            merged["authors"] = result["authors"]
        merged.update(url=doc["url"], modified_at=stamp, first_captured_at=current.get("first_captured_at") or current.get("captured_at") or doc["created_at"] or stamp)
        atomic_write(path, encoded(merged))
        latest = vault.documents().get(key)
        if latest:
            merged["scholarly_lookup"]["input_hash"] = enrichment_signature(vault, latest)
            atomic_write(path, encoded(merged))
        vault.render()
    from .organization import auto_organize_page
    return auto_organize_page(vault, key)


def cache_openalex(vault, *, force=False, progress=None, get=get_json):
    """Backfill full OpenAlex records for already resolved library items only."""
    docs = [doc for doc in vault.documents().values() if openalex_key(doc["metadata"].get("openalex_id"))]
    status = {"total": len(docs), "done": 0, "fetched": 0, "cached": 0, "failed": 0}
    with vault.lock():
        vault.snapshot()
    for doc in docs:
        key = openalex_key(doc["metadata"]["openalex_id"])
        try:
            path = vault.path("openalex", key)
            fresh = path.exists() and time.time() - path.stat().st_mtime < 7 * 86400
            if fresh and not force:
                work = read_json(path)
                status["cached"] += 1
            else:
                secret = vault.secret("OPENALEX_API_KEY")
                work = fetch_openalex("https://api.openalex.org/works/" + key, get, {"Authorization": "Bearer " + secret} if secret else None)
                status["fetched"] += 1
            resolved = openalex_key(work.get("id"))
            if not resolved:
                raise ValueError("Invalid cached OpenAlex work")
            metadata = oa_metadata(work)
            if fresh and not force:
                metadata["openalex_fetched_at"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
            with vault.lock():
                latest = vault.documents().get(doc["id"])
                if not latest or openalex_key(latest["metadata"].get("openalex_id")) != key:
                    raise ValueError("Work changed during lookup")
                atomic_write(vault.path("openalex", resolved), encoded(work))
                if not fresh or force:
                    vault.path("openalex", resolved).touch()
                current = read_json(vault.path("metadata", doc["id"]), {})
                metadata["provenance"] = {field: {"source": "openalex", "url": metadata["openalex_api_url"]} for field in metadata if field != "provenance"}
                merged = merge_scholarly(current, metadata)
                merged["modified_at"] = now()
                atomic_write(vault.path("metadata", doc["id"]), encoded(merged))
        except (RuntimeError, OSError, ValueError, TypeError, KeyError):
            status["failed"] += 1
        status["done"] += 1
        if progress:
            progress(dict(status))
    with vault.lock():
        vault.render()
        vault.snapshot()
    return status


def enrich_library(vault, *, force=False, progress=None):
    from .local_classifier import link_type
    docs = [doc for doc in vault.documents().values() if link_type(doc) == "paper" or doc["classification"]["link_type"] == "paper"]
    eligible = len(docs)
    docs = [doc for doc in docs if force or enrichment_due(vault, doc)]
    status = {"state": "running", "total": len(docs), "skipped": eligible - len(docs), "done": 0, "matched": 0, "failed": 0}
    if progress:
        progress(dict(status))
    for doc in docs:
        try:
            result = enrich_document(vault, doc["id"], force=force)
            providers = result["metadata"].get("scholarly_lookup", {}).get("providers", {})
            status["matched"] += "matched" in providers.values()
            status["failed"] += "matched" not in providers.values()
        except (RuntimeError, OSError, ValueError):
            status["failed"] += 1
        status["done"] += 1
        if progress:
            progress(dict(status))
        if status["done"] < status["total"]:
            time.sleep(1.05)  # Do not pause on pages skipped by the cache.
    status.update(state="partial" if status["failed"] else "complete", completed=now())
    if docs:
        with vault.lock():
            vault.snapshot()
    if progress:
        progress(dict(status))
    return status
