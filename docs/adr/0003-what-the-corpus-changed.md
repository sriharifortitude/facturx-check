# 3. What the corpus changed

Status: accepted

The first version was written from the Factur-X specification and a single valid file.
Running it over the 36 PDFs in the Mustang test resources, before any README existed,
showed it was wrong in these ways, all fixed:

1. **ZUGFeRD 1.0 reported as errors.** Its root is `CrossIndustryDocument` in another
   namespace, its file is `ZUGFeRD-invoice.xml`, its levels are BASIC/COMFORT/EXTENDED
   and its XMP namespace differs. Six files in the corpus were reported as "not an invoice". It is
   now recognised and checked on its own terms.
2. **ZUGFeRD 2.0's XMP namespace reported as a warning.** It is a legitimate
   namespace; the warning was noise and is now a note in the facts.
3. **Order-X reported as a broken invoice.** Order-X is a different standard with the
   same wrapper. It is now identified and skipped (FX020).
4. **Guideline identifiers.** The table knew the Factur-X spellings only. The corpus
   has the `urn:zugferd.de:2p0:*` forms, an older colon-separated Factur-X spelling,
   and XRechnung 1.2 under a different URN prefix than 3.0. Unrecognised ones now
   produce a warning and skip the comparison.
5. **Choosing the invoice among several XML attachments.** The first match was used,
   so a file with two invoice-named attachments was compared against the wrong one.
   The attachment the XMP names is now preferred.
6. **A damaged file called empty.** In `corruptedV2PDF.pdf` the cross-reference table
   is broken and pypdf's recovery resolves the catalog to the wrong objects, so the
   tool said "no embedded files" about a file that has some. That is a false
   statement, so it now says the structure is damaged and the files could not be
   located (FX018).
7. **PDF/A-4.** One file claims it. Whether the current specifications permit it for
   Factur-X I could not confirm, so it is reported and not judged.

The general lesson, which is why this ADR exists: a checker's first version encodes the
author's reading of the standard, and the only thing that finds the distance between
that and practice is files that other people made.
