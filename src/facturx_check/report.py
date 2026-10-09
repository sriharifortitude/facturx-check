"""Text and JSON output."""

from __future__ import annotations

import json

from .rules import ERROR, Result

_ORDER = {"error": 0, "warning": 1, "info": 2}


def _n(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def render_text(r: Result) -> str:
    errors, warnings = r.count(ERROR), r.count("warning")
    lines = []
    if errors:
        lines.append(f"{r.path}: {_n(errors, 'error')}, {_n(warnings, 'warning')}")
    elif warnings:
        lines.append(f"{r.path}: no errors, {_n(warnings, 'warning')}")
    else:
        lines.append(f"{r.path}: consistent")
    facts = r.facts
    if "xml_profile" in facts or "xmp_profile" in facts:
        lines.append(
            f"  profile: XML says {facts.get('xml_profile', '?')}, XMP says {facts.get('xmp_profile', '?')}"
            + (f"; invoice {facts['invoice_number']}" if "invoice_number" in facts else "")
        )
    for f in sorted(r.findings, key=lambda f: (_ORDER[f.severity], f.id)):
        subject = f" [{f.subject}]" if f.subject else ""
        lines.append(f"  {f.severity:<7} {f.id}{subject} {f.message}")
    return "\n".join(lines)


def render_json(results: list[Result]) -> str:
    return json.dumps(
        [
            {
                "path": r.path,
                "facts": r.facts,
                "findings": [
                    {"id": f.id, "severity": f.severity, "message": f.message, "subject": f.subject} for f in r.findings
                ],
            }
            for r in results
        ],
        indent=2,
        ensure_ascii=False,
    )
