# 1. Check that the parts agree, not that the file is valid

Status: accepted

## Context

Two mature validators exist. veraPDF checks PDF/A conformance; the EN 16931
schematron, run by Mustang or KoSIT, checks the XML. Neither answers a question that
causes real rejections: do the XMP, the PDF attachment dictionary and the XML say the
same thing? Each validator looks at its own layer. A file can pass both and still name
a different profile in the XMP than in the XML, because no rule spans the layers.

## Decision

This tool checks only agreement between the layers, plus the few PDF/A-3 attachment
requirements that are cheap to read (relationship, subtype, `/AF`, XMP declarations).
It does not try to be a validator. It reads the XML for three facts: the root element,
the guideline identifier, the invoice number.

## Consequences

- It is small enough to read in one sitting and has no Java dependency.
- It will say "consistent" about files that veraPDF or the schematron reject. The
  README says so before anything else, and the corpus run shows two such files.
- Anything it cannot place (an unknown guideline identifier, PDF/A-4) is reported as
  "not judged" rather than guessed, because a wrong verdict from a checker is worse
  than none.
