"""Collapse PDF portfolios (collections of embedded files) into a single
conjoined PDF."""

import pymupdf

from .pdfutil import warn


def is_portfolio(doc):
    return doc.embfile_count() > 0


def collapse_portfolio(doc, source_name="input"):
    """Return a new, plain fitz.Document containing the original document's
    own pages followed by every embedded file, each converted to PDF pages
    and appended in order. Embedded files MuPDF can't render (unsupported
    formats) get a placeholder page instead of being silently dropped."""
    merged = pymupdf.open()

    if doc.page_count > 0:
        merged.insert_pdf(doc)

    for name in doc.embfile_names():
        info = doc.embfile_info(name)
        data = doc.embfile_get(name)
        label = info.get("filename") or name

        try:
            sub = pymupdf.open(stream=data, filename=label)
            pdf_bytes = sub.convert_to_pdf()
            sub.close()
            sub_pdf = pymupdf.open(stream=pdf_bytes, filetype="pdf")
            merged.insert_pdf(sub_pdf)
            sub_pdf.close()
            continue
        except Exception as e:
            warn(f"could not render embedded file '{label}' from {source_name}: {e}")

        page = merged.new_page()
        page.insert_text(
            (72, 72),
            f"[Embedded file could not be converted]\n"
            f"name: {label}\n"
            f"size: {len(data)} bytes",
            fontsize=12,
        )

    return merged
