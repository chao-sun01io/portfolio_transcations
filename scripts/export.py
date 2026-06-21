# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Export an account's canonical records to an output format.

Usage:
    uv run python export.py --account NAME [--format wealthfolio] [--out FILE]
        [--opening-date YYYY-MM-DD] [--no-opening-guard]

Default output path: output/<account>.<suffix> (e.g. output/huabao.wealthfolio.csv).

By default an opening-balance guard synthesizes the minimal opening holdings so
exported positions never go negative (brokers that only provide recent history
report sells of shares bought before the window). `--opening-date D` additionally
rolls up all pre-D activity into an opening snapshot. `--no-opening-guard` exports
the raw canonical rows untouched. See positions.py.
"""

import argparse
import os

import common
import converters
import positions


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export canonical records to an output format.")
    ap.add_argument("--account", required=True, help="account name")
    ap.add_argument("--format", default="wealthfolio",
                    choices=sorted(converters.CONVERTERS), help="output format")
    ap.add_argument("--out", help="output file path (default: output/<account>.<suffix>)")
    ap.add_argument("--opening-date", metavar="YYYY-MM-DD",
                    help="roll up all activity before this date into an opening snapshot")
    ap.add_argument("--no-opening-guard", action="store_true",
                    help="disable opening synthesis; export raw canonical rows")
    args = ap.parse_args(argv)

    rows = common.read_canonical(args.account)
    if not rows:
        ap.error(f"no canonical records for account {args.account!r}; run ingest first")

    export_rows = rows
    if not args.no_opening_guard:
        export_rows, report = positions.synthesize_openings(rows, args.opening_date)
        print(f"opening synthesis: {report['opening_lots']} opening lots "
              f"({report['guard_symbols']} guard, {report['rollup_symbols']} rollup), "
              f"{report['deposits']} combined cash rows")

    converter = converters.get(args.format)
    out_path = args.out
    if not out_path:
        suffix = converters.SUFFIXES[args.format]
        os.makedirs(common.OUTPUT_DIR, exist_ok=True)
        out_path = os.path.join(common.OUTPUT_DIR, f"{args.account}.{suffix}")

    written, skipped = converter.write(export_rows, out_path)
    print(f"wrote {out_path}: {written} rows ({skipped} skipped: unmapped action)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
