from __future__ import annotations

import json
import unittest
from pathlib import Path

from meaning_diff import align_sentences, compare_texts, detect_signals, render_markdown, split_sentences


ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = (ROOT / "fixtures" / "sharing-before.md").read_text(encoding="utf-8")
        cls.after = (ROOT / "fixtures" / "sharing-after.md").read_text(encoding="utf-8")

    def test_fixture_finds_literal_changes_and_preserves_unpaired_sentences(self):
        report = compare_texts(self.before, self.after)
        kinds = [signal["kind"] for signal in report["signals"]]
        self.assertIn("number_changed", kinds)
        self.assertIn("modal_changed", kinds)
        self.assertIn("negation_changed", kinds)
        self.assertIn("condition_changed", kinds)
        self.assertIn("sentence_dropped", kinds)
        self.assertIn("sentence_added", kinds)
        number = next(s for s in report["signals"] if s["kind"] == "number_changed")
        self.assertEqual(number["before_tokens"], ["24 hours"])
        self.assertEqual(number["after_tokens"], ["48 hours"])
        change = next(p for p in report["changed_pairs"] if p["before"] and p["before"]["text"].startswith("Guests"))
        self.assertEqual(change["before"]["line_start"], 3)
        self.assertEqual(change["after"]["line_start"], 3)
        self.assertLessEqual(change["similarity"], 1)
        dropped = next(p for p in report["changed_pairs"] if p["after"] is None)
        self.assertIn("must", dropped["before"]["text"])
        self.assertTrue(any(p["before"] and p["after"] and p["before"]["text"].startswith("A reviewer")
                            for p in report["changed_pairs"]))
        self.assertTrue(any(p["after"] and p["before"] is None for p in report["changed_pairs"]))
        unchanged = "The retention setting is optional for guest links."
        self.assertFalse(any(p["before"] and p["before"]["text"] == unchanged for p in report["changed_pairs"]))
        self.assertIn("No signal means only", " ".join(report["method"]["limitations"]))

    def test_paragraph_lines_headings_and_fenced_code(self):
        text = "# Access rules\n\nGuests may wait.\nFor 2.5% of accounts, no retry occurs.\n\n```python\nGuests must retry.\n```\n\n## Audit\nLogs remain."
        sentences = split_sentences(text)
        self.assertEqual([s["text"] for s in sentences], ["Guests may wait.", "For 2.5% of accounts, no retry occurs.", "Logs remain."])
        self.assertEqual((sentences[0]["line_start"], sentences[1]["line_start"], sentences[1]["line_end"]), (3, 4, 4))
        self.assertEqual(sentences[0]["context"], "Access rules")
        self.assertEqual(sentences[-1]["context"], "Access rules > Audit")

    def test_numeric_decimal_percentage_and_no_quantity_false_positive(self):
        old, new = split_sentences("Rate is 2.5% for 24 hours."), split_sentences("Rate is 2.5% for 48 hours.")
        pair = align_sentences(old, new)[0]
        signals = detect_signals(pair)
        numeric = [s for s in signals if s["kind"] == "number_changed"]
        self.assertEqual(numeric[0]["before_tokens"], ["2.5%", "24 hours"])
        self.assertEqual(numeric[0]["after_tokens"], ["2.5%", "48 hours"])
        self.assertEqual([s["kind"] for s in compare_texts("A route exists.", "A route is available.")["signals"]], [])

    def test_whole_word_modal_and_negation_tokens(self):
        report = compare_texts("The value is not in the notebook; a mayor may review.",
                               "The value is in the notebook; a mayor can review.")
        kinds = [s["kind"] for s in report["signals"]]
        self.assertEqual(kinds, ["modal_changed", "negation_changed"] if kinds[0] == "modal_changed" else ["negation_changed", "modal_changed"])
        modal = next(s for s in report["signals"] if s["kind"] == "modal_changed")
        self.assertEqual(modal["before_tokens"], ["may"])
        self.assertEqual(modal["after_tokens"], ["can"])
        negation = next(s for s in report["signals"] if s["kind"] == "negation_changed")
        self.assertEqual(negation["before_tokens"], ["not"])
        self.assertEqual(negation["after_tokens"], [])
        false_positive = compare_texts("A cannotary waits in the notebook.", "A cannotary rests in the notebook.")
        self.assertEqual(false_positive["signals"], [])

    def test_decimal_abbreviation_limitation_is_stable(self):
        sentences = split_sentences("Dr. Lee waits. Version 2.5 works.")
        self.assertEqual([s["text"] for s in sentences], ["Dr.", "Lee waits.", "Version 2.5 works."])

    def test_case_whitespace_only_changes_are_ignored(self):
        report = compare_texts("Guests MUST wait.\n", "  guests must wait.  ")
        self.assertEqual(report["changed_pairs"], [])
        self.assertEqual(report["signals"], [])

    def test_only_after_condition_removal_is_flagged(self):
        report = compare_texts("The content is published only after approval.", "The content is published.")
        self.assertEqual([signal["kind"] for signal in report["signals"]], ["condition_changed"])
        self.assertEqual(report["signals"][0]["before_tokens"], ["only after approval."])
        self.assertEqual(report["signals"][0]["after_tokens"], [])
        exact = compare_texts("The content is published only after approval.", "The content is published only after approval.")
        self.assertEqual(exact["signals"], [])

    def test_exact_anchors_duplicate_sentences_and_alignment_are_deterministic(self):
        before = split_sentences("Same sentence. Same sentence. Value is 24 hours. Final sentence.")
        after = split_sentences("Same sentence. Same sentence. Value is 48 hours. Final sentence.")
        first = align_sentences(before, after)
        second = align_sentences(before, after)
        self.assertEqual(first, second)
        changed = compare_texts("Same sentence. Same sentence. Value is 24 hours. Final sentence.",
                                "Same sentence. Same sentence. Value is 48 hours. Final sentence.")
        self.assertEqual(len([p for p in changed["changed_pairs"] if p["before"] and p["after"]]), 1)
        self.assertEqual(changed["signals"][0]["kind"], "number_changed")
        self.assertEqual(len({p["before"]["id"] for p in first if p["before"]}), len([p for p in first if p["before"]]))
        self.assertEqual(len({p["after"]["id"] for p in first if p["after"]}), len([p for p in first if p["after"]]))

    def test_empty_documents_and_unmatched_sentence_priority(self):
        added = compare_texts("", "A new sentence appears.")
        self.assertEqual(added["signals"][0]["kind"], "sentence_added")
        self.assertEqual(added["signals"][0]["priority"], "low")
        urgent = compare_texts("", "A service must wait 24 hours.")
        self.assertEqual(urgent["signals"][0]["priority"], "medium")
        dropped = compare_texts("Guests must never reshare.", "")
        self.assertEqual(dropped["signals"][0]["kind"], "sentence_dropped")
        self.assertEqual(dropped["signals"][0]["priority"], "medium")

    def test_threshold_bounds_and_no_duplicate_usage(self):
        for threshold in (-.01, 1.01, True):
            with self.assertRaises(ValueError):
                align_sentences([], [], threshold)
        before = split_sentences("Old request. Another old request. Unchanged.")
        after = split_sentences("New demand. Unchanged.")
        aligned = align_sentences(before, after, .9)
        self.assertEqual(sum(p["before"] is None for p in aligned), 1)
        self.assertEqual(sum(p["after"] is None for p in aligned), 2)

    def test_markdown_report_keeps_pipes_and_backticks_inside_fences(self):
        report = compare_texts("Policy | must remain ```visible```.", "Policy | should remain ```visible```.")
        markdown = render_markdown(report)
        self.assertIn("````text\nPolicy | must remain ```visible```.\n````", markdown)
        self.assertIn("`modal_changed`", markdown)
        self.assertIn("Before: `['must']`; after: `['should']`", markdown)
        self.assertIn("No semantic equivalence judgment", markdown)
        self.assertEqual(markdown, render_markdown(report))


if __name__ == "__main__":
    unittest.main()
