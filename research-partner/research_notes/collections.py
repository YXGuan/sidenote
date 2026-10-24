"""Read-only, local NLP collections. Never rewrite explicit reactions or groups."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import html
import re

AUTO_IDS = ("liked-auto", "questions-auto", "visit-often")
AUTO_NAMES = ("Liked (Auto)", "Questions (Auto)", "Visit Often")
POSITIVE_THRESHOLD = 0.35
FREQUENT_VISITS = 3
VISIT_DAYS = 30


@lru_cache(maxsize=1)
def tools():
    try:
        from nltk.tokenize import TreebankWordTokenizer
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    except ImportError:
        raise RuntimeError("Install local NLP dependencies: python3 -m pip install --target research-partner/.local-tools/python -r research-partner/requirements.txt") from None
    return TreebankWordTokenizer(), SentimentIntensityAnalyzer()


def plain_text(text, *, reader=False):
    text = html.unescape(text or "")
    text = re.sub(r"```.*?```|~~~.*?~~~", " ", text, flags=re.S)
    if reader:
        text = re.sub(r"(?m)^\s*>.*$", " ", text)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+|<[^>]*>", " ", text)
    return text.strip()


def is_question(sentence):
    tokens = [t.casefold() for t in tools()[0].tokenize(sentence) if any(c.isalpha() for c in t)]
    if not tokens:
        return False
    if "?" in sentence or "？" in sentence:
        return True
    auxiliary = {"am", "is", "are", "was", "were", "do", "does", "did", "can", "could", "should", "would", "will", "have", "has", "had", "may", "might", "must"}
    wh = {"what", "why", "when", "where", "who", "whom", "whose", "which", "how"}
    if len(tokens) >= 3 and tokens[0] in wh:
        return tokens[1] in auxiliary or (tokens[0] == "how" and tokens[1] in {"many", "much", "long", "often", "far", "to"})
    subjects = {"i", "you", "we", "they", "it", "he", "she", "this", "that", "these", "those", "there", "the", "a", "an"}
    if len(tokens) >= 3 and tokens[0] in auxiliary and tokens[1] in subjects:
        return True
    return bool(re.search(r"\b(?:i wonder|wondering)\s+(?:if|whether|how|why|what)\b", sentence, re.I))


@lru_cache(maxsize=8192)
def text_signals(text, reader=False):
    text = plain_text(text, reader=reader)
    # Bounded, deterministic splitting; Treebank tokenization needs no downloaded corpus.
    sentences = [s.strip() for s in re.split(r"(?<=[.!?？])\s+|\n+", text) if s.strip()]
    questions = [s for s in sentences if is_question(s)]
    statements = " ".join(s for s in sentences if s not in questions)
    score = tools()[1].polarity_scores(statements)["compound"] if reader and statements else 0
    return {"has_question": bool(questions), "sentiment": score}


def collection_signals(doc, *, today=None):
    from .store import quote_text
    positive = negative = questions = 0
    for annotation in doc["annotations"]:
        comment = text_signals(annotation.get("text", ""), True)
        quoted = text_signals(quote_text(annotation))
        questions += int(comment["has_question"] or quoted["has_question"])
        state = doc.get("annotation_states", {}).get(annotation["id"], {})
        if state.get("reaction") != "dislike":
            positive += int(comment["sentiment"] >= POSITIVE_THRESHOLD)
        negative += int(comment["sentiment"] <= -POSITIVE_THRESHOLD)
    today = today or datetime.now(timezone.utc).date()
    start = (today - timedelta(days=VISIT_DAYS - 1)).isoformat()
    end = today.isoformat()
    visits = sum(value for day, value in doc.get("activity", {}).get("visits_by_day", {}).items() if start <= day <= end)
    signals = {"positive_comments": positive, "negative_comments": negative, "question_annotations": questions, "visits_30_days": visits}
    collections = []
    if positive > negative and doc.get("reaction") not in ("bad", "hate", "dislike"):
        collections.append("liked-auto")
    if questions:
        collections.append("questions-auto")
    if visits >= FREQUENT_VISITS:
        collections.append("visit-often")
    return {"automatic_collections": collections, "collection_signals": signals}
