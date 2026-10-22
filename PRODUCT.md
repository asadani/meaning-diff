# Meaning Diff

Meaning Diff helps a reviewer notice prose edits that deserve a closer look: a changed limit, a weaker obligation, a removed negation, a dropped condition, or a deleted sentence.

The example compares two versions of a document-sharing specification. “Guests must not reshare” becomes “Guests may reshare”; “within 24 hours” becomes “within 48 hours”; and an approval condition disappears. The report places old and new sentences side by side with source locations and names the literal signals that changed.

The v0.1 CLI aligns sentences using lexical similarity and produces JSON or Markdown. It calls the output heuristic review signals, never a semantic equivalence judgment. Subtle paraphrases can be missed, unrelated sentences can align, and a flagged edit can be intentional.

Its job differs from a text diff by prioritizing a small set of inspectable change patterns. It does not decide whether the revision is correct, resolve contradictions, or approve a document.

Validate with realistic specification revisions containing consequential and harmless edits. Measure useful changes noticed and false positives compared with normal diff review. Accuracy claims require such labeled evidence; the initial fixtures are demonstrations and tests only.
