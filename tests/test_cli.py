from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.before = self.work / "before.md"
        self.after = self.work / "after.md"
        self.before.write_text("Guests must not reshare within 24 hours unless approved.\n", encoding="utf-8")
        self.after.write_text("Guests may reshare within 48 hours.\n", encoding="utf-8")
        self.output = self.work / "report.json"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "meaning_diff", *map(str, args)], cwd=REPO,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_json_and_markdown_cli_outputs_and_exit_codes(self):
        self.cli("compare", self.before, self.after, "--format", "json", "--out", self.output, expected=1)
        report = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(report["before"]["sha256"], hashlib.sha256(self.before.read_bytes()).hexdigest())
        self.assertEqual(report["after"]["sha256"], hashlib.sha256(self.after.read_bytes()).hexdigest())
        self.assertEqual([s["kind"] for s in report["signals"]], ["number_changed", "modal_changed", "negation_changed", "condition_changed"])
        markdown = self.work / "report.md"
        self.cli("compare", self.before, self.after, "--format", "markdown", "--out", markdown, expected=1)
        content = markdown.read_text(encoding="utf-8")
        self.assertIn("number_changed", content)
        self.assertIn("lines 1–1", content)
        self.assertIn("not a condition parser", content)

    def test_identical_and_empty_comparisons_exit_zero(self):
        copy = self.work / "same.md"
        shutil.copyfile(self.before, copy)
        report = self.cli("compare", self.before, copy, "--format", "json")
        self.assertEqual(report.returncode, 0)
        value = json.loads(report.stdout)
        self.assertEqual(value["signals"], [])
        self.assertEqual(value["changed_pairs"], [])
        empty = self.work / "empty.md"
        empty.write_text("", encoding="utf-8")
        self.cli("compare", empty, empty, "--out", self.output)

    def test_invalid_utf8_and_threshold_return_two_without_report(self):
        self.before.write_bytes(b"valid\xff")
        self.cli("compare", self.before, self.after, "--out", self.output, expected=2)
        self.assertFalse(self.output.exists())
        self.before.write_text("valid", encoding="utf-8")
        self.cli("compare", self.before, self.after, "--threshold", "1.01", "--out", self.output, expected=2)
        self.assertFalse(self.output.exists())

    def test_same_inputs_repeated_output_is_byte_deterministic(self):
        self.cli("compare", self.before, self.after, "--out", self.output, expected=1)
        first = self.output.read_bytes()
        self.cli("compare", self.before, self.after, "--out", self.output, expected=1)
        self.assertEqual(self.output.read_bytes(), first)

    def test_cli_help_and_version(self):
        help_result = subprocess.run([sys.executable, "-m", "meaning_diff", "--help"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn("compare", help_result.stdout)
        version = subprocess.run([sys.executable, "-m", "meaning_diff", "--version"], cwd=REPO, text=True, capture_output=True)
        self.assertEqual(version.stdout.strip(), "meaning-diff 0.1.0")


if __name__ == "__main__":
    unittest.main()
