"""The checks. Each finding has a stable ID, a severity and one sentence saying what is wrong."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .cii import Cii, parse_cii
from .pdf import Attachment, PdfInfo
from .xmp import NS_ZF1, NS_ZF20, XmlError, Xmp, parse_xmp

ERROR = "error"
WARNING = "warning"
INFO = "info"

# File names the Factur-X and ZUGFeRD specifications allow for the embedded invoice.
INVOICE_NAMES = {"factur-x.xml", "zugferd-invoice.xml", "ZUGFeRD-invoice.xml", "xrechnung.xml"}
_VALID_RELATIONSHIPS = {"Data", "Source", "Alternative", "Supplement", "Unspecified"}
_PROFILES = {"MINIMUM", "BASIC WL", "BASIC", "EN 16931", "EXTENDED", "XRECHNUNG"}
# ZUGFeRD 1.0 named its levels differently.
_PROFILES_V1 = {"BASIC", "COMFORT", "EXTENDED"}


@dataclass(frozen=True)
class Finding:
    id: str
    severity: str
    message: str
    #: What the finding is about, e.g. the attachment name.
    subject: str = ""


@dataclass
class Result:
    path: str
    findings: list[Finding]
    #: Facts found, for the report; empty when nothing could be read.
    facts: dict[str, str]

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)


def _is_xml(a: Attachment) -> bool:
    return a.name.lower().endswith(".xml") or (a.subtype or "").lower() in {"text/xml", "application/xml"}


def check(info: PdfInfo) -> Result:
    findings: list[Finding] = []
    facts: dict[str, str] = {"pdf": info.header, "pages": str(info.pages)}

    def add(id_: str, severity: str, message: str, subject: str = "") -> None:
        findings.append(Finding(id_, severity, message, subject))

    if info.encrypted:
        add("FX013", ERROR, "the PDF is encrypted; PDF/A forbids encryption, and nothing else could be checked")
        return Result(info.path, findings, facts)

    for problem in info.attachment_errors:
        add("FX018", ERROR, problem)

    xml_files = [a for a in info.attachments if _is_xml(a)]
    cii: Cii | None = None
    invoice: Attachment | None = None

    if not info.attachments and info.attachment_errors:
        pass  # the reading problem above is the explanation; "no embedded files" would be misleading
    elif not info.attachments:
        add("FX001", ERROR, "the PDF has no embedded files, so it carries no invoice data")
    elif not xml_files:
        add("FX001", ERROR, "none of the embedded files is XML: " + ", ".join(a.name for a in info.attachments))
    else:
        if any(a.name.lower() == "order-x.xml" for a in xml_files):
            add("FX020", INFO, "this is an Order-X file (an order, not an invoice); it was not checked")
            return Result(info.path, findings, facts)
        named = [a for a in xml_files if a.name in INVOICE_NAMES]
        wanted = _xmp_filename(info)
        invoice = next((a for a in named if a.name == wanted), None) or (named[0] if named else xml_files[0])
        facts["attachment"] = invoice.name
        if len(xml_files) > 1:
            add(
                "FX014",
                WARNING,
                "more than one embedded XML file: " + ", ".join(a.name for a in xml_files),
                invoice.name,
            )
        if not named:
            add(
                "FX002",
                ERROR,
                f"the embedded XML is named {invoice.name!r}; the specifications use factur-x.xml, "
                "zugferd-invoice.xml (ZUGFeRD-invoice.xml in 1.0) or xrechnung.xml",
                invoice.name,
            )
        _check_attachment(invoice, add)
        try:
            cii = parse_cii(invoice.data)
        except XmlError as e:
            add("FX012", ERROR, f"the embedded XML cannot be used: {e}", invoice.name)
        if cii is not None:
            if cii.generation == "1.0":
                facts["format"] = "ZUGFeRD 1.0"
            facts["xml_guideline"] = cii.guideline or "(none)"
            if cii.number:
                facts["invoice_number"] = cii.number
            if cii.profile:
                facts["xml_profile"] = cii.profile
            if cii.guideline is None:
                add(
                    "FX012",
                    ERROR,
                    "the XML has no guideline identifier (BT-24), so its profile is unknown",
                    invoice.name,
                )
            elif cii.profile is None:
                add(
                    "FX019",
                    WARNING,
                    f"the guideline identifier {cii.guideline!r} is not one this tool recognises as a Factur-X "
                    "profile; the profile comparison was skipped",
                    invoice.name,
                )

    xmp = _check_xmp(info, add, facts)

    if xmp is not None and invoice is not None:
        fname = xmp.fx.get("DocumentFileName")
        if fname is not None and fname != invoice.name:
            add(
                "FX009",
                ERROR,
                f"the XMP says the invoice file is {fname!r} but the embedded file is {invoice.name!r}",
                invoice.name,
            )
        level = xmp.fx.get("ConformanceLevel")
        if cii is not None and cii.profile and level and level.upper() != cii.profile:
            add(
                "FX010",
                ERROR,
                f"the XMP declares conformance level {level!r} but the XML's guideline identifier means {cii.profile!r}",
            )
        if invoice.relationship in _VALID_RELATIONSHIPS:
            profile = cii.profile if cii and cii.profile else (level.upper() if level else None)
            if profile in {"MINIMUM", "BASIC WL"} and invoice.relationship != "Data":
                add(
                    "FX003",
                    WARNING,
                    f"Factur-X 1.0 gives profile {profile} the relationship Data, not {invoice.relationship}",
                    invoice.name,
                )

    if cii is not None and cii.number:
        text = info.text()
        if text.strip() and cii.number not in text.replace("\n", " "):
            add(
                "FX017",
                INFO,
                f"the invoice number {cii.number!r} from the XML was not found in the PDF's text; "
                "text extraction is unreliable, so this is only a hint",
            )
    return Result(info.path, findings, facts)


def _xmp_filename(info: PdfInfo) -> str | None:
    if info.xmp is None:
        return None
    try:
        return parse_xmp(info.xmp).fx.get("DocumentFileName")
    except XmlError:
        return None


def _check_attachment(a: Attachment, add: Callable[..., None]) -> None:
    if a.relationship is None:
        add("FX003", ERROR, "the file specification has no /AFRelationship, which PDF/A-3 requires", a.name)
    elif a.relationship not in _VALID_RELATIONSHIPS:
        add("FX003", ERROR, f"/AFRelationship /{a.relationship} is not a PDF/A-3 value", a.name)
    if not a.in_catalog_af:
        add("FX004", WARNING, "the file specification is not listed in the catalog's /AF array", a.name)
    if a.subtype is None:
        add("FX005", ERROR, "the embedded file stream has no /Subtype (a MIME type), which PDF/A-3 requires", a.name)
    elif a.subtype.lower() not in {"text/xml", "application/xml"}:
        add("FX005", WARNING, f"the embedded file stream's /Subtype is {a.subtype!r}, not text/xml", a.name)


def _check_xmp(info: PdfInfo, add: Callable[..., None], facts: dict[str, str]) -> Xmp | None:
    if info.xmp is None:
        add("FX006", ERROR, "the PDF has no XMP metadata stream")
        return None
    try:
        xmp = parse_xmp(info.xmp)
    except XmlError as e:
        add("FX006", ERROR, f"the XMP metadata cannot be used: {e}")
        return None

    if xmp.pdfa_part is None:
        add("FX007", ERROR, "the XMP has no pdfaid:part, so the file does not claim to be PDF/A")
    else:
        facts["pdfa"] = f"{xmp.pdfa_part}{(xmp.pdfa_conformance or '').lower()}"
        if xmp.pdfa_part in {"1", "2"}:
            add(
                "FX007",
                ERROR,
                f"the XMP claims PDF/A-{xmp.pdfa_part}, which cannot carry an embedded invoice XML; PDF/A-3 is needed",
            )
        elif xmp.pdfa_part == "4":
            add(
                "FX007",
                WARNING,
                "the XMP claims PDF/A-4; the Factur-X and ZUGFeRD versions this tool was checked against use "
                "PDF/A-3, so this was not judged",
            )
        elif xmp.pdfa_part != "3":
            add("FX007", ERROR, f"the XMP claims PDF/A-{xmp.pdfa_part}, which is not a PDF/A part this tool knows")
    if xmp.pdfa_part is not None and xmp.pdfa_conformance is None:
        add("FX007", ERROR, "the XMP has no pdfaid:conformance")

    if not xmp.fx:
        add(
            "FX008",
            ERROR,
            "the XMP has no Factur-X properties (fx:DocumentType, DocumentFileName, Version, ConformanceLevel)",
        )
        return xmp
    facts["xmp_namespace"] = xmp.fx_namespace or ""
    for key in ("DocumentType", "DocumentFileName", "Version", "ConformanceLevel"):
        if not xmp.fx.get(key):
            add("FX008", ERROR, f"the XMP is missing fx:{key}")
    if xmp.fx.get("DocumentType") and xmp.fx["DocumentType"] != "INVOICE":
        add("FX015", ERROR, f"fx:DocumentType is {xmp.fx['DocumentType']!r}; it must be INVOICE")
    level = xmp.fx.get("ConformanceLevel")
    if level:
        facts["xmp_profile"] = level
        legacy = xmp.fx_namespace == NS_ZF1
        if level.upper() not in (_PROFILES_V1 if legacy else _PROFILES):
            add(
                "FX015",
                ERROR,
                f"fx:ConformanceLevel {level!r} is not one of {', '.join(sorted(_PROFILES_V1 if legacy else _PROFILES))}",
            )
    if xmp.fx_namespace == NS_ZF20:
        facts["format"] = "ZUGFeRD 2.0"
    elif xmp.fx_namespace == NS_ZF1:
        facts["format"] = "ZUGFeRD 1.0"

    if xmp.fx_namespace not in xmp.declared_schemas:
        add(
            "FX011",
            ERROR,
            f"the XMP uses the namespace {xmp.fx_namespace} but declares no pdfaExtension schema for it; "
            "PDF/A validators reject undeclared properties",
        )
    else:
        missing = [
            p
            for p in ("DocumentFileName", "DocumentType", "Version", "ConformanceLevel")
            if p not in xmp.declared_properties
        ]
        if missing:
            add("FX011", ERROR, "the pdfaExtension schema does not declare: " + ", ".join(missing))
    return xmp
