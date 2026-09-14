"""Low-level xref surgery shared by normal and nuclear modes."""

import re
import sys

import pymupdf

_REF_RE = re.compile(r"^\s*(\d+)\s+\d+\s+R\s*$")


def warn(msg):
    print(f"warning: {msg}", file=sys.stderr)


def _split_ref(value):
    m = _REF_RE.match(value)
    return int(m.group(1)) if m else None


def open_pdf(path, password=None):
    doc = pymupdf.open(path)
    if not doc.is_pdf:
        raise SystemExit(f"'{path}' is not a PDF")
    if doc.needs_pass:
        if not password or not doc.authenticate(password):
            raise SystemExit(
                f"'{path}' requires a password to open; pass --password"
            )
    return doc


def delete_catalog_key(doc, key):
    cat = doc.pdf_catalog()
    typ, _ = doc.xref_get_key(cat, key)
    if typ not in (None, "null"):
        doc.xref_set_key(cat, key, "null")


def _acroform_target(doc):
    """Return (xref_num, None) if AcroForm is an indirect object, or
    (None, inline_dict_string) if it is embedded inline in the catalog."""
    cat = doc.pdf_catalog()
    typ, val = doc.xref_get_key(cat, "AcroForm")
    if typ == "xref":
        return _split_ref(val), None
    if typ == "dict":
        return None, val
    return None, None


def _set_inline_scalar(dict_string, key, value):
    if re.search(r"/" + key + r"\b", dict_string):
        return re.sub(r"/" + key + r"\s+[^/<>\[\]]+", f"/{key} {value}", dict_string)
    return dict_string[:-2] + f"/{key} {value}>>"


def clean_acroform(doc):
    """Clear the AppendOnly signature-lock bit and force appearance
    regeneration so other programs don't choke on stale/locked forms."""
    af_xref, inline = _acroform_target(doc)
    if af_xref is not None:
        doc.xref_set_key(af_xref, "NeedAppearances", "true")
        typ, val = doc.xref_get_key(af_xref, "SigFlags")
        if typ == "int":
            newflags = int(val) & ~2
            doc.xref_set_key(af_xref, "SigFlags", str(newflags))
    elif inline is not None:
        cat = doc.pdf_catalog()
        new_val = _set_inline_scalar(inline, "NeedAppearances", "true")
        m = re.search(r"/SigFlags\s+(\d+)", new_val)
        if m:
            newflags = int(m.group(1)) & ~2
            new_val = re.sub(r"/SigFlags\s+\d+", f"/SigFlags {newflags}", new_val)
        doc.xref_set_key(cat, "AcroForm", new_val)


def is_dynamic_xfa(doc):
    """True if this is a dynamic XFA form: its real content is XML that
    only Adobe's own renderer turns into pages at open time. The static
    page content every other renderer (including this tool) sees is just
    Adobe's 'Please wait...' placeholder, so there's nothing real to
    unlock or rasterize.

    /NeedsRendering true is the direct, documented signal for this. A
    hybrid XFA form (XFA data alongside a real static AcroForm fallback,
    the common case from Acrobat) doesn't set it and has actual widgets,
    so it's left alone -- we only fall back to "has XFA but no widgets at
    all" as a second signal for forms that omit the flag.
    """
    cat = doc.pdf_catalog()
    typ, val = doc.xref_get_key(cat, "NeedsRendering")
    if typ == "bool" and val == "true":
        return True

    af_xref, inline = _acroform_target(doc)
    if af_xref is not None:
        typ, _ = doc.xref_get_key(af_xref, "XFA")
        has_xfa = typ not in (None, "null")
    elif inline is not None:
        has_xfa = "/XFA" in inline
    else:
        has_xfa = False

    if not has_xfa:
        return False
    return not any(True for page in doc for _ in page.widgets())


def clean_catalog(doc):
    """Strip Adobe Reader-extension / certification cruft at the document
    level: usage rights (UR3), DocMDP certification, Reader-extension
    markers."""
    for key in ("Perms", "Extensions"):
        delete_catalog_key(doc, key)
    clean_acroform(doc)


def unlock_field_chain(doc, xref, seen=None):
    """Remove the /Lock dictionary and clear the ReadOnly flag bit on a
    field object and every ancestor in its /Parent chain (radio groups /
    shared fields keep their lock on the parent, not each kid)."""
    if seen is None:
        seen = set()
    if xref in seen:
        return
    seen.add(xref)

    typ, _ = doc.xref_get_key(xref, "Lock")
    if typ not in (None, "null"):
        doc.xref_set_key(xref, "Lock", "null")

    typ, val = doc.xref_get_key(xref, "Ff")
    if typ == "int":
        newval = int(val) & ~1
        if newval != int(val):
            doc.xref_set_key(xref, "Ff", str(newval))

    typ, val = doc.xref_get_key(xref, "Parent")
    if typ == "xref":
        parent_xref = _split_ref(val)
        if parent_xref is not None:
            unlock_field_chain(doc, parent_xref, seen)


def save_stripped(doc, output_path):
    """Write out with encryption fully removed and the file rebuilt clean."""
    doc.save(
        output_path,
        garbage=4,
        deflate=True,
        clean=True,
        encryption=pymupdf.PDF_ENCRYPT_NONE,
    )
