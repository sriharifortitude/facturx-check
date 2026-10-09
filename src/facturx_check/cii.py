"""The few facts this tool needs from a UN/CEFACT Cross Industry Invoice."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .xmp import XmlError, parse_xml_safely

NS_RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
NS_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"

# Guideline identifiers (BT-24) to the profile names Factur-X uses in its XMP.
_PROFILES = {
    "urn:factur-x.eu:1p0:minimum": "MINIMUM",
    "urn:factur-x.eu:1p0:basicwl": "BASIC WL",
    "urn:cen.eu:en16931:2017#compliant#urn:factur-x.eu:1p0:basic": "BASIC",
    "urn:cen.eu:en16931:2017": "EN 16931",
    "urn:cen.eu:en16931:2017#conformant#urn:factur-x.eu:1p0:extended": "EXTENDED",
}
_XRECHNUNG_MARKERS = ("urn:xeinkauf.de:kosit:xrechnung_", "urn:xoev-de:kosit:standard:xrechnung_")
_ZUGFERD2 = {"minimum": "MINIMUM", "basicwl": "BASIC WL", "basic": "BASIC", "extended": "EXTENDED"}
# ZUGFeRD 1.0 (2014) used a different root element and its own profile names.
NS_ZF1 = "urn:ferd:CrossIndustryDocument:invoice:1p0"
NS_RAM_V1 = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:12"
_ZUGFERD1 = {"basic": "BASIC", "comfort": "COMFORT", "extended": "EXTENDED"}


@dataclass
class Cii:
    guideline: str | None
    profile: str | None
    number: str | None
    type_code: str | None
    #: "1.0" for the original ZUGFeRD, "2" for CrossIndustryInvoice (ZUGFeRD 2.x, Factur-X).
    generation: str = "2"


def profile_for(guideline: str | None) -> str | None:
    if guideline is None:
        return None
    g = guideline.strip()
    if g in _PROFILES:
        return _PROFILES[g]
    if g.startswith("urn:cen.eu:en16931:2017#") and any(m in g for m in _XRECHNUNG_MARKERS):
        return "XRECHNUNG"
    m = re.match(r"^urn:cen\.eu:en16931:2017#(?:compliant|conformant)#urn:zugferd\.de:2p0:(\w+)$", g)
    if m and m.group(1) in _ZUGFERD2:
        return _ZUGFERD2[m.group(1)]
    # Older spelling, with colons, seen in ZUGFeRD 2.0/2.1 files.
    m = re.match(r"^urn:cen\.eu:en16931:2017[:#](?:compliant|conformant)[:#](?:urn:)?factur-x\.eu:1p0:(\w+)$", g)
    if m and m.group(1) in {"basic", "en16931", "extended"}:
        return {"basic": "BASIC", "en16931": "EN 16931", "extended": "EXTENDED"}[m.group(1)]
    m = re.match(r"^urn:zugferd\.de:2p0:(\w+)$", g)
    if m and m.group(1) in _ZUGFERD2:
        return _ZUGFERD2[m.group(1)]
    m = re.match(r"^urn:ferd:CrossIndustryDocument:invoice:1p0:(\w+)$", g)
    if m and m.group(1) in _ZUGFERD1:
        return _ZUGFERD1[m.group(1)]
    return None


def _text(root: ET.Element, path: str, ns: dict[str, str] | None = None) -> str | None:
    el = root.find(path, ns or {"rsm": NS_RSM, "ram": NS_RAM})
    if el is None or el.text is None:
        return None
    return str(el.text).strip() or None


def parse_cii(data: bytes) -> Cii:
    """Raise XmlError when the data is not a CrossIndustryInvoice."""
    root = parse_xml_safely(data)
    if root.tag == f"{{{NS_ZF1}}}CrossIndustryDocument":
        ns = {"rsm": NS_ZF1, "ram": NS_RAM_V1}
        context = "rsm:SpecifiedExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID"
        guideline = _text(root, context, ns)
        number = _text(root, "rsm:HeaderExchangedDocument/ram:ID", ns)
        return Cii(guideline, profile_for(guideline), number, None, "1.0")
    if root.tag != f"{{{NS_RSM}}}CrossIndustryInvoice":
        raise XmlError(f"the root element is {root.tag}, not a CrossIndustryInvoice")
    guideline = _text(root, "rsm:ExchangedDocumentContext/ram:GuidelineSpecifiedDocumentContextParameter/ram:ID")
    return Cii(
        guideline=guideline,
        profile=profile_for(guideline),
        number=_text(root, "rsm:ExchangedDocument/ram:ID"),
        type_code=_text(root, "rsm:ExchangedDocument/ram:TypeCode"),
    )
