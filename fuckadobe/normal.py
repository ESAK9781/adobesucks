"""Normal mode: keep all fields, values and signatures, just strip the
security theater (encryption/permissions, field locks, usage-rights /
certification restrictions)."""

from .pdfutil import clean_catalog, unlock_field_chain


def unlock(doc):
    for page in doc:
        for widget in page.widgets() or []:
            new_flags = widget.field_flags & ~1  # clear ReadOnly bit
            if new_flags != widget.field_flags:
                widget.field_flags = new_flags
                widget.update()
            unlock_field_chain(doc, widget.xref)

    clean_catalog(doc)
    return doc
