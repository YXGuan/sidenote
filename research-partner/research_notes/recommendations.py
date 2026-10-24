"""Semantic Scholar recommendations from the complete, read-time Liked (Auto) set.

GET is local-only. An explicit refresh sends bibliographic identifiers (or a
paper title when no identifier exists), never annotations or personal notes.
"""
import hashlib
import re
from urllib.parse import quote, urlencode, urlsplit

from .local_classifier import link_type
from .network import get_json
from .scholarly import accepted_work, arxiv_id, identifiers, s2_request
from .store import atomic_write, encoded, now, read_json

API = "https://api.semanticscholar.org"
FIELDS = "title,authors,year,venue,abstract,externalIds,citationCount,openAccessPdf"
CACHE = ".local/recommendations.json"


def paper_id(value):
    value = str(value or "")
    return value.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", value) else ""


def doi(value):
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", str(value or ""), flags=re.I)
    return value.lower() if re.fullmatch(r"10\.\d{4,9}/\S+", value) else ""


def identity(doc):
    meta = doc.get("metadata", {})
    ids = identifiers(doc["url"], meta)
    s2 = paper_id(meta.get("semantic_scholar_id"))
    parsed = urlsplit(doc["url"])
    if not s2 and parsed.hostname in ("semanticscholar.org", "www.semanticscholar.org"):
        s2 = paper_id(parsed.path.rstrip("/").split("/")[-1])
    result = {"s2": s2, "doi": doi(ids["doi"]),
              "arxiv": re.sub(r"v\d+$", "", ids["arxiv_id"]).lower()}
    if parsed.hostname == "pubmed.ncbi.nlm.nih.gov" and re.fullmatch(r"/\d+/?", parsed.path):
        result["pmid"] = parsed.path.strip("/")
    return {k: v for k, v in result.items() if v}


def inventory(vault):
    docs = vault.documents()
    candidates, skipped = [], 0
    for doc in docs.values():
        if "liked-auto" not in doc.get("automatic_collections", []):
            continue
        if doc.get("reaction") in ("bad", "dislike", "hate"):
            continue
        ids = identity(doc)
        if not ids and doc.get("classification", {}).get("link_type") != "paper" and link_type(doc) != "paper":
            skipped += 1
            continue
        title = doc.get("metadata", {}).get("title") or doc["title"]
        candidates.append({"document_id": doc["id"], "title": title, "identity": ids,
                           "authors": doc.get("metadata", {}).get("authors", [])})
    candidates.sort(key=lambda item: item["document_id"])
    signature = hashlib.sha256(encoded({"version": 1, "seeds": candidates})).hexdigest()
    return docs, candidates, skipped, signature


def aliases(ids):
    return {(key, value) for key, value in ids.items() if value}


def state(vault):
    docs, candidates, skipped, signature = inventory(vault)
    cache = read_json(vault.root / CACHE, {})
    # Saved works are excluded on every read, including after an unchanged refresh.
    saved = set().union(*(aliases(identity(doc)) for doc in docs.values()))
    papers = [p for p in cache.get("papers", []) if not aliases(p["identity"]) & saved]
    return {"provider": "Semantic Scholar", "collection": "liked-auto",
            "eligible_count": len(candidates), "skipped_count": skipped,
            "used_seed_count": cache.get("used_seed_count", 0),
            "unresolved_count": cache.get("unresolved_count", 0),
            "seeds": cache.get("seeds", []), "papers": papers,
            "generated_at": cache.get("generated_at"),
            "stale": bool(cache) and cache.get("input_hash") != signature}


def _identifier(ids):
    for kind, prefix in (("s2", ""), ("doi", "DOI:"), ("arxiv", "ARXIV:"), ("pmid", "PMID:")):
        if ids.get(kind):
            return prefix + ids[kind]
    return ""


def _paper(work):
    if not isinstance(work, dict) or not paper_id(work.get("paperId")) or not isinstance(work.get("title"), str):
        raise ValueError("Semantic Scholar returned invalid paper data; previous recommendations are retained")
    key = paper_id(work["paperId"])
    external = work.get("externalIds") or {}
    ids = {"s2": key, "doi": doi(external.get("DOI")),
           "arxiv": re.sub(r"v\d+$", "", arxiv_id(external.get("ArXiv"))).lower(),
           "pmid": str(external.get("PubMed") or "")}
    pdf = (work.get("openAccessPdf") or {}).get("url") or ""
    parsed = urlsplit(pdf)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        pdf = ""
    return {"paper_id": key, "title": work["title"][:2000],
            "url": "https://www.semanticscholar.org/paper/" + key,
            "authors": [p["name"][:200] for p in work.get("authors") or [] if isinstance(p, dict) and isinstance(p.get("name"), str)],
            "year": work.get("year") if type(work.get("year")) is int else None,
            "venue": str(work.get("venue") or "")[:1000],
            "abstract": str(work.get("abstract") or "")[:30000],
            "citation_count": work.get("citationCount") if type(work.get("citationCount")) is int else None,
            "pdf_url": pdf, "identity": {k: v for k, v in ids.items() if v}}


def refresh(vault, *, approved=False, get=get_json):
    if approved is not True:
        raise ValueError("Choose Refresh recommendations to send paper identifiers and unresolved paper titles to Semantic Scholar")
    _docs, candidates, _skipped, signature = inventory(vault)
    key = vault.secret("S2_API_KEY")
    headers = {"x-api-key": key} if key else None

    def api(path, **kwargs):
        return s2_request(get, API + path, api_headers=headers, attempts=2, max_bytes=10_000_000, **kwargs)

    seeds = [dict(item, status="unresolved") for item in candidates]
    by_identifier = {}
    for seed in seeds:
        identifier = _identifier(seed["identity"])
        if identifier:
            by_identifier.setdefault(identifier, []).append(seed)
    identifiers_to_resolve = list(by_identifier)
    # Every seed is attempted. Batch size is an API bound, not a library cap.
    for offset in range(0, len(identifiers_to_resolve), 500):
        batch = identifiers_to_resolve[offset:offset + 500]
        works = api("/graph/v1/paper/batch?fields=externalIds", data={"ids": batch})
        if not isinstance(works, list) or len(works) != len(batch):
            raise ValueError("Semantic Scholar returned an incomplete seed lookup; retry the refresh")
        for identifier, work in zip(batch, works):
            if work is None:
                continue
            canonical = paper_id(work.get("paperId")) if isinstance(work, dict) else ""
            if not canonical:
                raise ValueError("Semantic Scholar returned an invalid seed identifier")
            for seed in by_identifier[identifier]:
                seed.update(paper_id=canonical, status="used")
    for seed in seeds:
        if seed["identity"]:
            continue
        result = api("/graph/v1/paper/search?" + urlencode({"query": seed["title"][:500], "limit": 5, "fields": "title,authors,externalIds"}))
        matched = accepted_work(result.get("data", []), seed["title"], {"authors": seed["authors"]})
        canonical = paper_id(matched.get("paperId")) if matched else ""
        if canonical:
            seed.update(paper_id=canonical, status="used")
    positive = sorted({seed["paper_id"] for seed in seeds if seed["status"] == "used"})
    papers = []
    if positive:
        result = api("/recommendations/v1/papers/?" + urlencode({"fields": FIELDS, "limit": 500}),
                     data={"positivePaperIds": positive, "negativePaperIds": []})
        if not isinstance(result, dict) or not isinstance(result.get("recommendedPapers"), list):
            raise ValueError("Semantic Scholar returned invalid recommendations; previous results are retained")
        seen = set(positive)
        seen_aliases = set()
        for work in result["recommendedPapers"]:
            paper = _paper(work)
            if paper["paper_id"] not in seen and not aliases(paper["identity"]) & seen_aliases:
                papers.append(paper)
                seen.add(paper["paper_id"])
                seen_aliases.update(aliases(paper["identity"]))
    with vault.lock():
        if inventory(vault)[3] != signature:
            raise ValueError("Liked papers changed during the request; refresh again")
        atomic_write(vault.root / CACHE, encoded({"input_hash": signature, "generated_at": now(),
            "used_seed_count": len(positive), "unresolved_count": sum(s["status"] != "used" for s in seeds),
            "seeds": [{k: s[k] for k in ("document_id", "title", "status", "paper_id") if k in s} for s in seeds],
            "papers": papers}))
    return state(vault)
