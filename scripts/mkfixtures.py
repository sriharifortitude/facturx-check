"""Write the small PDFs in testdata/ that the README's example runs on.

Run from the repository root:  python scripts/mkfixtures.py
They are synthetic: built with pypdf, one defect each, and no real invoice data.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tests.builder import Spec, build, cii_xml, xmp_packet  # noqa: E402

FIXTURES = {
    "consistent.pdf": Spec(),
    "profile-mismatch.pdf": Spec(xml=cii_xml("BASIC"), xmp=xmp_packet(level="EN 16931")),
    "wrong-filename.pdf": Spec(xmp=xmp_packet(filename="zugferd-invoice.xml")),
    "undeclared-schema.pdf": Spec(xmp=xmp_packet(declare=False)),
    "pdfa-2.pdf": Spec(xmp=xmp_packet(part="2", conformance="B")),
    "no-xmp.pdf": Spec(xmp=None),
}


def main() -> None:
    out = ROOT / "testdata"
    out.mkdir(exist_ok=True)
    for name, spec in FIXTURES.items():
        (out / name).write_bytes(build(spec))
        print("wrote", out / name)


if __name__ == "__main__":
    main()
