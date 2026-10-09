"""Reading the parts of a PDF that make it a hybrid e-invoice.

A PDF is untrusted input, so everything here is capped: the file, each attachment
after decompression, the metadata stream, and the number of attachments. Anything
pypdf raises on malformed input becomes a PdfError, never a traceback.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pypdf
import pypdf.errors

MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 16 * 1024 * 1024
MAX_XMP_BYTES = 4 * 1024 * 1024
MAX_ATTACHMENTS = 64
_MAX_TREE_DEPTH = 16

# pypdf's default ceiling on one decompressed stream is 75 MB. An invoice XML is kilobytes.
for _limit in ("zlib", "lzw", "run_length", "brotli"):
    setattr(pypdf.Configuration, f"{_limit}_maximum_output_length", MAX_ATTACHMENT_BYTES)


class PdfError(Exception):
    """The file is not a PDF this tool can read."""


@dataclass
class Attachment:
    name: str
    #: The file specification's /AFRelationship without the slash, or None.
    relationship: str | None
    #: The embedded stream's /Subtype (a MIME type) without the slash, or None.
    subtype: str | None
    data: bytes
    #: Whether the catalog's /AF array lists this file specification.
    in_catalog_af: bool
    description: str | None = None


@dataclass
class PdfInfo:
    path: str
    header: str
    pages: int
    encrypted: bool
    xmp: bytes | None
    attachments: list[Attachment] = field(default_factory=list)
    #: Problems met while reading attachments (an oversized one, a corrupt stream).
    attachment_errors: list[str] = field(default_factory=list)
    _reader: Any = None

    def text(self, max_pages: int = 3) -> str:
        """Best-effort visible text of the first pages. Text extraction from PDF is unreliable."""
        if self._reader is None or self.encrypted:
            return ""
        parts: list[str] = []
        for page in list(self._reader.pages)[:max_pages]:
            try:
                parts.append(page.extract_text() or "")
            except (pypdf.errors.PyPdfError, ValueError, KeyError, RecursionError, TypeError, AttributeError):
                continue
        return "\n".join(parts)


def _name(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text[1:] if text.startswith("/") else text


def _walk_names(node: Any, out: list[tuple[str, Any]], depth: int = 0) -> None:
    """Collect (name, file specification) pairs from a name tree, whose leaves may sit under /Kids."""
    if depth > _MAX_TREE_DEPTH or node is None or len(out) > MAX_ATTACHMENTS:
        return
    node = node.get_object()
    names = node.get("/Names")
    if names is not None:
        names = names.get_object()
        for i in range(0, len(names) - 1, 2):
            out.append((str(names[i]), names[i + 1]))
    kids = node.get("/Kids")
    if kids is not None:
        for kid in kids.get_object():
            _walk_names(kid, out, depth + 1)


def _object_id(ref: Any) -> int | None:
    return getattr(ref, "idnum", None)


def read_pdf(path: str | Path) -> PdfInfo:
    p = Path(path)
    try:
        size = p.stat().st_size
    except OSError as e:
        raise PdfError(f"cannot read ({e.__class__.__name__})") from None
    if size > MAX_PDF_BYTES:
        raise PdfError(f"larger than {MAX_PDF_BYTES >> 20} MiB; refusing it")
    try:
        raw = p.read_bytes()
    except OSError as e:
        raise PdfError(f"cannot read ({e.__class__.__name__})") from None
    if not raw.lstrip(b"\x00\t\n\r\f ").startswith(b"%PDF-") and b"%PDF-" not in raw[:1024]:
        raise PdfError("not a PDF (no %PDF- header)")

    try:
        reader = pypdf.PdfReader(io.BytesIO(raw), strict=False)
        header = reader.pdf_header
        encrypted = bool(reader.is_encrypted)
        if encrypted:
            return PdfInfo(p.as_posix(), header, 0, True, None, _reader=reader)
        pages = len(reader.pages)
        root: Any = reader.trailer["/Root"].get_object()
    except (pypdf.errors.PyPdfError, ValueError, KeyError, RecursionError, TypeError, AttributeError, OSError) as e:
        raise PdfError(f"not a readable PDF: {_first_line(e)}") from None

    info = PdfInfo(p.as_posix(), header, pages, False, None, _reader=reader)
    info.xmp = _read_xmp(root, info)

    af_ids: set[int] = set()
    try:
        af = root.get("/AF")
        if af is not None:
            for ref in af.get_object():
                if (oid := _object_id(ref)) is not None:
                    af_ids.add(oid)
    except (pypdf.errors.PyPdfError, ValueError, TypeError, AttributeError, RecursionError):
        info.attachment_errors.append("the catalog's /AF entry is malformed")

    pairs: list[tuple[str, Any]] = []
    try:
        names = root.get("/Names")
        if names is not None:
            tree = names.get_object().get("/EmbeddedFiles")
            _walk_names(tree, pairs)
    except (pypdf.errors.PyPdfError, ValueError, TypeError, AttributeError, RecursionError):
        info.attachment_errors.append("the embedded-files name tree is malformed")

    for display_name, spec_ref in pairs[:MAX_ATTACHMENTS]:
        _read_attachment(display_name, spec_ref, af_ids, info)
    if not pairs and not info.attachment_errors and b"/EmbeddedFile" in raw:
        # A damaged cross-reference table can make the catalog resolve to the wrong objects. Saying
        # "no embedded files" about a file that contains some would be a false answer.
        info.attachment_errors.append(
            "the file contains embedded-file markers but its structure is damaged, so they could not be located"
        )
    if len(pairs) > MAX_ATTACHMENTS:
        info.attachment_errors.append(f"more than {MAX_ATTACHMENTS} attachments; the rest were not read")
    return info


def _first_line(e: BaseException) -> str:
    return (str(e).splitlines() or [e.__class__.__name__])[0][:160]


def _read_xmp(root: Any, info: PdfInfo) -> bytes | None:
    meta = root.get("/Metadata")
    if meta is None:
        return None
    try:
        stream = meta.get_object()
        data: bytes = stream.get_data()
    except (pypdf.errors.PyPdfError, ValueError, TypeError, AttributeError, RecursionError, KeyError) as e:
        info.attachment_errors.append(f"the XMP metadata stream cannot be read: {_first_line(e)}")
        return None
    if len(data) > MAX_XMP_BYTES:
        info.attachment_errors.append(f"the XMP metadata is larger than {MAX_XMP_BYTES >> 20} MiB; ignored")
        return None
    return data


def _read_attachment(display_name: str, spec_ref: Any, af_ids: set[int], info: PdfInfo) -> None:
    try:
        spec = spec_ref.get_object()
        name = str(spec.get("/UF") or spec.get("/F") or display_name)
        relationship = _name(spec.get("/AFRelationship"))
        description = spec.get("/Desc")
        stream_ref = spec.get("/EF", {}).get("/F") or spec.get("/EF", {}).get("/UF")
        if stream_ref is None:
            info.attachment_errors.append(f"{name}: a file specification with no embedded file stream")
            return
        stream = stream_ref.get_object()
        subtype = _name(stream.get("/Subtype"))
        data: bytes = stream.get_data()
    except pypdf.errors.LimitReachedError:
        info.attachment_errors.append(f"{display_name}: expands beyond {MAX_ATTACHMENT_BYTES >> 20} MiB; refusing it")
        return
    except (pypdf.errors.PyPdfError, ValueError, TypeError, AttributeError, KeyError, RecursionError) as e:
        info.attachment_errors.append(f"{display_name}: cannot be read ({_first_line(e)})")
        return
    if len(data) > MAX_ATTACHMENT_BYTES:
        info.attachment_errors.append(f"{display_name}: larger than {MAX_ATTACHMENT_BYTES >> 20} MiB; refusing it")
        return
    info.attachments.append(
        Attachment(
            name=name,
            relationship=relationship,
            subtype=subtype,
            data=data,
            in_catalog_af=_object_id(spec_ref) in af_ids if _object_id(spec_ref) is not None else False,
            description=str(description) if description is not None else None,
        )
    )
