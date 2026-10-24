"""Small, offline baseline. These are evidence-based rules, not model predictions.

No imports from a model hub, downloads, subprocesses, or network clients. Unknown
is intentional: a URL or a generic word such as "model" is not enough evidence.
"""
import json
import re
from urllib.parse import urlsplit

from pathlib import Path

RULES_VERSION = 2
TAXONOMY = json.loads(Path(__file__).with_name("taxonomy.json").read_text())
TOPICS = {name: tuple(item["terms"]) for name, item in TAXONOMY["topics"].items()}
SUBTOPICS = {(topic, name): tuple(terms) for topic, item in TAXONOMY["topics"].items() for name, terms in item["subtopics"].items()}


def matches(text, phrase):
    return bool(re.search(r"(?<!\w)" + re.escape(phrase.replace("-", " ")) + r"(?!\w)", text, re.IGNORECASE))


def link_type(page):
    parsed = urlsplit(page.get("url", ""))
    host, path = (parsed.hostname or "").lower(), parsed.path.lower()
    title = str(page.get("title", "")).lower()
    metadata = page.get("metadata", {})
    def domain(*names):
        return any(host == name or host.endswith("." + name) for name in names)
    if domain("youtube.com", "youtu.be", "vimeo.com"):
        return "video"
    if domain("podcasts.apple.com", "podcasts.google.com") or "/podcast" in path:
        return "podcast"
    if domain("books.google.com", "goodreads.com") or matches(title, "book review"):
        return "book"
    if host.startswith("docs.") or any(word in path for word in ("/docs/", "/documentation/")):
        return "documentation"
    if metadata.get("journal") or metadata.get("doi") or domain("arxiv.org", "biorxiv.org", "medrxiv.org", "pubmed.ncbi.nlm.nih.gov", "pmc.ncbi.nlm.nih.gov", "openreview.net", "doi.org", "aclanthology.org", "papers.ssrn.com", "semanticscholar.org", "dl.acm.org", "ieeexplore.ieee.org", "nature.com", "science.org", "sciencedirect.com", "link.springer.com", "onlinelibrary.wiley.com", "jmlr.org", "proceedings.mlr.press", "psyarxiv.com", "osf.io"):
        return "paper"
    if domain("reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "theguardian.com", "nytimes.com", "cbc.ca"):
        return "news"
    if domain("medium.com", "substack.com", "wordpress.com", "blogspot.com") or host.startswith("blog.") or "/blog/" in path:
        return "blog"
    return "unknown"


def local_classify(pages, taxonomy=()):
    """Classify in process. Scores are deliberately not represented as probabilities."""
    result = []
    for page in pages:
        metadata = page.get("metadata", {})
        # URLs, author names, journal names and existing tags must not label themselves.
        content = json.dumps({"title": page.get("title", ""), "abstract": metadata.get("abstract", ""), "description": metadata.get("description", ""), "scholarly_topics": metadata.get("scholarly_topics", []), "notes": page.get("page_notes", []), "personal": page.get("personal_notes", "")}, ensure_ascii=False).lower()
        content = content.replace("-", " ")
        kind = link_type(page)
        title = page.get("title", "").replace("-", " ").lower()
        topics = []
        for name, phrases in TOPICS.items():
            hits = [phrase for phrase in phrases if matches(content, phrase)]
            # A generic incidental word in a long abstract does not establish a subject.
            if any(matches(title, phrase) for phrase in phrases) or len(hits) >= 2:
                topics.append(name)
        subtopics = []
        for (topic, name), phrases in SUBTOPICS.items():
            if any(matches(content, phrase) for phrase in phrases):
                if topic not in topics:
                    topics.append(topic)
                subtopics.append({"topic": topic, "name": name})
        topics = topics[:8]
        subtopics = [item for item in subtopics if item["topic"] in topics][:12]
        tags = list(dict.fromkeys([item["name"] for item in subtopics] + topics))[:8]
        result.append({"document_id": page["document_id"], "tags": tags, "link_type": kind,
                       "topics": topics, "subtopics": subtopics})
    return {"pages": result}
