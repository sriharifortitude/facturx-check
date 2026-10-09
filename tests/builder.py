"""Build small hybrid-invoice PDFs with pypdf, one defect at a time."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import cast

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    TextStringObject,
)

GUIDELINE = {
    "MINIMUM": "urn:factur-x.eu:1p0:minimum",
    "BASIC WL": "urn:factur-x.eu:1p0:basicwl",
    "BASIC": "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic",
    "EN 16931": "urn:cen.eu:en16931:2017",
    "EXTENDED": "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended",
}

NS_FX = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"


def cii_xml(profile: str = "EN 16931", number: str = "INV-2026-001", guideline: str | None = None) -> bytes:
    gid = guideline if guideline is not None else GUIDELINE[profile]
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rsm:CrossIndustryInvoice xmlns:rsm="urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100" '
        'xmlns:ram="urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100">'
        "<rsm:ExchangedDocumentContext><ram:GuidelineSpecifiedDocumentContextParameter>"
        f"<ram:ID>{gid}</ram:ID></ram:GuidelineSpecifiedDocumentContextParameter></rsm:ExchangedDocumentContext>"
        f"<rsm:ExchangedDocument><ram:ID>{number}</ram:ID><ram:TypeCode>380</ram:TypeCode></rsm:ExchangedDocument>"
        "</rsm:CrossIndustryInvoice>"
    ).encode()


def xmp_packet(
    *,
    part: str | None = "3",
    conformance: str | None = "B",
    doc_type: str | None = "INVOICE",
    filename: str | None = "factur-x.xml",
    version: str | None = "1.0",
    level: str | None = "EN 16931",
    namespace: str = NS_FX,
    declare: bool = True,
    declared_props: tuple[str, ...] = ("DocumentFileName", "DocumentType", "Version", "ConformanceLevel"),
) -> bytes:
    fx = "".join(
        f"<fx:{k}>{v}</fx:{k}>"
        for k, v in (
            ("DocumentType", doc_type),
            ("DocumentFileName", filename),
            ("Version", version),
            ("ConformanceLevel", level),
        )
        if v is not None
    )
    pdfaid = ""
    if part is not None:
        pdfaid += f"<pdfaid:part>{part}</pdfaid:part>"
    if conformance is not None:
        pdfaid += f"<pdfaid:conformance>{conformance}</pdfaid:conformance>"
    props = "".join(
        f"<rdf:li rdf:parseType='Resource'><pdfaProperty:name>{n}</pdfaProperty:name></rdf:li>" for n in declared_props
    )
    schema = (
        "<pdfaExtension:schemas xmlns:pdfaExtension='http://www.aiim.org/pdfa/ns/extension/'><rdf:Bag>"
        "<rdf:li rdf:parseType='Resource'>"
        f"<pdfaSchema:namespaceURI xmlns:pdfaSchema='http://www.aiim.org/pdfa/ns/schema#'>{namespace}</pdfaSchema:namespaceURI>"
        f"<pdfaSchema:property xmlns:pdfaSchema='http://www.aiim.org/pdfa/ns/schema#'><rdf:Seq>{props}</rdf:Seq></pdfaSchema:property>"
        "</rdf:li></rdf:Bag></pdfaExtension:schemas>"
        if declare
        else ""
    )
    return (
        "<?xpacket begin='﻿' id='W5M0MpCehiHzreSzNTczkc9d'?>"
        "<x:xmpmeta xmlns:x='adobe:ns:meta/'><rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>"
        "<rdf:Description rdf:about='' xmlns:pdfaid='http://www.aiim.org/pdfa/ns/id/'>"
        f"{pdfaid}</rdf:Description>"
        f"<rdf:Description rdf:about='' xmlns:fx='{namespace}'>{fx}</rdf:Description>"
        "<rdf:Description rdf:about='' xmlns:pdfaProperty='http://www.aiim.org/pdfa/ns/property#'>"
        f"{schema}</rdf:Description>"
        "</rdf:RDF></x:xmpmeta><?xpacket end='w'?>"
    ).encode()


@dataclass
class Spec:
    xml: bytes | None = field(default_factory=cii_xml)
    name: str = "factur-x.xml"
    relationship: str | None = "Alternative"
    subtype: str | None = "text/xml"
    in_af: bool = True
    xmp: bytes | None = field(default_factory=xmp_packet)
    extra: list[tuple[str, bytes]] = field(default_factory=list)
    encrypt: bool = False
    raw_stream: bytes | None = None
    raw_filter: str | None = None
    #: Leave the file out of the embedded-files name tree, as a damaged catalog would.
    hide_tree: bool = False


def build(spec: Spec | None = None) -> bytes:
    spec = spec or Spec()
    w = PdfWriter()
    w.add_blank_page(200, 200)
    af = ArrayObject()
    files = ([(spec.name, spec.xml)] if spec.xml is not None else []) + [(n, d) for n, d in spec.extra]
    for i, (name, data) in enumerate(files):
        primary = i == 0 and spec.xml is not None
        stream = DecodedStreamObject()
        stream.set_data(data)
        if primary and spec.raw_stream is not None:
            stream = DecodedStreamObject()
            stream._data = spec.raw_stream  # pre-encoded bytes, written as they are
            stream[NameObject("/Filter")] = NameObject(spec.raw_filter or "/FlateDecode")
        stream[NameObject("/Type")] = NameObject("/EmbeddedFile")
        subtype = spec.subtype if primary else ("text/xml" if name.endswith(".xml") else "image/png")
        if subtype is not None:
            stream[NameObject("/Subtype")] = NameObject("/" + subtype)
        sref = w._add_object(stream)
        fs = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Filespec"),
                NameObject("/F"): TextStringObject(name),
                NameObject("/UF"): TextStringObject(name),
                NameObject("/EF"): DictionaryObject({NameObject("/F"): sref, NameObject("/UF"): sref}),
            }
        )
        rel = spec.relationship if primary else "Supplement"
        if rel is not None:
            fs[NameObject("/AFRelationship")] = NameObject("/" + rel)
        fref = w._add_object(fs)
        if not primary or spec.in_af:
            af.append(fref)
        if not (primary and spec.hide_tree):
            _register(w, name, fref)
    root = w._root_object
    if len(af):
        root[NameObject("/AF")] = af
    if spec.xmp is not None:
        m = DecodedStreamObject()
        m.set_data(spec.xmp)
        m[NameObject("/Type")] = NameObject("/Metadata")
        m[NameObject("/Subtype")] = NameObject("/XML")
        root[NameObject("/Metadata")] = w._add_object(m)
    if spec.encrypt:
        w.encrypt("user", "owner")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _register(w: PdfWriter, name: str, fref: object) -> None:
    root = w._root_object
    names = root.get("/Names")
    if names is None:
        names = DictionaryObject()
        root[NameObject("/Names")] = names
    ef = names.get("/EmbeddedFiles")
    if ef is None:
        ef = DictionaryObject({NameObject("/Names"): ArrayObject()})
        names[NameObject("/EmbeddedFiles")] = ef
    listing = cast(ArrayObject, ef["/Names"])
    listing.append(TextStringObject(name))
    listing.append(fref)
