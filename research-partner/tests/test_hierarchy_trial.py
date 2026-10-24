"""The exploratory classifier must reject ungrounded or uncontrolled results."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments"))
import hierarchy_trial as trial


class HierarchyTrialTests(unittest.TestCase):
    def setUp(self):
        self.pages, expected = trial.samples(synthetic_only=True)
        self.result = {"pages": [{
            "document_id": page["document_id"],
            "primary": {"path_id": expected[page["document_id"]],
                        "evidence_field": "none" if expected[page["document_id"]] == "unknown" else "title",
                        "evidence_quote": "" if expected[page["document_id"]] == "unknown" else page["title"]},
            "secondary": [],
        } for page in self.pages]}

    def test_public_parser_handles_nested_markup_and_abstract_boundary(self):
        parser = trial.ArxivAbstract()
        parser.feed('<meta name="citation_title" content="A paper"><blockquote class="abstract mathjax"><span>Abstract:</span> Social <i>behavior</i>.</blockquote><p>Unrelated text</p>')
        self.assertEqual(parser.title, "A paper")
        self.assertEqual("".join(parser.abstract), "Abstract: Social behavior.")

    def test_valid_controls_and_abstention(self):
        self.assertEqual(set(trial.validate(self.result, self.pages)), {page["document_id"] for page in self.pages})

    def test_fabricated_quotes_and_unlisted_paths_are_rejected(self):
        for field, value in [("evidence_quote", "A statement absent from the supplied evidence"),
                             ("path_id", "invented-label")]:
            with self.subTest(field=field):
                result = copy.deepcopy(self.result)
                result["pages"][0]["primary"][field] = value
                with self.assertRaises(ValueError):
                    trial.validate(result, self.pages)

    def test_missing_duplicate_and_unknown_with_secondary_are_rejected(self):
        missing = {"pages": self.result["pages"][:-1]}
        duplicate = {"pages": self.result["pages"] + [self.result["pages"][0]]}
        ambiguous = copy.deepcopy(self.result)
        ambiguous["pages"][-1]["secondary"] = [copy.deepcopy(ambiguous["pages"][0]["primary"])]
        for result in (missing, duplicate, ambiguous):
            with self.assertRaises(ValueError):
                trial.validate(result, self.pages)


if __name__ == "__main__":
    unittest.main()
