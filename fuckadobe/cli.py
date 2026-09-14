import argparse
import os
import sys

import pymupdf

from .normal import unlock
from .nuclear import flatten_and_rebuild
from .pdfutil import is_dynamic_xfa, open_pdf, save_stripped, warn
from .portfolio import collapse_portfolio, is_portfolio


def _derive_output(first_input, mode):
    base, _ext = os.path.splitext(first_input)
    suffix = "_nuked" if mode == "nuclear" else "_deadobe"
    return f"{base}{suffix}.pdf"


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
    p.add_argument("input", nargs="+", help="input PDF(s); multiple files are concatenated in order")
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


def main(argv=None):
    args = build_parser().parse_args(argv)

    docs = [_load_one(path, args) for path in args.input]

    if len(docs) == 1:
        working = docs[0]
    else:
        working = pymupdf.open()
        for d in docs:
            working.insert_pdf(d)
            d.close()

    if working.page_count == 0:
        raise SystemExit("no pages to write: input is empty after processing")

    if args.mode == "normal":
        result = unlock(working)
    else:
        result = flatten_and_rebuild(working, dpi=args.dpi)

    output = args.output or _derive_output(args.input[0], args.mode)
    save_stripped(result, output)
    print(f"wrote {output} ({result.page_count} pages)")


if __name__ == "__main__":
    main()
