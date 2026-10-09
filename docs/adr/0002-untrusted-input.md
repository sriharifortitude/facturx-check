# 2. Treat the PDF and its XML as hostile

Status: accepted

## Context

The usual place this tool runs is an accounts-payable pipeline, on files that arrive
from suppliers or by email. A PDF can carry a compressed stream that expands by orders
of magnitude, and the XML inside it (and the XMP beside it) can declare entities that
expand the same way.

## Decision

- Cap the file (64 MiB), each attachment after decompression (16 MiB), the XMP
  (4 MiB), the attachment count (64) and the name-tree depth (16). pypdf's own
  decompression ceiling is 75 MB per stream; it is lowered through
  `pypdf.Configuration` so a bomb is refused by the library before it is expanded, and
  the length is checked again afterwards.
- Parse XML with defusedxml and `forbid_dtd=True`. An earlier draft searched the raw
  bytes for `<!DOCTYPE` and used the standard library; that is bypassed by a UTF-16
  document, where the marker is not the byte string searched for. Rather than add a
  second, hand-written filter, the parser that is built for this is used, and a test
  with a UTF-16 DTD keeps it honest.
- Every exception pypdf can raise on malformed input becomes a reported finding or a
  `PdfError`. A fuzz-style test (truncation at 40 points, a byte flipped at 60) checks
  that nothing else escapes.
- Never execute, render or fetch anything. Text extraction is limited to three pages.

## Consequences

- A legitimate invoice larger than the caps is refused. The caps are constants in one
  file; an invoice XML is kilobytes and a hybrid PDF is rarely over a few MB.
- A refused attachment is a finding (FX018), not a silent skip, so the pipeline sees
  that the file was not checked.
- The dependence on `pypdf.Configuration` makes the minimum pypdf version 6.20, the
  one the tests ran against; I have not tested older ones.
