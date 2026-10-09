from __future__ import annotations

import contextlib
import zlib
from pathlib import Path

import pytest

from facturx_check.pdf import MAX_ATTACHMENT_BYTES, PdfError, read_pdf
from facturx_check.rules import Result, check

from .builder import Spec, build, cii_xml, xmp_packet


def run(tmp_path: Path, spec: Spec | None = None, data: bytes | None = None) -> Result:
    p = tmp_path / "in.pdf"
    p.write_bytes(data if data is not None else build(spec))
    return check(read_pdf(p))


def ids(r: Result, severity: str | None = None) -> set[str]:
    return {f.id for f in r.findings if severity is None or f.severity == severity}


def test_a_consistent_file_has_no_findings(tmp_path: Path) -> None:
    r = run(tmp_path)
    assert r.findings == []
    assert r.facts["xml_profile"] == r.facts["xmp_profile"] == "EN 16931"
    assert r.facts["invoice_number"] == "INV-2026-001"


@pytest.mark.parametrize("profile", ["MINIMUM", "BASIC WL", "BASIC", "EN 16931", "EXTENDED"])
def test_every_profile_round_trips(tmp_path: Path, profile: str) -> None:
    rel = "Data" if profile in {"MINIMUM", "BASIC WL"} else "Alternative"
    r = run(tmp_path, Spec(xml=cii_xml(profile), xmp=xmp_packet(level=profile), relationship=rel))
    assert r.findings == []


def test_profile_mismatch_between_xmp_and_xml(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xml=cii_xml("BASIC"), xmp=xmp_packet(level="EN 16931")))
    assert ids(r, "error") == {"FX010"}


def test_xmp_filename_differs_from_attachment(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xmp=xmp_packet(filename="zugferd-invoice.xml")))
    assert ids(r, "error") == {"FX009"}


def test_no_attachment(tmp_path: Path) -> None:
    assert "FX001" in ids(run(tmp_path, Spec(xml=None)), "error")


def test_attachment_that_is_not_xml(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xml=None, extra=[("photo.png", b"\x89PNG")]))
    assert "FX001" in ids(r, "error")


def test_wrong_attachment_name(tmp_path: Path) -> None:
    assert "FX002" in ids(run(tmp_path, Spec(name="invoice.xml")), "error")


def test_name_is_case_sensitive(tmp_path: Path) -> None:
    assert "FX002" in ids(run(tmp_path, Spec(name="Factur-X.xml", xmp=xmp_packet(filename="Factur-X.xml"))), "error")


def test_missing_relationship(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(relationship=None))
    assert [f.message for f in r.findings if f.id == "FX003"] == [
        "the file specification has no /AFRelationship, which PDF/A-3 requires"
    ]


def test_invalid_relationship(tmp_path: Path) -> None:
    assert ids(run(tmp_path, Spec(relationship="Banana")), "error") == {"FX003"}


def test_minimum_expects_data_relationship(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xml=cii_xml("MINIMUM"), xmp=xmp_packet(level="MINIMUM"), relationship="Alternative"))
    assert ids(r) == {"FX003"} and ids(r, "error") == set()


def test_not_listed_in_catalog_af(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(in_af=False))
    assert ids(r) == {"FX004"} and ids(r, "error") == set()


def test_missing_subtype(tmp_path: Path) -> None:
    assert ids(run(tmp_path, Spec(subtype=None)), "error") == {"FX005"}


def test_other_subtype_is_a_warning(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(subtype="application/octet-stream"))
    assert ids(r) == {"FX005"} and ids(r, "error") == set()


def test_no_xmp(tmp_path: Path) -> None:
    assert ids(run(tmp_path, Spec(xmp=None)), "error") == {"FX006"}


def test_malformed_xmp(tmp_path: Path) -> None:
    assert "FX006" in ids(run(tmp_path, Spec(xmp=b"<x:xmpmeta><unclosed>")), "error")


def test_xmp_without_pdfa_id(tmp_path: Path) -> None:
    assert "FX007" in ids(run(tmp_path, Spec(xmp=xmp_packet(part=None, conformance=None))), "error")


@pytest.mark.parametrize("part", ["1", "2"])
def test_pdfa_1_and_2_cannot_carry_the_xml(tmp_path: Path, part: str) -> None:
    r = run(tmp_path, Spec(xmp=xmp_packet(part=part)))
    assert any(f.id == "FX007" and "cannot carry" in f.message for f in r.findings)


def test_pdfa_4_is_reported_not_judged(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xmp=xmp_packet(part="4")))
    assert ids(r) == {"FX007"} and ids(r, "error") == set()


def test_missing_invoice_properties(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xmp=xmp_packet(version=None, level=None)))
    assert "FX008" in ids(r, "error")


def test_document_type_must_be_invoice(tmp_path: Path) -> None:
    assert "FX015" in ids(run(tmp_path, Spec(xmp=xmp_packet(doc_type="ORDER"))), "error")


def test_unknown_conformance_level(tmp_path: Path) -> None:
    assert "FX015" in ids(run(tmp_path, Spec(xmp=xmp_packet(level="COMFORT"))), "error")


def test_schema_not_declared(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xmp=xmp_packet(declare=False)))
    assert any(f.id == "FX011" and "declares no pdfaExtension schema" in f.message for f in r.findings)


def test_schema_declares_too_few_properties(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xmp=xmp_packet(declared_props=("DocumentType",))))
    assert any("Version" in f.message for f in r.findings if f.id == "FX011")


def test_attribute_form_xmp_is_read(tmp_path: Path) -> None:
    xmp = (
        b"<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
        b"<rdf:Description rdf:about='' xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/' pdfaid:part='3' pdfaid:conformance='B'"
        b" xmlns:fx='urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#' fx:DocumentType='INVOICE'"
        b" fx:DocumentFileName='factur-x.xml' fx:Version='1.0' fx:ConformanceLevel='EN 16931'>"
        b"</rdf:Description></rdf:RDF></x:xmpmeta>"
    )
    r = run(tmp_path, Spec(xmp=xmp))
    assert "FX008" not in ids(r) and "FX009" not in ids(r) and r.facts["xmp_profile"] == "EN 16931"


def test_embedded_xml_is_not_an_invoice(tmp_path: Path) -> None:
    assert "FX012" in ids(run(tmp_path, Spec(xml=b"<hello/>")), "error")


def test_embedded_xml_is_malformed(tmp_path: Path) -> None:
    assert "FX012" in ids(run(tmp_path, Spec(xml=b"<rsm:CrossIndustryInvoice")), "error")


def test_unknown_guideline_skips_the_comparison(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(xml=cii_xml(guideline="urn:example:other")))
    assert ids(r) == {"FX019"}


def test_two_xml_attachments_prefers_the_one_the_xmp_names(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(extra=[("zugferd-invoice.xml", cii_xml("BASIC"))]))
    assert r.facts["attachment"] == "factur-x.xml" and ids(r) == {"FX014"}


def test_xmp_names_the_second_attachment(tmp_path: Path) -> None:
    other = ("zugferd-invoice.xml", cii_xml("EN 16931"))
    r = run(tmp_path, Spec(extra=[other], xmp=xmp_packet(filename="zugferd-invoice.xml")))
    assert r.facts["attachment"] == "zugferd-invoice.xml"
    assert "FX009" not in ids(r)


def test_embedded_file_that_cannot_be_located_is_not_called_absent(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(hide_tree=True))
    assert "FX018" in ids(r, "error") and "FX001" not in ids(r)


def test_a_dtd_without_entities_is_still_refused(tmp_path: Path) -> None:
    xml = b'<?xml version="1.0"?><!DOCTYPE x SYSTEM "http://example.invalid/x.dtd"><x/>'
    r = run(tmp_path, Spec(xml=xml))
    assert any(f.id == "FX012" and "DTD" in f.message for f in r.findings)


def test_encrypted_pdf_is_reported_not_crashed(tmp_path: Path) -> None:
    r = run(tmp_path, Spec(encrypt=True))
    assert ids(r) == {"FX013"}


def test_legacy_zugferd_1(tmp_path: Path) -> None:
    xml = (
        b'<rsm:CrossIndustryDocument xmlns:rsm="urn:ferd:CrossIndustryDocument:invoice:1p0" '
        b'xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:12">'
        b"<rsm:SpecifiedExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter>"
        b"<ram:ID>urn:ferd:CrossIndustryDocument:invoice:1p0:comfort</ram:ID>"
        b"</ram:GuidelineSpecifiedDocumentContextParameter></rsm:SpecifiedExchangedDocumentContext>"
        b"<rsm:HeaderExchangedDocument><ram:ID>R-1</ram:ID></rsm:HeaderExchangedDocument></rsm:CrossIndustryDocument>"
    )
    ns = "urn:ferd:pdfa:CrossIndustryDocument:invoice:1p0#"
    r = run(
        tmp_path,
        Spec(
            xml=xml,
            name="ZUGFeRD-invoice.xml",
            xmp=xmp_packet(filename="ZUGFeRD-invoice.xml", level="COMFORT", namespace=ns),
        ),
    )
    assert r.findings == [] and r.facts["format"] == "ZUGFeRD 1.0"


# --- untrusted input -------------------------------------------------------------------------------------------


def test_not_a_pdf(tmp_path: Path) -> None:
    p = tmp_path / "x.pdf"
    p.write_bytes(b"hello world")
    with pytest.raises(PdfError):
        read_pdf(p)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PdfError):
        read_pdf(tmp_path / "nope.pdf")


def test_truncated_pdf_never_raises_anything_else(tmp_path: Path) -> None:
    full = build()
    for cut in range(0, len(full), max(1, len(full) // 40)):
        p = tmp_path / "t.pdf"
        p.write_bytes(full[:cut])
        with contextlib.suppress(PdfError):
            check(read_pdf(p))


def test_byte_flips_never_raise_anything_else(tmp_path: Path) -> None:
    full = bytearray(build())
    for i in range(0, len(full), max(1, len(full) // 60)):
        mutated = bytearray(full)
        mutated[i] ^= 0xFF
        p = tmp_path / "m.pdf"
        p.write_bytes(bytes(mutated))
        with contextlib.suppress(PdfError):
            check(read_pdf(p))


def test_decompression_bomb_is_refused(tmp_path: Path) -> None:
    bomb = zlib.compress(b"A" * (MAX_ATTACHMENT_BYTES + 1024 * 1024), 9)
    assert len(bomb) < 100_000
    r = run(tmp_path, Spec(raw_stream=bomb, raw_filter="/FlateDecode"))
    assert "FX018" in ids(r, "error")
    assert any("refusing" in f.message for f in r.findings)


def test_utf16_doctype_in_the_xml_is_refused(tmp_path: Path) -> None:
    evil = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x>&a;</x>'.encode("utf-16")
    assert "FX012" in ids(run(tmp_path, Spec(xml=evil)), "error")


def test_entity_expansion_in_xmp_is_refused(tmp_path: Path) -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY a "aaaaaaaaaa">'
        b'<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]><l>&b;</l>'
    )
    assert "FX006" in ids(run(tmp_path, Spec(xmp=bomb)), "error")
