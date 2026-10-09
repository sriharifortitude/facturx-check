"""The XMP metadata packet: PDF/A identification and the Factur-X extension properties.

XMP is RDF/XML, and the same property can be written as an attribute of
rdf:Description or as a child element; both forms are read. DTDs and entities are
refused outright (defusedxml with forbid_dtd), because XMP is untrusted input and
entity expansion is the classic way to make an XML reader run out of memory.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_fromstring

NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
NS_PDFAID = "http://www.aiim.org/pdfa/ns/id/"
NS_PDFAEXT = "http://www.aiim.org/pdfa/ns/extension/"
NS_PDFASCHEMA = "http://www.aiim.org/pdfa/ns/schema#"
NS_PDFAPROP = "http://www.aiim.org/pdfa/ns/property#"
#: Factur-X 1.0 and ZUGFeRD 2.1+.
NS_FX = "urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0#"
#: ZUGFeRD 2.0 used its own namespace.
NS_ZF20 = "urn:zugferd:pdfa:CrossIndustryDocument:invoice:2p0#"
#: The original ZUGFeRD 1.0.
NS_ZF1 = "urn:ferd:pdfa:CrossIndustryDocument:invoice:1p0#"


class XmlError(ValueError):
    """The XML was not parsed: it is malformed, or uses a DTD or entities."""


def parse_xml_safely(data: bytes) -> ET.Element:
    try:
        root: ET.Element = safe_fromstring(data, forbid_dtd=True)
        return root
    except DefusedXmlException:
        raise XmlError("it declares a DTD or entities, which this tool does not process") from None
    except ET.ParseError as e:
        raise XmlError(f"not well-formed XML ({e})") from None
    except (ValueError, RecursionError, UnicodeError):
        raise XmlError("not parseable XML") from None


@dataclass
class Xmp:
    #: pdfaid:part and pdfaid:conformance
    pdfa_part: str | None = None
    pdfa_conformance: str | None = None
    #: The invoice properties, keyed by local name: DocumentType, DocumentFileName, Version, ConformanceLevel.
    fx: dict[str, str] = field(default_factory=dict)
    #: Namespace URI that carried those properties, or None when none was found.
    fx_namespace: str | None = None
    #: Namespace URIs declared by pdfaExtension:schemas entries.
    declared_schemas: list[str] = field(default_factory=list)
    #: Property names declared by the extension schema for the invoice namespace.
    declared_properties: list[str] = field(default_factory=list)


def _local(tag: str) -> tuple[str, str]:
    if tag.startswith("{"):
        ns, _, name = tag[1:].partition("}")
        return ns, name
    return "", tag


def parse_xmp(data: bytes) -> Xmp:
    root = parse_xml_safely(data)
    out = Xmp()
    seen: dict[str, dict[str, str]] = {}

    def record(ns: str, name: str, value: str) -> None:
        seen.setdefault(ns, {})[name] = value.strip()

    for desc in root.iter(f"{{{NS_RDF}}}Description"):
        for key, value in desc.attrib.items():
            ns, name = _local(key)
            if ns:
                record(ns, name, value)
        for child in desc:
            ns, name = _local(child.tag)
            if ns in (NS_PDFAID, NS_FX, NS_ZF20, NS_ZF1) and len(child) == 0:
                record(ns, name, child.text or "")

    pdfaid = seen.get(NS_PDFAID, {})
    out.pdfa_part = pdfaid.get("part")
    out.pdfa_conformance = pdfaid.get("conformance")
    for ns in (NS_FX, NS_ZF20, NS_ZF1):
        if ns in seen:
            out.fx = seen[ns]
            out.fx_namespace = ns
            break

    for uri in root.iter(f"{{{NS_PDFASCHEMA}}}namespaceURI"):
        if uri.text and uri.text.strip():
            out.declared_schemas.append(uri.text.strip())
    # Properties are declared as pdfaSchema:property -> rdf:li -> pdfaProperty:name.
    for li in root.iter(f"{{{NS_PDFASCHEMA}}}property"):
        for prop in li.iter(f"{{{NS_PDFAPROP}}}name"):
            if prop.text and prop.text.strip():
                out.declared_properties.append(prop.text.strip())
    return out
