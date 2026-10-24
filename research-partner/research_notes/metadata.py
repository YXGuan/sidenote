"""Citation metadata from embedded standards and optional existing tools."""
from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from urllib.parse import quote, urlsplit

from .network import get_json, request
from .store import atomic_write, document_id, encoded, normalize_source, normalize_url, now, read_json


def strings(value):
    if not isinstance(value, list):
        value = [value] if value else []
    return list(dict.fromkeys(v.strip()[:1000] for v in value[:200] if isinstance(v, str) and v.strip()))


def clean_metadata(value, url, source):
    if not isinstance(value, dict):
        raise ValueError("Metadata must be an object")
    result = {"url": normalize_source(url)}
    for field in ("title", "journal", "doi", "published", "publisher", "canonical_url", "arxiv_id", "description"):
        choices = strings(value.get(field))
        if choices:
            result[field] = choices[0]
    abstract = value.get("abstract")
    if isinstance(abstract, list):
        abstract = " ".join(v for v in abstract[:10] if isinstance(v, str))
    if isinstance(abstract, str) and abstract.strip():
        result["abstract"] = abstract.strip()[:14000]
    for field in ("authors", "institutions"):
        values = strings(value.get(field))
        if values:
            result[field] = values
    if result.get("doi"):
        doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", result["doi"], flags=re.I).strip()
        if re.fullmatch(r"10\.\d{4,9}/\S+", doi):
            result["doi"] = doi
        else:
            result.pop("doi")
    # Field-level evidence identifies observed data, not model guesses.
    result["provenance"] = {k: {"source": source, "url": url} for k in result if k not in ("url", "provenance")}
    return result


def clean_manual_metadata(value, url):
    allowed = {"authors", "institutions", "journal", "doi", "published", "arxiv_id", "description"}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError("Unsupported metadata correction")
    for key, item in value.items():
        if key in ("authors", "institutions"):
            if not isinstance(item, list) or len(item) > 200 or any(not isinstance(v, str) or len(v) > 1000 for v in item):
                raise ValueError("Authors and institutions must be lists of names")
        elif not isinstance(item, str) or len(item) > 1000:
            raise ValueError("Metadata fields must be text of at most 1000 characters")
    cleaned = clean_metadata(value, url, "manual")
    if value.get("doi") and "doi" not in cleaned:
        raise ValueError("Use a valid DOI, for example 10.1145/1234567")
    if value.get("arxiv_id") and not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-zA-Z.-]+/\d{7})(?:v\d+)?", value["arxiv_id"].strip()):
        raise ValueError("Use an arXiv ID such as 1706.03762")
    return {key: cleaned.get(key, [] if key in ("authors", "institutions") else "") for key in value} | {"provenance": {key: {"source": "manual", "url": url} for key in value}}


class EmbeddedMetadata(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = {}
        self.title = []
        self.jsonld = []
        self.in_title = False
        self.in_json = False
        self.json_chunks = []
        self.canonical = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            name = (attrs.get("name") or attrs.get("property") or "").lower()
            if name and attrs.get("content"):
                self.meta.setdefault(name, []).append(attrs["content"])
        if tag == "link" and "canonical" in attrs.get("rel", "").lower().split():
            self.canonical = attrs.get("href")
        if tag == "title":
            self.in_title = True
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self.in_json = True
            self.json_chunks = []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.in_json:
            self.in_json = False
            try:
                self.jsonld.append(json.loads("".join(self.json_chunks)))
            except (ValueError, RecursionError):
                pass

    def handle_data(self, data):
        if self.in_title:
            self.title.append(data)
        if self.in_json:
            self.json_chunks.append(data)

    def result(self):
        def first(*names):
            return next((self.meta[name] for name in names if self.meta.get(name)), [])
        result = {
            "title": first("citation_title", "dc.title", "og:title", "twitter:title") or "".join(self.title).strip(),
            "authors": first("citation_author", "dc.creator", "author"),
            "institutions": first("citation_author_institution", "citation_author_affiliation"),
            "journal": first("citation_journal_title", "prism.publicationname"),
            "published": first("citation_publication_date", "citation_date", "article:published_time"),
            "doi": first("citation_doi", "dc.identifier", "prism.doi"),
            "publisher": first("citation_publisher", "dc.publisher"),
            "canonical_url": self.canonical,
            "description": first("og:description", "description", "twitter:description"),
            "abstract": " ".join(first("citation_abstract", "dc.description", "dcterms.abstract")),
            "arxiv_id": first("citation_arxiv_id"),
        }
        candidates = []
        has_citation_title = bool(first("citation_title", "dc.title"))
        for obj in self.jsonld:
            if isinstance(obj, list):
                candidates.extend(obj)
            elif isinstance(obj, dict):
                candidates.extend(obj.get("@graph", [obj]))
        for item in candidates:
            if not isinstance(item, dict):
                continue
            types = item.get("@type", [])
            types = [types] if isinstance(types, str) else (types if isinstance(types, list) else [])
            if not any(t in ("ScholarlyArticle", "Article", "NewsArticle", "BlogPosting", "Book", "WebPage") for t in types):
                continue
            if not has_citation_title and (item.get("headline") or item.get("name")):
                result["title"] = item.get("headline") or item.get("name")
                has_citation_title = True
            authors, institutions = [], []
            people = item.get("author", [])
            if not isinstance(people, list):
                people = [people]
            for person in people:
                if isinstance(person, str):
                    authors.append(person)
                elif isinstance(person, dict):
                    authors.extend(strings(person.get("name")))
                    affiliations = person.get("affiliation", [])
                    if not isinstance(affiliations, list):
                        affiliations = [affiliations]
                    for affiliation in affiliations:
                        institutions.extend(strings(affiliation.get("name") if isinstance(affiliation, dict) else affiliation))
            result["authors"] = result["authors"] or authors
            result["institutions"] = result["institutions"] or institutions
            result["published"] = result["published"] or item.get("datePublished")
            result["description"] = result["description"] or item.get("description")
            result["abstract"] = result["abstract"] or item.get("abstract")
            part = item.get("isPartOf", {})
            result["journal"] = result["journal"] or (part.get("name") if isinstance(part, dict) else None)
            identifiers = item.get("identifier", [])
            if not isinstance(identifiers, list):
                identifiers = [identifiers]
            for identifier in identifiers:
                if isinstance(identifier, dict) and str(identifier.get("propertyID", "")).lower() == "doi":
                    result["doi"] = result["doi"] or identifier.get("value")
        return result


def parse_html(html, url):
    parser = EmbeddedMetadata()
    parser.feed(html)
    return clean_metadata(parser.result(), url, "embedded-metadata")


def crossref_metadata(doi, get=get_json):
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    message = get(url)["message"]
    authors, institutions = [], []
    for person in message.get("author", []):
        authors.append(person.get("name") or " ".join(filter(None, [person.get("given"), person.get("family")])))
        institutions.extend(a["name"] for a in person.get("affiliation", []) if a.get("name"))
    dates = message.get("published", {}).get("date-parts", [])
    values = {"title": message.get("title"), "authors": authors, "institutions": institutions, "journal": message.get("container-title"), "doi": message.get("DOI"), "published": "-".join(str(i) for i in dates[0]) if dates else None, "publisher": message.get("publisher")}
    return clean_metadata(values, url, "crossref")


def zotero_metadata(url, endpoint, get=get_json):
    parsed = urlsplit(endpoint)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username or parsed.password:
        raise ValueError("Use a local Zotero translation-server URL, such as http://127.0.0.1:1969")
    items = get(endpoint.rstrip("/") + "/web", data=url, content_type="text/plain")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise ValueError("Zotero could not translate this page")
    item = items[0]
    people = [p for p in item.get("creators", []) if p.get("creatorType") == "author"]
    return clean_metadata({"title": item.get("title"), "authors": [p.get("name") or " ".join(filter(None, [p.get("firstName"), p.get("lastName")])) for p in people], "journal": item.get("publicationTitle"), "doi": item.get("DOI"), "published": item.get("date"), "publisher": item.get("publisher")}, url, "zotero-translation-server")


def enrich(vault, key, *, crossref=True, zotero_url=None):
    docs = vault.documents()
    if key not in docs:
        raise ValueError("Document not found")
    url = docs[key]["url"]
    body, content_type = request(url, public_only=True)
    if "html" not in content_type.lower():
        raise ValueError("This URL does not serve HTML; capture its landing page metadata in the browser")
    match = re.search(r"charset=([\w-]+)", content_type, re.I)
    metadata = parse_html(body.decode(match[1] if match else "utf-8", errors="replace"), url)
    if zotero_url:
        translated = zotero_metadata(url, zotero_url)
        metadata = merge_metadata(metadata, translated)
    if crossref and metadata.get("doi"):
        metadata = merge_metadata(crossref_metadata(metadata["doi"]), metadata)
    with vault.lock():
        current = read_json(vault.path("metadata", key), {})
        metadata = merge_metadata(current, metadata)
        metadata["url"] = url
        metadata["captured_at"] = now()
        atomic_write(vault.path("metadata", key), encoded(metadata))
        vault.render()
    return metadata


def merge_metadata(old, new):
    merged = old | {k: v for k, v in new.items() if v not in (None, [], "", {})}
    merged["provenance"] = old.get("provenance", {}) | new.get("provenance", {})
    return merged
