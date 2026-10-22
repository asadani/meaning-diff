"""Deterministic sentence alignment and literal review-signal heuristics."""

from __future__ import annotations

import difflib
import hashlib
import re
from typing import Any

_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?%?(?:\s+(?!for\b|of\b|with\b|and\b|or\b|at\b|in\b|on\b|to\b|if\b|unless\b|when\b)[A-Za-z][\w-]*)?", re.IGNORECASE)
_MODAL = re.compile(r"\b(?:must|shall|should|may|can|will|required|optional)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|never|no|cannot|\w+n['’]t)\b", re.IGNORECASE)
_CONDITION = re.compile(r"\b(?:as\s+long\s+as|provided\s+that|only\s+(?:when|after|before)|if|unless|except|until)\b", re.IGNORECASE)
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s*(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
_FENCE_CLOSE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*$")


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def split_sentences(text: str) -> list[dict[str, Any]]:
    """Split prose into located sentence records, excluding fenced code."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    records: list[dict[str, Any]] = []
    heading_stack: dict[int, str] = {}
    paragraph_start: int | None = None
    paragraph_parts: list[str] = []
    position = 0
    in_fence: tuple[str, int] | None = None

    def flush() -> None:
        nonlocal paragraph_start, paragraph_parts
        if paragraph_start is None:
            return
        value = "".join(paragraph_parts)
        bounds = [m.end() for m in re.finditer(r"[.!?](?=[ \t\r\n]|$)", value)]
        start = 0
        for end in [*bounds, len(value)]:
            raw = value[start:end]
            left = len(raw) - len(raw.lstrip())
            right = len(raw.rstrip())
            if right > left:
                absolute_start = paragraph_start + start + left
                absolute_end = paragraph_start + start + right
                sent = value[start + left:start + right]
                record = {
                    "id": f"s{len(records) + 1:04d}",
                    "text": sent,
                    "line_start": _line_number(text, absolute_start),
                    "line_end": _line_number(text, max(absolute_start, absolute_end - 1)),
                }
                context = " > ".join(heading_stack[level] for level in sorted(heading_stack))
                if context:
                    record["context"] = context
                records.append(record)
            start = end
        paragraph_start, paragraph_parts = None, []

    for line in text.splitlines(keepends=True):
        line_body = line.rstrip("\r\n")
        marker = _FENCE.match(line_body)
        if in_fence:
            fence_char, fence_len = in_fence
            closer = _FENCE_CLOSE.match(line_body)
            if closer and closer.group(1)[0] == fence_char and len(closer.group(1)) >= fence_len:
                in_fence = None
            position += len(line)
            continue
        if marker:
            flush()
            token = marker.group(1)
            in_fence = (token[0], len(token))
            position += len(line)
            continue
        heading = _HEADING.match(line_body)
        if heading:
            flush()
            level, title = len(heading.group(1)), heading.group(2).strip()
            heading_stack = {n: value for n, value in heading_stack.items() if n < level}
            if title:
                heading_stack[level] = title
            position += len(line)
            continue
        if not line_body.strip():
            flush()
            position += len(line)
            continue
        if paragraph_start is None:
            paragraph_start = position
        paragraph_parts.append(line)
        position += len(line)
    flush()
    return records


def _pair_id(old_index: int | None, new_index: int | None, before: dict | None, after: dict | None) -> str:
    fingerprint = hashlib.sha256(((before or {}).get("text", "") + "\0" + (after or {}).get("text", "")).encode("utf-8")).hexdigest()[:8]
    old_part = f"o{old_index + 1:04d}" if old_index is not None else "o----"
    new_part = f"n{new_index + 1:04d}" if new_index is not None else "n----"
    return f"pair-{old_part}-{new_part}-{fingerprint}"


def align_sentences(before: list[dict], after: list[dict], threshold: float = 0.45) -> list[dict]:
    """Align exact normalized anchors, then greedily align replacements."""
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise ValueError("threshold must be a number in [0, 1]")
    for label, sentences in (("before", before), ("after", after)):
        if not isinstance(sentences, list) or any(not isinstance(s, dict) or not isinstance(s.get("text"), str) for s in sentences):
            raise ValueError(f"{label} sentences must be a list of sentence objects with text")
    old_norm = [_normalize(s["text"]) for s in before]
    new_norm = [_normalize(s["text"]) for s in after]
    matcher = difflib.SequenceMatcher(None, old_norm, new_norm, autojunk=False)
    aligned: dict[tuple[int, int], tuple[float, str]] = {}
    used_old: set[int] = set()
    used_new: set[int] = set()
    opcodes = matcher.get_opcodes()
    new_order_old: dict[int, int] = {}
    for tag, i1, i2, j1, j2 in opcodes:
        if tag in ("insert", "replace"):
            for ni in range(j1, j2):
                new_order_old[ni] = i1
        if tag == "equal":
            for oi, ni in zip(range(i1, i2), range(j1, j2)):
                aligned[(oi, ni)] = (1.0, "exact")
                used_old.add(oi)
                used_new.add(ni)
        elif tag == "replace":
            candidates = []
            for oi in range(i1, i2):
                for ni in range(j1, j2):
                    ratio = difflib.SequenceMatcher(None, old_norm[oi], new_norm[ni], autojunk=False).ratio()
                    if ratio >= threshold:
                        candidates.append((-ratio, oi, ni))
            for neg_ratio, oi, ni in sorted(candidates):
                if oi not in used_old and ni not in used_new:
                    aligned[(oi, ni)] = (-neg_ratio, "similarity")
                    used_old.add(oi)
                    used_new.add(ni)
    pairs = []
    for (oi, ni), (score, method) in aligned.items():
        if method == "exact":
            continue
        pairs.append({"_old_index": oi, "_new_index": ni, "before": before[oi], "after": after[ni], "similarity": round(score, 4), "_alignment": method})
    for oi, sentence in enumerate(before):
        if oi not in used_old:
            pairs.append({"_old_index": oi, "_new_index": None, "before": sentence, "after": None, "similarity": None, "_alignment": "unmatched"})
    for ni, sentence in enumerate(after):
        if ni not in used_new:
            pairs.append({"_old_index": None, "_new_index": ni, "before": None, "after": sentence, "similarity": None, "_alignment": "unmatched"})
    pairs.sort(key=lambda p: (p["_old_index"] if p["_old_index"] is not None else new_order_old.get(p["_new_index"], len(before)),
                              p["_new_index"] if p["_new_index"] is not None else len(after)))
    result = []
    for pair in pairs:
        oi, ni = pair.pop("_old_index"), pair.pop("_new_index")
        pair["id"] = _pair_id(oi, ni, pair["before"], pair["after"])
        result.append(pair)
    return result


def _tokens(pattern: re.Pattern, text: str) -> list[str]:
    return [match.group(0).strip().casefold() for match in pattern.finditer(text)]


def _condition_suffix(text: str) -> str | None:
    match = _CONDITION.search(text)
    return _normalize(text[match.start():]) if match else None


def _family_tokens(text: str) -> dict[str, list[str]]:
    condition = _condition_suffix(text)
    return {
        "numbers": _tokens(_NUMBER, text),
        "modals": _tokens(_MODAL, text),
        "negations": _tokens(_NEGATION, text),
        "conditions": [condition] if condition is not None else [],
    }


def _signal(pair: dict, kind: str, priority: str, message: str, before_tokens: Any = None, after_tokens: Any = None) -> dict:
    digest = hashlib.sha256(f"{pair['id']}\0{kind}".encode()).hexdigest()[:8]
    result = {"id": f"signal-{kind}-{digest}", "pair_id": pair["id"], "kind": kind, "priority": priority, "message": message}
    if before_tokens is not None:
        result["before_tokens"] = before_tokens
    if after_tokens is not None:
        result["after_tokens"] = after_tokens
    return result


def detect_signals(pair: dict) -> list[dict]:
    """Return fixed-vocabulary literal review signals for one aligned pair."""
    before, after = pair.get("before"), pair.get("after")
    old_text = before["text"] if before else ""
    new_text = after["text"] if after else ""
    if before is None:
        families = _family_tokens(new_text)
        urgent = bool(families["numbers"] or families["modals"] or families["negations"])
        return [_signal(pair, "sentence_added", "medium" if urgent else "low",
                        "Sentence added; review its effect. Token-family evidence is included for prioritization.",
                        [], families)]
    if after is None:
        families = _family_tokens(old_text)
        return [_signal(pair, "sentence_dropped", "medium",
                        "Sentence dropped; review its effect. Token-family evidence is included for prioritization.",
                        families, [])]
    if _normalize(old_text) == _normalize(new_text):
        return []
    signals = []
    old_nums, new_nums = _tokens(_NUMBER, old_text), _tokens(_NUMBER, new_text)
    if old_nums != new_nums:
        signals.append(_signal(pair, "number_changed", "high", "Ordered numeric tokens differ; units are not converted or compared for equivalence.", old_nums, new_nums))
    old_modals, new_modals = _tokens(_MODAL, old_text), _tokens(_MODAL, new_text)
    if old_modals != new_modals:
        signals.append(_signal(pair, "modal_changed", "high", "Modal or requirement-word tokens differ; no universal obligation ranking is applied.", old_modals, new_modals))
    old_neg, new_neg = _tokens(_NEGATION, old_text), _tokens(_NEGATION, new_text)
    if old_neg != new_neg:
        signals.append(_signal(pair, "negation_changed", "high", "Negation tokens differ.", old_neg, new_neg))
    old_condition, new_condition = _condition_suffix(old_text), _condition_suffix(new_text)
    if old_condition != new_condition:
        signals.append(_signal(pair, "condition_changed", "medium", "Condition-marker suffixes differ; this is a phrase heuristic, not a condition parser.",
                               [old_condition] if old_condition is not None else [], [new_condition] if new_condition is not None else []))
    return signals


def compare_texts(before: str, after: str, threshold: float = 0.45) -> dict:
    """Compare prose without filesystem access and return a deterministic report."""
    old_sentences, new_sentences = split_sentences(before), split_sentences(after)
    pairs = align_sentences(old_sentences, new_sentences, threshold)
    changed_pairs = []
    signals = []
    for pair in pairs:
        # Exact anchors do not appear in the aligned changed-pair list. Similarity
        # pairs with only case/whitespace changes are ignored by design.
        pair_signals = detect_signals(pair)
        if pair["_alignment"] == "similarity" and _normalize(pair["before"]["text"]) == _normalize(pair["after"]["text"]):
            continue
        clean = {key: value for key, value in pair.items() if not key.startswith("_")}
        changed_pairs.append(clean)
        signals.extend(pair_signals)
    method = {
        "alignment": "SequenceMatcher exact normalized anchors; greedy within-block lexical similarity replacements",
        "threshold": float(threshold),
        "language": "en",
        "limitations": [
            "Heuristic sentence alignment can miss subtle paraphrases or pair unrelated replacement sentences.",
            "Abbreviations, tables, and unusual Markdown may segment imperfectly; fenced code blocks are ignored.",
            "Reordered sentences may appear as added and dropped; moves are not detected.",
            "Case and whitespace-only sentence edits are ignored. Numeric units are not converted.",
            "Condition suffixes beginning with if, unless, except, only when, only after, only before, provided that, as long as, or until are literal phrase comparisons, not parsed logic.",
            "Signal priorities are review-order hints, not severity or correctness.",
            "No signal means only that these configured patterns were not detected; it does not mean meaning was preserved.",
        ],
    }
    return {"schema_version": 1, "method": method, "changed_pairs": changed_pairs, "signals": signals}


def render_markdown(report: dict) -> str:
    """Render a portable Markdown view with safe fences around literal text."""
    signals_by_pair: dict[str, list[dict]] = {}
    for signal in report["signals"]:
        signals_by_pair.setdefault(signal["pair_id"], []).append(signal)
    lines = ["# Meaning Diff review", "", "**Heuristic review signals. No semantic equivalence judgment is made.**", "",
             f"- Changed sentence pairs: {len(report['changed_pairs'])}",
             f"- Review signals: {len(report['signals'])}",
             f"- Alignment threshold: {report['method']['threshold']:.2f}", "", "## Limitations", ""]
    lines.extend(f"- {lim}" for lim in report["method"]["limitations"])
    lines += ["", "## Changed sentences", ""]
    if not report["changed_pairs"]:
        lines.append("No configured heuristic signals detected.")
    for pair in report["changed_pairs"]:
        before, after = pair["before"], pair["after"]
        score = f"{pair['similarity']:.4f}" if pair["similarity"] is not None else "unmatched"
        lines += [f"### {pair['id']} — alignment score: {score}", ""]
        for side, sentence in (("Before", before), ("After", after)):
            if sentence is None:
                lines += [f"**{side}:** (no sentence)", ""]
            else:
                location = f"lines {sentence['line_start']}–{sentence['line_end']}"
                context = f"; context: {sentence['context']}" if sentence.get("context") else ""
                lines += [f"**{side} ({location}{context}):**", "", _fence(sentence["text"]), ""]
        pair_signals = signals_by_pair.get(pair["id"], [])
        if pair_signals:
            lines.append("**Signals:**")
            for signal in pair_signals:
                evidence = ""
                if "before_tokens" in signal or "after_tokens" in signal:
                    evidence = f" Before: {_inline(signal.get('before_tokens', []))}; after: {_inline(signal.get('after_tokens', []))}."
                lines.append(f"- `{signal['kind']}` ({signal['priority']}): {signal['message']}{evidence}")
            lines.append("")
        else:
            lines += ["No configured heuristic signals detected for this pair.", ""]
    return "\n".join(lines).rstrip() + "\n"


def _fence(text: str) -> str:
    longest = max((len(run) for run in re.findall(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def _inline(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    delimiter = "`" * (max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    return f"{delimiter}{text}{delimiter}"
