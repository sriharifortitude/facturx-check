# facturx-check

[![CI](https://github.com/sriharifortitude/facturx-check/actions/workflows/ci.yml/badge.svg)](https://github.com/sriharifortitude/facturx-check/actions/workflows/ci.yml)

Checks that a Factur-X / ZUGFeRD hybrid e-invoice agrees with itself: the PDF/A-3
wrapper, the XMP metadata, and the XML invoice embedded in it. Python 3.12, two small
dependencies (pypdf, defusedxml), MIT.

## What it is for

A hybrid invoice is a PDF a person reads with an XML a machine reads, and three
separate places have to say the same thing: the XMP says which profile and which file
name the invoice has, the PDF says how the file is attached, and the XML says which
profile it really is. Generators get these out of step (the profile is changed in one
place, the file is renamed, the XMP extension schema is left out), and the receiving
system then rejects the invoice with a message that says little. This tool finds the
disagreement and names it:

<!-- demo:start -->
```
$ facturx-check testdata/consistent.pdf
testdata/consistent.pdf: consistent
  profile: XML says EN 16931, XMP says EN 16931; invoice INV-2026-001

$ facturx-check testdata/profile-mismatch.pdf
testdata/profile-mismatch.pdf: 1 error, 0 warnings
  profile: XML says BASIC, XMP says EN 16931; invoice INV-2026-001
  error   FX010 the XMP declares conformance level 'EN 16931' but the XML's guideline identifier means 'BASIC'

$ facturx-check testdata/wrong-filename.pdf
testdata/wrong-filename.pdf: 1 error, 0 warnings
  profile: XML says EN 16931, XMP says EN 16931; invoice INV-2026-001
  error   FX009 [factur-x.xml] the XMP says the invoice file is 'zugferd-invoice.xml' but the embedded file is 'factur-x.xml'

$ facturx-check testdata/undeclared-schema.pdf
testdata/undeclared-schema.pdf: 1 error, 0 warnings
  profile: XML says EN 16931, XMP says EN 16931; invoice INV-2026-001
  error   FX011 the XMP uses the namespace urn:factur-x:pdfa:CrossIndustryDocument:invoice:1p0# but declares no pdfaExtension schema for it; PDF/A validators reject undeclared properties

$ facturx-check testdata/pdfa-2.pdf
testdata/pdfa-2.pdf: 1 error, 0 warnings
  profile: XML says EN 16931, XMP says EN 16931; invoice INV-2026-001
  error   FX007 the XMP claims PDF/A-2, which cannot carry an embedded invoice XML; PDF/A-3 is needed

$ facturx-check testdata/no-xmp.pdf
testdata/no-xmp.pdf: 1 error, 0 warnings
  profile: XML says EN 16931, XMP says ?; invoice INV-2026-001
  error   FX006 the PDF has no XMP metadata stream
```
<!-- demo:end -->

Exit codes: 0 no errors, 1 at least one error (or a warning with `--strict`), 2 no
file could be read. `--json` gives the same findings for a pipeline. Pass a directory
to check every `*.pdf` under it.

## What it is not

**It is not a PDF/A validator and not an EN 16931 validator.** It does not check fonts,
colour spaces, the PDF's own structure, or whether the XML satisfies the business rules
and code lists. For those use [veraPDF](https://verapdf.org/) and the official
schematron (or the Mustang validator). A file this tool calls consistent can still be
rejected by either. In the Mustang test corpus, `invalidPDF.pdf` and
`XMLinvalidV2PDF.pdf` are named invalid for exactly those reasons, and this tool,
correctly for its purpose, reports them consistent.

## Checks

| ID | Severity | What it finds |
|---|---|---|
| FX001 | error | no embedded files, or none that is XML |
| FX002 | error | the XML is not named `factur-x.xml`, `zugferd-invoice.xml` (`ZUGFeRD-invoice.xml` in 1.0) or `xrechnung.xml`; the match is case-sensitive |
| FX003 | error / warning | `/AFRelationship` missing or not a PDF/A-3 value; warning when MINIMUM or BASIC WL does not use `Data` |
| FX004 | warning | the file specification is not in the catalog's `/AF` array |
| FX005 | error / warning | the embedded stream has no `/Subtype`, or it is not `text/xml` |
| FX006 | error | no XMP metadata, or it cannot be parsed |
| FX007 | error / warning | no PDF/A identification; PDF/A-1 or -2 (cannot carry the XML); PDF/A-4 is reported but not judged |
| FX008 | error | the XMP lacks the Factur-X properties |
| FX009 | error | the XMP names a different file than the one attached |
| FX010 | error | the XMP profile differs from the profile the XML's guideline identifier (BT-24) means |
| FX011 | error | the XMP uses the invoice namespace without declaring it in a `pdfaExtension` schema, or declares too few properties |
| FX012 | error | the XML is malformed, not a CrossIndustryInvoice, or has no guideline identifier |
| FX013 | error | the PDF is encrypted |
| FX014 | warning | more than one XML attachment |
| FX015 | error | `fx:DocumentType` is not `INVOICE`, or the conformance level is not a known one |
| FX017 | info | the invoice number is not found in the PDF's text (text extraction is unreliable; a hint only) |
| FX018 | error | an attachment could not be read: oversized, corrupt, or the file's structure is too damaged to locate it |
| FX019 | warning | the guideline identifier is not one this tool knows, so the profile comparison was skipped |
| FX020 | info | an Order-X file (an order, not an invoice); not checked |

ZUGFeRD 1.0 (a `CrossIndustryDocument` root, levels BASIC/COMFORT/EXTENDED) and the
ZUGFeRD 2.0 XMP namespace are recognised as what they are. I got both wrong in the
first version and reported them as errors; the corpus showed it
([ADR 3](docs/adr/0003-what-the-corpus-changed.md)).

## Install

```bash
pip install git+https://github.com/sriharifortitude/facturx-check@v0.1.0
facturx-check invoice.pdf
facturx-check invoices/ --json --strict
```

## Untrusted input

A PDF from a supplier is untrusted. The file is capped at 64 MiB; each attachment is
capped at 16 MiB *after* decompression (pypdf's own default is 75 MB), so a zip bomb
inside an attachment is refused and reported, not expanded; the XMP at 4 MiB; at most
64 attachments, and the name tree is walked to a bounded depth. XML (the XMP and the
invoice) is parsed with defusedxml and any DTD or entity is refused, including in
UTF-16, where a byte search for `<!DOCTYPE` would not see it. Nothing is executed and
nothing is fetched. [ADR 2](docs/adr/0002-untrusted-input.md) has the reasoning.

## Tested

```bash
pip install -e ".[dev]" && pytest -q     # 46 tests
```

Fixtures are built by `tests/builder.py` with pypdf, one defect at a time, so each
check has a test that fails when only that defect is present. Other tests cut a valid
PDF at 40 places and flip a byte at 60 places and require that the tool reports and
never crashes; a 17 MiB decompression bomb that compresses to under 100 KB; a UTF-16
DTD; an entity-expansion XMP.

I broke the code in 23 places on purpose (each comparison, each severity decision, the
size limits, the DTD refusal, both XMP forms, the profile table) and checked a test
fails. The first run left six standing. In three, the mutant produced the same finding
ID with a different message, because my tests checked only the ID; in one the test
never made the XMP name the *second* attachment; one had no test at all (a damaged
file reported as having no attachments); and one needed a DTD with no entities,
because defusedxml refuses entities on its own. All six now have tests and none
survives.

**Against real files.** I ran it over the 36 PDFs in the
[Mustang project](https://github.com/ZUGFeRD/mustangproject)'s test resources: 12 are
consistent, 12 contain no invoice (documentation, PDF/A-1 samples, one deliberately
truncated file), 4 have a real inconsistency (an XMP with no Factur-X properties, an
unparseable XMP, a nonsense conformance level, a damaged cross-reference table), and
8 give warnings or notes. I read every finding and judged it by hand. I did **not**
compare the results with veraPDF or with Mustang's own validator, so "judged right"
means "I agree with it", not "a reference validator agrees". That corpus is not
copied into this repository.

**Not tested:** files from commercial invoicing systems (SAP, DATEV, Odoo and so on),
which is where I would expect the cases I have not seen; PDFs over a few MB; Windows
paths with non-ASCII names beyond what the standard library does; the profile table
against every spelling of the guideline identifier that exists in the wild (I handle
the ones in the corpus and the specifications as I read them, and report anything else
as FX019 rather than guessing). Text extraction for FX017 uses pypdf and fails on
scanned or oddly encoded PDFs, which is why it is only a note.

## Limits

- **Consistency, not validity.** See "What it is not".
- **Specification versions move.** Factur-X 1.0.x, ZUGFeRD 2.x and XRechnung change
  their rules between releases; this tool encodes what I could confirm, and says "not
  judged" where I could not (PDF/A-4).
- **One invoice per file.** With several XML attachments it picks the one the XMP
  names and warns.
- **No signature checking.** Signed PDFs are read, not verified.

## Licence

MIT.
