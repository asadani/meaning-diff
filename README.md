<p align="center">
  <img src="assets/logo.svg" alt="Meaning Diff — See what the rewrite changed" width="400" height="160">
</p>

Meaning Diff helps a reviewer find prose edits that may deserve a closer look: changed quantities, modal or requirement words, negations, conditions, and dropped or added sentences. It places the literal before and after text beside source line numbers. The output is a set of heuristic review signals; it never decides whether meaning was preserved.

## Quickstart

Requires Python 3.11 or newer. Runtime uses only the Python standard library. From this repository root:

```sh
out_dir="$(mktemp -d)"
python -m meaning_diff compare fixtures/sharing-before.md fixtures/sharing-after.md --format json --out "$out_dir/changes.json"
python -m meaning_diff compare fixtures/sharing-before.md fixtures/sharing-after.md --format markdown --out "$out_dir/changes.md"
```

Both commands exit `1` because the fixture contains review signals. The JSON includes five changed sentence pairs and seven signals: a changed `24 hours` to `48 hours`, `must` to `may`, removed `not`, a changed `unless` suffix, a `should` to `must` change, one dropped sentence, and one added sentence. It also includes a harmless paraphrase pair with no signal. Exact unchanged sentences are omitted from the changed pairs, and fenced code is ignored.

The first Markdown section looks like this:

```markdown
# Meaning Diff review

**Heuristic review signals. No semantic equivalence judgment is made.**

- Changed sentence pairs: 5
- Review signals: 7
- Alignment threshold: 0.45
```

Inspect the literal evidence in the JSON (excerpt):

```json
{
  "kind": "number_changed",
  "priority": "high",
  "before_tokens": ["24 hours"],
  "after_tokens": ["48 hours"],
  "message": "Ordered numeric tokens differ; units are not converted or compared for equivalence."
}
```

## How comparison works

Meaning Diff splits UTF-8 prose into sentence records with inclusive source lines. Blank lines and Markdown headings end a paragraph; headings attach as context labels. Fenced code blocks are skipped. Decimal dots without following whitespace do not end a sentence. It uses normalized exact sentence matches as alignment anchors, then applies `difflib.SequenceMatcher` to each replacement block and greedily pairs candidates at or above the chosen threshold. Similarity scores and the alignment method remain in the report so a reviewer can inspect questionable pairs. Unmatched sentences stay in the output as additions or drops; moves are not inferred.

For paired sentences, English v0.1 compares ordered numeric tokens (including decimals, `%`, and nearby word context), whole-word modal and requirement terms, whole-word negation terms and contractions, and suffixes beginning with `if`, `unless`, `except`, `only when`, `only after`, `only before`, `provided that`, `as long as`, or `until`. Repeated tokens stay repeated. A signal's priority is a fixed review-order hint: numeric, modal, and negation changes are high; condition and dropped sentences medium; added sentences low unless a number, modal, or negation appears. Priority does not mean severity, likelihood, correctness, or a universal ranking of words such as “must” and “should.”

Use it when revising an operational spec, policy, requirement, or review document and you want a second pass over patterns a normal diff can bury. A reviewer should read the surrounding source and decide whether each flagged change is intentional and consequential.

## CLI and output

```sh
python -m meaning_diff compare BEFORE AFTER [--format json|markdown] [--threshold 0.45] [--out FILE]
```

`--threshold` must be within `[0, 1]` and affects only replacement-block sentence alignment. The default is `0.45`. Without `--out`, the report goes to stdout. JSON includes `schema_version`, alignment method and threshold, limitations, before/after input paths and original-byte SHA-256 hashes, changed pairs, and signals. See [the report schema](docs/report.schema.json).

Exit codes are `0` when no configured signals were detected, `1` when one or more signals were produced, and `2` for invalid input, unreadable files, malformed UTF-8, or invalid threshold. A changed pair can have no signal, so a stylistic edit can appear in the report while the command exits `0`. Expected file errors print a short message to stderr. `--help` and `--version` are available.

## Limitations

This is a literal pattern detector, not a language parser or semantic comparison engine. Abbreviations such as “Dr.” may split unexpectedly. Tables, lists, and unusual Markdown can segment imperfectly. A similarity match can pair unrelated replacement sentences; exact anchors do not permit matching across other alignment blocks. Reordered sentences can appear as additions and drops. Subtle paraphrases can be missed, and intended edits can still be flagged. Number matching does not convert units or judge whether quantities are equivalent. Condition suffixes are compared as normalized text, not parsed as logic. The signal list is English-only.

“No configured heuristic signals detected” means only that these patterns were not found. It does not mean that meaning is unchanged, that the document is correct, or that the edit is safe to accept. The tool does not approve changes, provide a severity estimate, or establish accuracy against a labeled corpus.

## Development

```sh
python -m unittest discover -s tests -v
```

The pure API (`split_sentences`, `align_sentences`, `detect_signals`, `compare_texts`, `render_markdown`) does not read files. The CLI alone reads source bytes and adds path and SHA-256 provenance.

See [verification coverage](docs/VERIFICATION.md) and [the design plan](docs/PLAN.md) for tested behavior and remaining limits.
