"""Nuclear mode: rasterize every page so no original PDF object (locked
or not) survives, then rebuild a fresh AcroForm on top with the same
fields back in place, blank and unsigned."""

import pymupdf

from .pdfutil import clean_catalog, warn

# Field flag bits that only make sense on a filled-in / signed field.
# Cleared on every recreated widget so nothing nuclear-mode rebuilds looks
# pre-completed. (bit1 ReadOnly)
_READONLY_BIT = 1


def _capture_fields(doc):
    """Collect field metadata per page before rasterizing, since widgets
    disappear once we throw away the original page objects."""
    fields_by_page = []
    for page in doc:
        specs = []
        for widget in page.widgets() or []:
            specs.append(
                {
                    "name": widget.field_name,
                    "type": widget.field_type,
                    "type_string": widget.field_type_string,
                    "rect": widget.rect,
                    "flags": widget.field_flags & ~_READONLY_BIT,
                    "choice_values": widget.choice_values,
                    "text_font": widget.text_font,
                    "text_fontsize": widget.text_fontsize,
                    "border_width": widget.border_width,
                }
            )
        fields_by_page.append(specs)
    return fields_by_page


def _rasterize(doc, dpi):
    """Render every page to a PNG image, returning (rect, png_bytes) pairs."""
    rendered = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        rendered.append((page.rect, pix.tobytes("png")))
    return rendered


def _add_widget(page, spec):
    widget = pymupdf.Widget()
    widget.field_name = spec["name"]
    widget.field_type = spec["type"]
    widget.rect = spec["rect"]
    widget.field_flags = spec["flags"]
    if spec["text_font"]:
        widget.text_font = spec["text_font"]
    if spec["text_fontsize"]:
        widget.text_fontsize = spec["text_fontsize"]
    if spec["border_width"]:
        widget.border_width = spec["border_width"]

    if spec["type"] in (
        pymupdf.PDF_WIDGET_TYPE_COMBOBOX,
        pymupdf.PDF_WIDGET_TYPE_LISTBOX,
    ) and spec["choice_values"]:
        widget.choice_values = spec["choice_values"]

    if spec["type"] == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
        widget.field_value = False
    elif spec["type"] == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
        widget.field_value = False
    elif spec["type"] == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
        pass  # leave unset -> unsigned
    else:
        widget.field_value = ""

    page.add_widget(widget)


def flatten_and_rebuild(doc, dpi=200):
    fields_by_page = _capture_fields(doc)
    rendered_pages = _rasterize(doc, dpi)
    metadata = doc.metadata

    new_doc = pymupdf.open()
    for (rect, png_bytes), specs in zip(rendered_pages, fields_by_page):
        page = new_doc.new_page(width=rect.width, height=rect.height)
        page.insert_image(page.rect, stream=png_bytes)
        for spec in specs:
            try:
                _add_widget(page, spec)
            except Exception as e:
                warn(
                    f"could not recreate field '{spec['name']}' "
                    f"({spec['type_string']}): {e}"
                )

    if metadata:
        clean_meta = {k: v for k, v in metadata.items() if v}
        new_doc.set_metadata(clean_meta)

    clean_catalog(new_doc)
    return new_doc
