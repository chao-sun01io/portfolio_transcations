"""Shared helpers: data paths and canonical CSV read/write."""

import csv
import os

import schema

# Data lives in the working directory (or $PORTFOLIO_DATA_DIR), kept separate
# from the skill so the skill can be installed/shared independently.
DATA_ROOT = os.environ.get("PORTFOLIO_DATA_DIR") or os.getcwd()
INPUT_DIR = os.path.join(DATA_ROOT, "input")
TRANSACTIONS_DIR = os.path.join(DATA_ROOT, "transactions")
OUTPUT_DIR = os.path.join(DATA_ROOT, "output")


def canonical_path(account: str) -> str:
    return os.path.join(TRANSACTIONS_DIR, f"{account}.csv")


def read_canonical(account: str):
    """Return the list of canonical row dicts for an account ([] if none)."""
    path = canonical_path(account)
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _sort_key(row):
    return (row.get("date", ""), row.get("time", ""), row.get("symbol", ""))


def write_canonical_rows(path: str, rows, sort: bool = True):
    """Write canonical rows to `path` in the canonical CSV schema."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if sort:
        rows = sorted(rows, key=_sort_key)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=schema.COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in schema.COLUMNS})
    return path


def write_canonical(account: str, rows):
    """Write canonical rows (sorted by date/time/symbol) to the account CSV."""
    return write_canonical_rows(canonical_path(account), rows)
