"""Local Zotero interoperability. Imported evidence never becomes a hosted annotation."""
from __future__ import annotations

import copy
import hashlib
from html import escape
from html.parser import HTMLParser
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, Request, build_opener

from .metadata import clean_metadata, merge_metadata
from .network import tls_context
from .store import atomic_write, document_id, encoded, normalize_url, now, quote_text, read_json

MAX_BYTES = 10_000_000
MAX_ITEMS = 50_000
CSL_TYPES = {
    "journalArticle": "article-journal", "book": "book", "bookSection": "chapter",
    "conferencePaper": "paper-conference", "thesis": "thesis", "report": "report",
    "blogPost": "post-weblog", "newspaperArticle": "article-newspaper",
    "magazineArticle": "article-magazine", "dataset": "dataset", "webpage": "webpage",
}
RIS_TYPES = {
    "JOUR": "article-journal", "EJOUR": "article-journal", "BOOK": "book", "CHAP": "chapter",
    "CONF": "paper-conference", "CPAPER": "paper-conference", "THES": "thesis",
    "RPRT": "report", "BLOG": "post-weblog", "NEWS": "article-newspaper",
    "MGZN": "article-magazine", "DATA": "dataset", "ELEC": "webpage", "GEN": "article",
}
FIELDS = {"title": "title", "DOI": "doi", "container-title": "journal", "publisher": "publisher", "abstract": "abstract"}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)
        if tag in ("p", "div", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(value)
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def date_text(value):
    if not isinstance(value, dict):
        return ""
    parts = value.get("date-parts", [[]])
    if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
        return "-".join(str(part).zfill(4 if index == 0 else 2) for index, part in enumerate(parts[0][:3]))
    return str(value.get("literal") or value.get("raw") or "")


def issued(value):
    match = re.fullmatch(r"(\d{4})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?", value)
    return {"date-parts": [[int(v) for v in match.groups() if v]]} if match else {"literal": value}


def names(people):
    return [person.get("literal") or " ".join(filter(None, (person.get("given"), person.get("family")))) for person in people]


def parse_ris(text):
    records, record, last = [], None, None
    for line in text.lstrip("\ufeff").splitlines():
        if not line.strip():
            continue
        match = re.match(r"^([A-Z0-9]{2})  - ?(.*)$", line)
        if not match:
            if record is None or last is None:
                raise ValueError("Invalid RIS field; expected TY  - … through ER  -")
            record[last][-1] += "\n" + line.strip()
            continue
        tag, value = match.groups()
        if tag == "TY":
            if record is not None:
                raise ValueError("RIS record is missing ER")
            record = {}
        if record is None:
            raise ValueError("RIS record must start with TY")
        if tag == "ER":
            records.append(record)
            record, last = None, None
        else:
            record.setdefault(tag, []).append(value)
            last = tag
    if record is not None:
        raise ValueError("RIS record is missing ER")
    result = []
    for record in records:
        first = lambda *tags: next((record[t][0] for t in tags if record.get(t)), "")
        csl = {"type": RIS_TYPES.get(first("TY"), "article"), "title": first("TI", "T1"),
               "URL": first("UR"), "DOI": first("DO"), "container-title": first("T2", "JF", "JO"),
               "publisher": first("PB"), "abstract": first("AB", "N2"), "volume": first("VL"),
               "issue": first("IS"), "ISBN": first("SN"), "publisher-place": first("CY"),
               "author": [{"literal": name} for name in record.get("AU", record.get("A1", []))]}
        if first("ID"):
            csl["id"] = first("ID")
        if first("PY", "Y1", "DA"):
            csl["issued"] = issued(first("PY", "Y1", "DA").rstrip("/"))
        csl["page"] = "-".join(filter(None, (first("SP"), first("EP"))))
        result.append({"csl": csl, "notes": [plain(v) for v in record.get("N1", [])],
                       "tags": record.get("KW", [])})
    return result


def parse_csl(text):
    records = json.loads(text.lstrip("\ufeff"))
    if isinstance(records, dict):
        records = [records]
    if not isinstance(records, list):
        raise ValueError("CSL JSON must contain an object or array of references")
    return [{"csl": record, "notes": [], "tags": []} for record in records]


def validate_items(items, namespace):
    if not items or len(items) > MAX_ITEMS:
        raise ValueError("Import must contain 1–50,000 references")
    for item in items:
        csl = item["csl"]
        if not isinstance(csl, dict) or not isinstance(csl.get("type"), str) or not isinstance(csl.get("title"), str) or not csl["title"].strip():
            raise ValueError("Every reference needs a type and nonempty title")
        for field in (*FIELDS, "URL", "volume", "issue", "page", "ISBN", "ISSN", "publisher-place", "language"):
            if field in csl and not isinstance(csl[field], str):
                raise ValueError(f"Reference {field} must be text")
        people = csl.get("author", [])
        if not isinstance(people, list) or any(not isinstance(p, dict) or any(not isinstance(p[field], str) for field in ("literal", "given", "family", "suffix", "non-dropping-particle", "dropping-particle") if field in p) for p in people):
            raise ValueError("Reference authors must be CSL name objects")
        if "issued" in csl and not isinstance(csl["issued"], dict):
            raise ValueError("Reference issued date must be a CSL date object")
        identifier = csl.get("id")
        if identifier is not None and not isinstance(identifier, (str, int)):
            raise ValueError("Reference ID must be text or a number")
        # Missing URLs are legitimate (books, offline PDFs). Never dereference imports.
        metadata = clean_metadata({target: csl.get(source) for source, target in FIELDS.items()} |
                                  {"authors": names(people), "published": date_text(csl.get("issued"))}, "urn:sidenote:reference", "zotero-import")
        doi = metadata.get("doi", "").casefold()
        url = csl.get("URL", "")
        if url:
            url = normalize_url(url)
        stable_id = identifier if namespace.startswith(("zotero-desktop:", "zotero-online:")) or isinstance(identifier, str) and identifier.startswith(("http://zotero.org/", "https://www.zotero.org/", "https://zotero.org/", "urn:sidenote:")) else None
        identity = namespace + ":" + str(stable_id or doi or url or digest({k: v for k, v in csl.items() if k != "id"}))
        if isinstance(stable_id, str) and re.fullmatch(r"https?://(?:www\.)?zotero\.org/(?:users|groups)/[1-9]\d*/items/[A-Z0-9]+", stable_id):
            identity = "zotero:" + re.sub(r"^https?://(?:www\.)?zotero\.org/", "", stable_id)
        item.update(identity=identity, metadata=metadata, doi=doi,
                    url=url or ("https://doi.org/" + quote(metadata["doi"], safe="/") if doi else "urn:sidenote:reference:" + digest(identity)[:32]))
        if any(not isinstance(v, str) for v in item["notes"] + item["tags"]):
            raise ValueError("Imported notes and tags must be text")
    return items


def import_items(vault, items, *, namespace, original):
    """Validate the entire batch before writing; preserve manual edits and removed items."""
    if not vault.config().get("user"):
        raise ValueError("Initialize this vault first")
    items = validate_items(items, namespace)
    counts = {"created": 0, "updated": 0, "unchanged": 0, "references": len(items)}
    with vault.lock():
        docs = vault.documents(include_removed=True)
        references = vault.records("references")
        identities = {source["identity"]: key for key, record in references.items() for source in record.get("sources", {}).values()}
        zotero_ids = {source["csl"]["id"]: key for key, record in references.items() for source in record.get("sources", {}).values() if str(source["csl"].get("id", "")).startswith("https://www.zotero.org/")}
        by_doi = {doc["metadata"]["doi"].casefold(): key for key, doc in docs.items() if doc["metadata"].get("doi")}
        # Keep original exports as immutable evidence, addressed by their content hash.
        atomic_write(vault.path("imports", digest(original)), encoded(original))
        for item in items:
            exported_id = str(item["csl"].get("id", "")).removeprefix("urn:sidenote:")
            own_key = exported_id if str(item["csl"].get("id", "")).startswith("urn:sidenote:") and exported_id in docs else None
            key = identities.get(item["identity"]) or zotero_ids.get(item["csl"].get("id")) or by_doi.get(item["doi"]) or own_key or document_id(item["url"])
            url = docs.get(key, {}).get("url", item["url"])
            path = vault.path("metadata", key)
            current = read_json(path, {})
            incoming = copy.deepcopy(item["metadata"])
            incoming["url"] = url
            for evidence in incoming["provenance"].values():
                evidence["url"] = url
            merged = merge_metadata(current, incoming)
            record = references.setdefault(key, {"sources": {}})
            source_key = digest(item["identity"])
            source = {k: item[k] for k in ("identity", "csl", "notes", "tags")}
            changed = record["sources"].get(source_key) != source or merged != current
            counts["created" if key not in docs else "updated" if changed else "unchanged"] += 1
            if changed:
                stamp = now()
                merged.update(first_captured_at=current.get("first_captured_at") or current.get("captured_at") or stamp, modified_at=stamp)
                record["sources"][source_key] = source
                atomic_write(path, encoded(merged))
                atomic_write(vault.path("references", key), encoded(record))
            identities[item["identity"]] = key
            if item["doi"]:
                by_doi[item["doi"]] = key
            docs.setdefault(key, {"url": url})
        vault.render()
    return counts


def import_file(vault, content, format="ris"):
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Reference file must be UTF-8 text of at most 10 MB")
    if format not in ("ris", "csl-json"):
        raise ValueError("Choose ris or csl-json")
    items = parse_ris(content) if format == "ris" else parse_csl(content)
    return import_items(vault, items, namespace=format, original={"format": format, "content": content})


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Zotero API must not redirect requests")


def local_get(path, server_id=None):
    # Fixed loopback destination, no proxy, no redirects, no credentials.
    headers = {"Zotero-API-Version": "3", "Accept": "application/json"}
    if server_id:
        headers["Zotero-Server-ID"] = server_id
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(Request("http://127.0.0.1:23119/api/" + path, headers=headers), timeout=20) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("Zotero response exceeded 10 MB")
            return json.loads(body), response.headers
    except HTTPError as error:
        error.close()
        if error.code == 403:
            raise ValueError("Enable Zotero Settings → Advanced → Allow other applications on this computer to communicate with Zotero") from None
        raise ValueError(f"Zotero local API returned HTTP {error.code}; retry with Zotero open") from None
    except (URLError, TimeoutError, OSError):
        raise ValueError("Open Zotero and enable its local API in Settings → Advanced, then retry") from None


def read_library(vault, *, get, prefix="users/0", namespace="zotero-desktop"):
    """Read a complete, stable library before committing any local changes."""
    rows, server_id, version, expected = [], None, None, None
    for start in range(0, MAX_ITEMS + 100, 100):
        batch, headers = get(f"{prefix}/items?format=json&limit=100&start={start}&sort=dateAdded&direction=asc", server_id)
        if not isinstance(batch, list):
            raise ValueError("Expected a Zotero item list")
        current_server = headers.get("Zotero-Server-ID")
        current_version = headers.get("Last-Modified-Version")
        if expected is None and headers.get("Total-Results") is not None:
            expected = int(headers["Total-Results"])
        if rows and (current_server != server_id or current_version != version):
            raise ValueError("Zotero library changed during import; retry")
        server_id, version = current_server, current_version
        rows.extend(batch)
        if len(rows) > MAX_ITEMS:
            raise ValueError("Zotero import supports at most 50,000 items including notes and attachments")
        if len(batch) < 100:
            break
    if expected is not None and len(rows) != expected:
        raise ValueError("Zotero returned an incomplete library; retry before importing")
    if any(not isinstance(row, dict) or not isinstance(row.get("data", row), dict) for row in rows):
        raise ValueError("Zotero returned an invalid item")
    data = [row.get("data", row) for row in rows if isinstance(row, dict)]
    parents = {row.get("key"): row for row in data if row.get("key")}
    notes = {}
    for row in data:
        if row.get("itemType") not in ("note", "annotation"):
            continue
        parent = row.get("parentItem")
        if parents.get(parent, {}).get("itemType") == "attachment":
            parent = parents[parent].get("parentItem")
        text = plain(row.get("note", "")) if row.get("itemType") == "note" else "\n".join(filter(None, (row.get("annotationText"), row.get("annotationComment"))))
        if text:
            notes.setdefault(parent, []).append(text)
    items = []
    wrappers = {row.get("key", row.get("data", {}).get("key")): row for row in rows}
    for row in data:
        if row.get("deleted") or row.get("itemType") in ("note", "annotation", "attachment"):
            continue
        try:
            source_url = normalize_url(row.get("url", ""))
        except ValueError:
            # Zotero's free-text URL field can contain a local path or invalid URL.
            # Retain it in the original export; use DOI/a local reference ID here.
            source_url = ""
        csl = {"id": row["key"], "type": CSL_TYPES.get(row.get("itemType"), "article"),
               "title": row.get("title") or row.get("caseName") or row.get("nameOfAct") or row.get("subject") or f"Untitled Zotero item {row['key']}", "URL": source_url, "DOI": row.get("DOI", ""),
               "container-title": row.get("publicationTitle") or row.get("bookTitle") or row.get("websiteTitle", ""),
               "publisher": row.get("publisher", ""), "abstract": row.get("abstractNote", ""),
               "issued": issued(row.get("date", "")), "author": []}
        library = wrappers.get(row["key"], {}).get("library", {})
        if library.get("id") and library.get("type") in ("user", "group"):
            csl["id"] = f"https://www.zotero.org/{library['type']}s/{library['id']}/items/{row['key']}"
        for field, source in (("volume", "volume"), ("issue", "issue"), ("page", "pages"), ("ISBN", "ISBN"), ("ISSN", "ISSN"), ("publisher-place", "place"), ("language", "language")):
            if row.get(source):
                csl[field] = row[source]
        for person in row.get("creators", []):
            if person.get("creatorType") != "author":
                continue
            csl["author"].append({"literal": person["name"]} if person.get("name") else {"given": person.get("firstName", ""), "family": person.get("lastName", "")})
        items.append({"csl": csl, "notes": notes.get(row["key"], []), "tags": [t["tag"] for t in row.get("tags", []) if t.get("tag")]})
    if not items:
        return {"created": 0, "updated": 0, "unchanged": 0, "references": 0}
    # Zotero 7 has no server ID: use the canonical per-item library link as a partition.
    library = server_id or next((row.get("links", {}).get("self", {}).get("href", "").split("/items/")[0] for row in rows if row.get("links", {}).get("self")), "local")
    return import_items(vault, items, namespace=namespace + ":" + library,
                        original={"format": namespace, "server_id": server_id, "items": rows})


def import_desktop(vault, *, get=local_get):
    """Read the personal desktop library and child notes; never write to Zotero."""
    return read_library(vault, get=get)


def connection_settings(vault):
    return {"connection": {"library_type": "users", "library_id": ""} | vault.config().get("zotero", {}),
            "api_key": {"configured": bool(vault.secret("ZOTERO_API_KEY")), "editable": not bool(os.environ.get("ZOTERO_API_KEY"))}}


def validate_connection(library_type, library_id):
    if library_type not in ("users", "groups") or not isinstance(library_id, str) or not re.fullmatch(r"[1-9]\d{0,15}", library_id):
        raise ValueError("Choose a personal or group library and enter its numeric Zotero library ID")


def save_connection(vault, values):
    if not isinstance(values, dict) or set(values) - {"library_type", "library_id", "api_key"}:
        raise ValueError("Unsupported Zotero connection setting")
    library_type, library_id = values.get("library_type"), values.get("library_id")
    validate_connection(library_type, library_id)
    # Reuse the existing owner-only, write-only secret store. Never copy keys into config.
    from .maintenance import save_settings
    if values.get("api_key") != "" and "api_key" in values:
        save_settings(vault, {}, {"ZOTERO_API_KEY": values["api_key"]})
    vault.configure(zotero={"library_type": library_type, "library_id": library_id})
    return connection_settings(vault)


def web_get(path, api_key, *, sleep=time.sleep):
    headers = {"Zotero-API-Version": "3", "Accept": "application/json", "Zotero-API-Key": api_key,
               "User-Agent": "sidenote Zotero integration"}
    # Fixed official HTTPS API only. Refuse redirects rather than forward credentials.
    opener = build_opener(HTTPSHandler(context=tls_context()), NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(Request("https://api.zotero.org/" + path, headers=headers), timeout=25) as response:
                body = response.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise ValueError("Zotero response exceeded 10 MB")
                backoff = response.headers.get("Backoff")
                if backoff:
                    delay = int(backoff)
                    if delay > 60:
                        raise ValueError("Zotero requested a long backoff; wait a few minutes and retry")
                    sleep(max(0, delay))
                return json.loads(body), response.headers
        except HTTPError as error:
            error.close()
            if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                try:
                    delay = max(1, int(error.headers.get("Retry-After", "2")))
                except ValueError:
                    delay = 2 ** attempt
                if delay > 60:
                    raise ValueError("Zotero is rate limited; wait a few minutes and retry") from None
                sleep(delay)
                continue
            if error.code in (401, 403):
                raise ValueError("Zotero denied access. Check the API key and its read access to this library in Zotero Settings") from None
            raise ValueError(f"Zotero online API returned HTTP {error.code}; check the library ID and retry") from None
        except (URLError, TimeoutError, OSError):
            raise ValueError("Could not reach Zotero online; check your connection and retry") from None


def import_online(vault, *, get=web_get):
    connection = connection_settings(vault)["connection"]
    validate_connection(connection["library_type"], connection["library_id"])
    key = vault.secret("ZOTERO_API_KEY")
    if not key:
        raise ValueError("Save a Zotero API key in Settings → Zotero first")
    if len(key) > 4096 or any(c.isspace() for c in key) or not key.isprintable():
        raise ValueError("Invalid saved Zotero API key")
    prefix = connection["library_type"] + "/" + connection["library_id"]
    def fetch(path, server_id):
        return get(path, key)
    return read_library(vault, get=fetch, prefix=prefix, namespace="zotero-online:" + prefix)


def reference_details(record):
    sources = record.get("sources", {}).values()
    return {"notes": list(dict.fromkeys(note for source in sources for note in source.get("notes", []))),
            "tags": sorted(set(tag for source in record.get("sources", {}).values() for tag in source.get("tags", [])))}


def export_library(vault, *, format="ris", include_notes=False, document_ids=None):
    if format not in ("ris", "csl-json"):
        raise ValueError("Choose ris or csl-json")
    if not isinstance(include_notes, bool):
        raise ValueError("include_notes must be true or false")
    docs = vault.documents()
    if document_ids is not None:
        if not isinstance(document_ids, list) or any(not isinstance(key, str) or key not in docs for key in document_ids):
            raise ValueError("Export document IDs must refer to visible library items")
        docs = {key: docs[key] for key in dict.fromkeys(document_ids)}
    references = vault.records("references")
    result, ris = [], []
    for key, doc in sorted(docs.items(), key=lambda pair: pair[1]["title"].casefold()):
        meta = doc["metadata"]
        sources = list(references.get(key, {}).get("sources", {}).values())
        csl = copy.deepcopy(sources[-1]["csl"]) if sources else {"type": "article-journal" if meta.get("journal") else "webpage"}
        for field in ("note", "annote"):
            csl.pop(field, None)
        csl.update(id="urn:sidenote:" + key, title=doc["title"])
        csl.pop("URL", None)
        if doc["url"].startswith(("https://", "http://")):
            csl["URL"] = doc["url"]
        for source, target in FIELDS.items():
            if source != "title":
                csl.pop(source, None)
                if meta.get(target):
                    csl[source] = meta[target]
        # Preserve structured names unless the user has corrected them locally.
        if names(csl.get("author", [])) != meta.get("authors", []):
            csl["author"] = [{"literal": name} for name in meta.get("authors", [])]
        if date_text(csl.get("issued")) != meta.get("published", ""):
            csl["issued"] = issued(meta.get("published", ""))
        result.append(csl)
        if format == "csl-json":
            continue
        line = lambda tag, value: ris.append(f"{tag}  - " + re.sub(r"[\r\n\x00]+", " ", str(value))) if value else None
        line("TY", next((tag for tag, value in RIS_TYPES.items() if value == csl["type"]), "GEN"))
        line("ID", csl["id"])
        line("TI", doc["title"])
        for person in csl.get("author", []):
            line("AU", person.get("literal") or ", ".join(filter(None, (person.get("family"), person.get("given")))))
        for tag, field in (("UR", "URL"), ("DO", "DOI"), ("T2", "container-title"), ("PB", "publisher"), ("AB", "abstract"), ("VL", "volume"), ("IS", "issue"), ("SP", "page"), ("SN", "ISBN"), ("LA", "language"), ("CY", "publisher-place")):
            line(tag, csl.get(field))
        line("PY", date_text(csl.get("issued")))
        for tag in doc["tags"]:
            line("KW", tag)
        if include_notes:
            notes = list(doc.get("reference_notes", []))
            for annotation in doc["annotations"]:
                text = "\n\n".join(filter(None, (quote_text(annotation), annotation.get("text"))))
                if text:
                    notes.append(text)
            if vault.personal_notes(key).strip():
                notes.append(vault.personal_notes(key).strip())
            for note in notes:
                # Zotero treats N1 as HTML. Escape all imported/user text first.
                line("N1", "<p>" + escape(note).replace("\n", "<br/>") + "</p>")
        ris.extend(["ER  -", ""])
    return {"filename": "sidenote.ris" if format == "ris" else "sidenote.csl.json",
            "content_type": "application/x-research-info-systems" if format == "ris" else "application/json",
            "content": "\n".join(ris) if format == "ris" else json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            "references": len(result)}
