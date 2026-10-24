from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_notes.collections import collection_signals, text_signals
from research_notes.store import Vault
from research_notes.native import mirror_annotation
from research_notes.server import library_document, public_document


def document(comment="", quote=""):
    return {"reaction": None, "activity": {}, "annotation_states": {}, "annotations": [{"id": "note", "text": comment, "target": [{"selector": [{"type": "TextQuoteSelector", "exact": quote}]}]}]}


class CollectionTests(unittest.TestCase):
    def test_vader_handles_positive_negative_and_negated_comments(self):
        self.assertIn("liked-auto", collection_signals(document("I love this approach. Excellent and useful!"))["automatic_collections"])
        for text in ("I do not like this. It is terrible.", "I hate this approach.", "The study reports 120 participants.", "Is this a great approach?"):
            self.assertNotIn("liked-auto", collection_signals(document(text))["automatic_collections"], text)

    def test_highlights_and_markdown_quotes_are_not_reader_endorsements(self):
        for doc in (document(quote="This is wonderful and excellent!"), document("> This is wonderful and excellent!"), document("```python\nprint('excellent')\n```")):
            self.assertNotIn("liked-auto", collection_signals(doc)["automatic_collections"])

    def test_explicit_dislikes_override_inferred_liking(self):
        doc = document("I love this approach!")
        doc["reaction"] = "bad"
        self.assertNotIn("liked-auto", collection_signals(doc)["automatic_collections"])
        doc["reaction"] = None
        doc["annotation_states"]["note"] = {"reaction": "dislike"}
        self.assertNotIn("liked-auto", collection_signals(doc)["automatic_collections"])

    def test_questions_include_unpunctuated_questions_and_source_highlights(self):
        for comment in ("Why does this work", "Can we reproduce this result", "I wonder whether this scales", "This is interesting. What is the sample size?", "怎么解释？"):
            self.assertIn("questions-auto", collection_signals(document(comment))["automatic_collections"], comment)
        self.assertIn("questions-auto", collection_signals(document(quote="How can we test this?"))["automatic_collections"])
        self.assertFalse(text_signals("Read https://example.org/?q=why")["has_question"])
        self.assertFalse(text_signals("We can reproduce this result.")["has_question"])
        self.assertFalse(text_signals("What we know about this topic.")["has_question"])

    def test_question_and_positive_statement_can_belong_to_both(self):
        signals = collection_signals(document("I love this approach! Can we reproduce it?"))
        self.assertEqual(signals["automatic_collections"], ["liked-auto", "questions-auto"])

    def test_frequent_visits_roll_out_after_thirty_days_and_ignore_future_dates(self):
        doc = document()
        doc["activity"] = {"visit_count": 100, "visits_by_day": {"2026-09-22": 40, "2026-09-23": 1, "2026-10-22": 2, "2026-10-23": 50}}
        current = collection_signals(doc, today=date(2026, 10, 22))
        self.assertEqual(current["collection_signals"]["visits_30_days"], 3)
        self.assertIn("visit-often", current["automatic_collections"])
        self.assertNotIn("visit-often", collection_signals(doc, today=date(2026, 11, 22))["automatic_collections"])

    def test_existing_notes_update_without_persisting_or_changing_manual_groups(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Vault(temporary)
            vault.initialize("reader")
            vault.configure(auto_categorize=False)
            note = {"id": "note", "uri": "https://example.org/paper", "user": "acct:reader@hypothes.is", "created": "2026-10-01T00:00:00Z", "updated": "2026-10-01T00:00:00Z", "text": "I love this! Why does it work?", "target": [], "tags": []}
            doc = mirror_annotation(vault, note)
            self.assertEqual(doc["groups"], [])
            self.assertIn("liked-auto", doc["automatic_collections"])
            self.assertIn("questions-auto", library_document(vault, doc)["automatic_collections"])
            self.assertIn("questions-auto", public_document(vault, doc)["automatic_collections"])
            self.assertEqual(vault.groups(), ["For later", "Likes"])
            note.update(text="A neutral observation.", updated="2026-10-02T00:00:00Z")
            changed = mirror_annotation(vault, note)
            self.assertEqual(changed["automatic_collections"], [])
            self.assertEqual(changed["reaction"], None)

    def test_browser_visits_never_save_unknown_pages_and_coalesce_with_sidebar_visits(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Vault(temporary)
            vault.initialize("reader")
            vault.configure(auto_categorize=False)
            self.assertFalse(vault.visit_saved_page("https://example.org/unknown"))
            self.assertFalse(vault.records("activity"))
            with patch("research_notes.store.now", return_value="2026-10-22T10:00:00Z"):
                doc = vault.capture("https://example.org/saved", {"title": "Saved"}, visit=True)
                self.assertTrue(vault.visit_saved_page(doc["url"] + "#fragment"))
            self.assertEqual(vault.documents()[doc["id"]]["activity"]["visit_count"], 1)
            with patch("research_notes.store.now", return_value="2026-10-22T10:06:00Z"):
                vault.visit_saved_page(doc["url"])
            changed = vault.documents()[doc["id"]]
            self.assertEqual(changed["activity"]["visit_count"], 2)
            self.assertEqual(changed["updated_at"], doc["updated_at"])
            self.assertEqual(vault.saved_urls(), [doc["url"]])

    def test_automatic_names_cannot_be_created_as_manual_collections(self):
        with tempfile.TemporaryDirectory() as temporary:
            vault = Vault(temporary)
            vault.initialize("reader")
            with self.assertRaisesRegex(ValueError, "automatic collection"):
                vault.create_group("Liked (Auto)")
