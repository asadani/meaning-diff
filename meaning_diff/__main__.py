"""CLI for Meaning Diff."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .core import compare_texts, render_markdown


def _read(path: Path) -> tuple[str, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} is not valid UTF-8 (byte offset {exc.start})") from exc
    return text, hashlib.sha256(raw).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meaning-diff", description="Locate literal prose changes that may deserve review.")
    parser.add_argument("--version", action="version", version=f"meaning-diff {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    compare = commands.add_parser("compare", help="compare two UTF-8 prose or Markdown files")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--format", choices=("json", "markdown"), default="json")
    compare.add_argument("--threshold", type=float, default=.45)
    compare.add_argument("--out", type=Path, help="write to this file; default is stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        before_text, before_hash = _read(args.before)
        after_text, after_hash = _read(args.after)
        report = compare_texts(before_text, after_text, args.threshold)
        report["before"] = {"path": str(args.before), "sha256": before_hash}
        report["after"] = {"path": str(args.after), "sha256": after_hash}
        if args.format == "markdown":
            output = render_markdown(report)
        else:
            output = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 1 if report["signals"] else 0
    except (ValueError, OSError) as exc:
        print(f"meaning-diff: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
