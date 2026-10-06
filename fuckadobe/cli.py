import argparse
import os
import sys

import pymupdf

from .normal import unlock
from .nuclear import flatten_and_rebuild
from .pdfutil import is_dynamic_xfa, open_pdf, save_stripped, warn
from .portfolio import collapse_portfolio, is_portfolio


_OUTPUT_SUFFIXES = ("_deadobe", "_nuked")


def _derive_output(first_input, mode):
    base, _ext = os.path.splitext(first_input)
    suffix = "_nuked" if mode == "nuclear" else "_deadobe"
    return f"{base}{suffix}.pdf"


def _pdfs_in_dir(directory):
    """Every PDF directly inside `directory` (no recursion), sorted by name.
    Skips our own previous outputs so re-running doesn't re-process them."""
    paths = []
    for name in sorted(os.listdir(directory), key=str.lower):
        path = os.path.join(directory, name)
        base, ext = os.path.splitext(name)
        if (
            os.path.isfile(path)
            and ext.lower() == ".pdf"
            and not base.endswith(_OUTPUT_SUFFIXES)
        ):
            paths.append(path)
    return paths


def build_parser():
    p = argparse.ArgumentParser(
        prog="fuckadobe",
        description=(
            "Strip Adobe security theater from PDFs. Normal mode unlocks "
            "locked fields/signatures in place; nuclear mode rasterizes "
            "every page and rebuilds a fresh, unsigned AcroForm on top, "
            "pre-filled with the original field values. Portfolios "
            "(embedded-file collections) are always collapsed into one "
            "conjoined PDF first."
        ),
    )
    p.add_argument(
        "input", nargs="+",
        help="input PDF(s); multiple files are concatenated in order. "
             "Pass a directory (e.g. ./) instead to process every PDF in it "
             "separately (no recursion, no concatenation).",
    )
    p.add_argument("-o", "--output", help="output path (default: <first input>_deadobe.pdf / _nuked.pdf)")
    p.add_argument(
        "-m", "--mode", choices=["normal", "nuclear"], default="normal",
        help="normal: unlock existing fields/signatures in place (default). "
             "nuclear: flatten every page to an image and re-add unsigned fields "
             "pre-filled with their original values.",
    )
    p.add_argument("-p", "--password", help="password to open an encrypted input PDF")
    p.add_argument("--dpi", type=int, default=200, help="render resolution for nuclear mode (default: 200)")
    p.add_argument(
        "--no-collapse-portfolio", action="store_true",
        help="don't collapse PDF portfolios (embedded files); error out instead if one is found",
    )
    return p


def _load_one(path, args):
    doc = open_pdf(path, args.password)
    if is_dynamic_xfa(doc):
        raise SystemExit(
            f"'{path}' is a dynamic XFA form: its real content is XML that "
            "only Adobe's own renderer turns into pages. What every other "
            "viewer (and this tool) sees as the page is just Adobe's "
            "'Please wait...' placeholder, so there's nothing real here to "
            "unlock or rasterize."
        )
    if is_portfolio(doc):
        if args.no_collapse_portfolio:
            raise SystemExit(
                f"'{path}' is a PDF portfolio with embedded files; "
                f"re-run without --no-collapse-portfolio to collapse it"
            )
        collapsed = collapse_portfolio(doc, source_name=path)
        doc.close()
        return collapsed
    return doc


def _count_signature_fields(doc):
    return sum(
        1
        for page in doc
        for w in page.widgets() or []
        if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE
    )


def _run(inputs, output, args):
    docs = [_load_one(path, args) for path in inputs]

    if args.mode == "nuclear" and len(docs) > 1:
        # Nuke each input on its own so filled signatures are rendered into
        # their pages before merging (merging first would drop them).
        working = pymupdf.open()
        for d in docs:
            nuked = flatten_and_rebuild(d, dpi=args.dpi)
            d.close()
            working.insert_pdf(nuked)
            nuked.close()
    elif len(docs) == 1:
        working = docs[0]
    else:
        for path, d in zip(inputs, docs):
            n = _count_signature_fields(d)
            if n:
                warn(
                    f"'{path}' has {n} certificate/signature field(s). "
                    "Concatenating PDFs rewrites the file, which invalidates "
                    "signatures, and the merged output does not carry the "
                    "signature fields over: they will be cleared."
                )
        working = pymupdf.open()
        for d in docs:
            working.insert_pdf(d)
            d.close()

    if working.page_count == 0:
        raise SystemExit("no pages to write: input is empty after processing")

    if args.mode == "normal":
        result = unlock(working)
    elif len(docs) > 1:
        result = working  # already nuked per input
    else:
        result = flatten_and_rebuild(working, dpi=args.dpi)

    output = output or _derive_output(inputs[0], args.mode)
    save_stripped(result, output)
    print(f"wrote {output} ({result.page_count} pages)")


def _run_directory(directory, args):
    paths = _pdfs_in_dir(directory)
    if not paths:
        raise SystemExit(f"no PDF files found in '{directory}'")
    failures = 0
    for path in paths:
        try:
            _run([path], None, args)
        except SystemExit as e:
            # One bad file (dynamic XFA, wrong password, ...) shouldn't abort
            # the rest of the batch.
            failures += 1
            print(f"skipped {path}: {e}", file=sys.stderr)
        except Exception as e:
            failures += 1
            print(f"skipped {path}: {type(e).__name__}: {e}", file=sys.stderr)
    print(f"processed {len(paths) - failures}/{len(paths)} PDF(s) in '{directory}'")
    if failures:
        raise SystemExit(1)


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if any(os.path.isdir(path) for path in args.input):
        if len(args.input) > 1:
            parser.error("a directory input must be the only input")
        if args.output:
            parser.error("-o/--output can't be used with a directory input; "
                         "each file gets its own <name>_deadobe.pdf / _nuked.pdf")
        _run_directory(args.input[0], args)
        return

    _run(args.input, args.output, args)


if __name__ == "__main__":
    main()
