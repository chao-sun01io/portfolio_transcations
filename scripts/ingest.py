# /// script
# requires-python = ">=3.10"
# dependencies = ["openpyxl"]
# ///
"""Ingest a broker export into the canonical per-account transactions CSV.

Incremental: existing rows are kept and only new txn_ids are appended, so
re-running on an updated export is safe and idempotent.

Usage:
    uv run python ingest.py <input-file> [--account NAME]

The account is inferred from the filename when --account is omitted: the
leading "tzzb_" prefix and the extension are stripped
(input/tzzb_huabao.xlsx -> huabao, input/tzzb_huabao-margin.xlsx -> huabao-margin).
"""

import argparse
import os
from collections import Counter

import common
import parsers


def infer_account(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    for prefix in ("tzzb_",):
        if base.startswith(prefix):
            base = base[len(prefix):]
    return base


def main(argv=None):
    ap = argparse.ArgumentParser(description="Ingest a broker export into canonical records.")
    ap.add_argument("input", help="path to the broker export file")
    ap.add_argument("--account", help="account name (default: inferred from filename)")
    args = ap.parse_args(argv)

    if not os.path.exists(args.input):
        ap.error(f"input file not found: {args.input}")

    account = args.account or infer_account(args.input)
    parser = parsers.detect_parser(args.input)
    if parser is None:
        ap.error(f"no parser recognizes {args.input!r}")

    source_file = os.path.basename(args.input)
    print(f"ingesting {source_file} -> account {account!r} (parser: {parser.NAME})")

    existing = common.read_canonical(account)
    seen = {row["txn_id"] for row in existing}

    added = 0
    skipped = 0
    unknown = Counter()          # unmapped type_raw -> count (this file)
    unknown_example = {}         # unmapped type_raw -> "date symbol name"
    new_rows = []
    for rec in parser.parse(args.input, account, source_file):
        if rec["action"] == "OTHER":
            t = rec["type_raw"]
            unknown[t] += 1
            unknown_example.setdefault(
                t, f"{rec['date']} {rec['symbol']} {rec['name']}".strip())
        if rec["txn_id"] in seen:
            skipped += 1
            continue
        seen.add(rec["txn_id"])
        new_rows.append(rec)
        added += 1

    if new_rows:
        path = common.write_canonical(account, existing + new_rows)
        print(f"wrote {path}")
    else:
        print("no new transactions; canonical file unchanged")

    print(f"summary: added {added}, skipped {skipped} (duplicates), "
          f"unknown-type {sum(unknown.values())}; total now {len(existing) + added}")

    if unknown:
        print("\nUNMAPPED transaction types (stored as action=OTHER, skipped on "
              "export). Ask the user how each should map, then add it to "
              f"TYPE_TO_ACTION in the parser ({parser.NAME}) and re-ingest:")
        for t, n in unknown.most_common():
            print(f"  - {t!r}  x{n}  e.g. {unknown_example[t]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
