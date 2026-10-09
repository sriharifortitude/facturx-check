"""Command line: facturx-check FILE... [--json] [--strict]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .pdf import PdfError, read_pdf
from .report import render_json, render_text
from .rules import ERROR, WARNING, Finding, Result, check


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="facturx-check",
        description="Check that a Factur-X / ZUGFeRD PDF's wrapper, XMP metadata and embedded XML agree. "
        "Not a PDF/A or EN 16931 validator.",
    )
    p.add_argument("files", nargs="+", help="PDF files, or directories searched for *.pdf")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true", help="exit 1 on warnings as well as errors")
    p.add_argument("--version", action="version", version=f"facturx-check {__version__}")
    args = p.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    paths: list[Path] = []
    for f in args.files:
        path = Path(f)
        paths.extend(sorted(path.rglob("*.pdf")) if path.is_dir() else [path])

    results: list[Result] = []
    unreadable = False
    for path in paths:
        try:
            results.append(check(read_pdf(path)))
        except PdfError as e:
            unreadable = True
            results.append(Result(path.as_posix(), [Finding("FX000", ERROR, str(e))], {}))

    if args.json:
        print(render_json(results))
    else:
        print("\n\n".join(render_text(r) for r in results))

    if unreadable and not any(r.facts for r in results):
        return 2
    failed = any(r.count(ERROR) for r in results) or (args.strict and any(r.count(WARNING) for r in results))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
