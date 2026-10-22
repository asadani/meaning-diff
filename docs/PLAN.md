# Meaning Diff v0.1 implementation plan

## User job and CLI

Compare two UTF-8 prose/Markdown files and locate potentially consequential changes with inspectable literal evidence.

```sh
python -m meaning_diff compare fixtures/before.md fixtures/after.md --format json --out changes.json
python -m meaning_diff compare fixtures/before.md fixtures/after.md --format markdown --out changes.md
```

Optional `--threshold` is a float in [0,1], default 0.45, used only for replacement-block sentence alignment. Return 1 when review signals exist, 0 when none, 2 for invalid input. A purely stylistic edit can appear in `changed_pairs` without producing a signal. No file mutation.

## Sentence records and deterministic alignment

Parse prose into paragraph blocks separated by blank lines or Markdown headings; ignore fenced code blocks. Split prose sentences at `.`, `?`, or `!` followed by whitespace or paragraph end. Preserve absolute character offsets so each sentence has `{id,text,line_start,line_end}`. Decimal dots without following whitespace do not split. Headings are context labels rather than sentences. Clearly document that abbreviations, tables, and unusual Markdown may segment imperfectly; no language parser is claimed. Use English v0.1 signal vocabulary.

Normalize alignment text by casefolding and collapsing whitespace. Use `difflib.SequenceMatcher(autojunk=False)` over sentence strings for exact-match anchors. Within each replace block, score all old/new pairs using string SequenceMatcher ratio; greedily pair descending ratio at or above threshold, tie-breaking old index then new index, each sentence used once. Unmatched old/new sentences are dropped/added. Do not match across other opcode blocks. Identical normalized sentences produce no changes. Retain scores and alignment method in reports so mistaken pairings can be reviewed. Reordered sentences may appear as added/dropped; do not claim move detection.

## Signals

For each changed paired sentence, extract and compare:

- `number_changed`: ordered numeric tokens including optional decimal and adjacent `%` (and nearby following word as context in evidence). Flag when numeric token lists differ; e.g. 24 → 48. Do not perform unit conversion or imply quantities are equivalent.
- `modal_changed`: case-insensitive whole-word `must`, `shall`, `should`, `may`, `can`, `will`, `required`, `optional`. Report old/new token lists, not an invented universal obligation ranking.
- `negation_changed`: whole-word `not`, `never`, `no`, `cannot` and contractions ending `n't`. Report literal old/new token lists.
- `condition_changed`: compare normalized suffixes beginning at the first whole phrase `if`, `unless`, `except`, `only when`, or `until`. A removed marker/suffix or changed condition suffix triggers the signal. This is a phrase heuristic, not a condition parser.
- `sentence_dropped` for an unmatched old sentence; `sentence_added` for unmatched new sentence. Include whether it contains any of the four token families so reviewers can prioritize it.

Numbers/modal/negation changes receive `priority: high`; condition and dropped sentences medium; added sentences low unless they contain a numeric/modal/negation token, then medium. This priority is a fixed review-order heuristic, not severity, probability, or correctness. Multiple signals can refer to the same pair. Literal list comparisons preserve duplicate tokens so disappearing repeated constraints remain visible.

## Report and API

JSON: `{schema_version:1,method:{alignment,threshold,language:"en",limitations:[...]},before:{path,sha256},after:{path,sha256},changed_pairs:[{id,before:sentence|null,after:sentence|null,similarity:number|null}],signals:[{id,pair_id,kind,priority,before_tokens?,after_tokens?,message}]}`. Pair IDs derive from old/new indexes plus text, signal IDs from pair/kind; ordering follows old position then new position. Markdown shows summary counts, limitations, and each pair with source lines, literal before/after, alignment score, and signals. Never omit unpaired sentences from the JSON.

- `split_sentences(text: str) -> list[dict]`
- `align_sentences(before: list[dict], after: list[dict], threshold: float = 0.45) -> list[dict]`
- `detect_signals(pair: dict) -> list[dict]`
- `compare_texts(before: str, after: str, threshold: float = 0.45) -> dict`
- `render_markdown(report: dict) -> str`

CLI adds file paths and original-byte hashes. Pure API must not read the filesystem. Empty documents are valid; empty versus populated means all added/dropped. Case/whitespace-only changes are ignored by design and disclosed.

## Meaningful fixture and acceptance tests

1. Before/after sharing specs include negation removal plus modal change, 24→48 hours, changed `unless` condition, an entirely dropped obligation, an unchanged paragraph, and a harmless paraphrase. Tests assert located signals and actual token evidence, not just report existence.
2. Numeric decimals and percentages are retained correctly; number-free edits do not invent quantity changes. Whole-word signal detection avoids `cannotary`, `notebook`, and `mayor` false matches.
3. Exact sentence anchors prevent unchanged neighboring sentences from being paired to an edit. Duplicate sentences, an empty side, and unequal replacement block lengths have stable deterministic alignment and no duplicated use of a sentence.
4. Multi-line paragraphs map to correct inclusive lines; fenced code is ignored; headings remain context. Abbreviation limitations are documented, with deterministic behavior tested.
5. Threshold bounds and invalid UTF-8 yield exit 2; identical/case-whitespace-only files yield exit 0; meaningful fixture yields exit 1 with JSON and Markdown output.
6. Markdown with backticks or pipes cannot corrupt the report structure. Repeated identical runs produce identical reports.

## Non-goals and milestone

Required: source-located segmentation, deterministic alignment, five signal families plus additions, JSON/Markdown, useful tests. Deferred: semantic embeddings, entailment, automatic acceptance, translation, DOCX/PDF ingestion, AST-level policy comparison. No “no meaning changed” message; say “no configured heuristic signals detected.”

Build segmentation/alignment, then literal detectors, then the report and CLI. Done means a reviewer can inspect all consequential fixture edits and see why each was flagged, including the heuristic limits.

## Independent review refinement

The bounded condition vocabulary also includes `only after`, `only before`, `provided that`, and `as long as`. These cover the motivating approval-precondition example without claiming general logical parsing. Regression tests distinguish a removed condition from an unchanged exact condition.
