# fuckadobe

A small, dependency-light CLI that strips Adobe's security theater out of
PDFs: locked form fields, post-signature field locks, usage-rights/
certification restrictions, and portfolio wrapping that make a perfectly
normal document a pain for any other program (or person) to read and edit.

One dependency: [PyMuPDF](https://pypi.org/project/pymupdf/). No system
binaries, no Poppler, no Ghostscript.

**[Landing page](https://ESAK9781.github.io/adobesucks/)**

## What it does

- **Normal mode** (default) — keeps every field, value, and signature
  exactly as-is, but:
  - removes encryption and owner-password permission restrictions
  - deletes `/Lock` dictionaries on fields (including up the `/Parent`
    chain, so shared/radio-group locks are cleared too)
  - clears the `ReadOnly` flag bit that Adobe sets on fields after a
    signature "locks" them
  - clears the AcroForm `AppendOnly` signature flag so the file stops
    demanding incremental-only updates
  - deletes `/Perms` (UR3 usage rights, DocMDP certification) and
    `/Extensions` (Reader-extension markers) from the document catalog

- **Nuclear mode** (`-m nuclear`) — for when a file is too mangled to trust:
  rasterizes every page to an image, throws away every original PDF object,
  and rebuilds a brand-new document with a fresh AcroForm laid on top —
  same field names, types, and positions, pre-filled with the original
  values, but unsigned.

- **Portfolios** — any PDF portfolio (a collection of embedded files) is
  automatically collapsed into one conjoined PDF: the cover pages plus
  every embedded file (PDF, image, or otherwise) appended in order.
  Anything MuPDF can't render inline gets a placeholder page rather than
  being silently dropped.

- **Multiple inputs** are concatenated, in the order given, before mode
  processing runs — same mechanism as portfolio collapsing.

## Install

```bash
pip install .
```

or for development:

```bash
pip install -e .
```

## Usage

```
fuckadobe INPUT [INPUT ...] [-o OUTPUT] [-m {normal,nuclear}]
                [-p PASSWORD] [--dpi DPI] [--no-collapse-portfolio]
```

Unlock a signed, field-locked form in place:

```bash
fuckadobe locked-contract.pdf
# -> locked-contract_deadobe.pdf
```

Nuke a file that's beyond trusting and get a clean, refillable copy with
the original values intact:

```bash
fuckadobe mangled-form.pdf -m nuclear --dpi 300
# -> mangled-form_nuked.pdf
```

Collapse a portfolio and merge in an extra cover sheet:

```bash
fuckadobe cover.pdf case-portfolio.pdf -o case-combined.pdf
```

Open a PDF that needs a password first:

```bash
fuckadobe encrypted.pdf -p correct-horse-battery-staple
```

## Limitations

- This does not crack passwords you don't know — a PDF that requires a
  user password to *open* still needs `-p` with the correct password.
  It only removes the after-the-fact restrictions Adobe layers on top
  once a file is open (owner-password permissions, field locks,
  certification/usage-rights extensions).
- Nuclear mode is intentionally lossy: it's a raster of the page plus a
  freshly built form layer, not a byte-faithful copy. Some exotic widget
  types (e.g. certain signature appearances on older readers) may not be
  recreatable and are skipped with a warning rather than failing the run.
- Non-PDF, non-image attachments inside a portfolio can't be rendered
  inline (no extra dependencies for arbitrary format conversion) and are
  replaced with a placeholder page naming the file.

## License

MIT
