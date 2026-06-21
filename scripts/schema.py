"""Canonical internal transaction schema (format- and broker-agnostic).

Defines the per-account canonical CSV columns, the normalized `action`
vocabulary every parser must emit, and the stable `txn_id` used for incremental
dedup. Broker-specific transaction-type mappings do NOT live here — each parser
owns its own mapping (e.g. `parsers/tzzb.py`) so new brokers/markets can define
their own vocabulary without touching this contract.

Keep `reference/canonical.md` (the human-readable companion) in sync with COLUMNS.
"""

import hashlib

# Canonical CSV columns, in order.
COLUMNS = [
    "txn_id",        # stable SHA1 dedup key (see make_txn_id)
    "account",       # account name (inferred from filename or supplied)
    "date",          # trade date, YYYY-MM-DD
    "time",          # trade time, HH:MM:SS ("" if unknown)
    "symbol",        # raw broker code, e.g. 600036 / 01888
    "name",          # security name as shown by the broker
    "type_raw",      # ORIGINAL broker transaction-type string (never lost)
    "action",        # normalized action (see ACTIONS)
    "subtype",       # normalized subtype, e.g. MARGIN ("" if none)
    "quantity",      # shares/units
    "price",         # unit price
    "cash_flow",     # signed cash impact (negative = money out)
    "gross_amount",  # gross trade amount (unsigned)
    "fee",           # total fees/commission
    "currency",      # CNY / HKD / ... detected from the market
    "note",          # broker remark (备注)
    "source_file",   # basename of the input file this row came from
]

# Sentinel symbol for pure cash movements that have no underlying security.
# Parsers set `symbol` to this for CASH_ACTIONS (currency is still detected from
# the raw broker code first, so e.g. an HKD levy stays HKD).
CASH_SYMBOL = "$CASH"

# Actions that are account-level cash movements (no security) -> CASH_SYMBOL.
# DIVIDEND / TAX are deliberately excluded: they stay tied to their security.
CASH_ACTIONS = {"DEPOSIT", "WITHDRAWAL", "INTEREST", "FEE"}

# Actions that move SECURITIES (or are unclassified) and so do NOT change the
# account cash balance, even though the broker may stamp a book value in
# cash_flow. e.g. inter-account share transfers (股份转入/转出), stock splits.
NON_CASH_ACTIONS = {"TRANSFER_IN", "TRANSFER_OUT", "SPLIT", "OTHER"}

# Normalized action vocabulary every parser maps its broker types into.
ACTIONS = {
    "BUY",
    "SELL",
    "TRANSFER_IN",
    "TRANSFER_OUT",
    "DIVIDEND",
    "INTEREST",
    "DEPOSIT",
    "WITHDRAWAL",
    "SPLIT",
    "FEE",
    "TAX",
    "OTHER",
}


def make_txn_id(row: dict, occurrence: int = 0) -> str:
    """Stable dedup key for a canonical row.

    Built from the immutable identifying fields so re-ingesting the same export
    yields identical ids. `occurrence` distinguishes rows that are otherwise
    byte-for-byte identical within a single source file (e.g. several same-day
    trades stamped 00:00:00); without it those genuine repeats would collapse
    into one and be silently lost. Because broker exports are append-only in
    chronological order, the per-tuple occurrence index is stable across
    re-exports, keeping ingestion idempotent.
    """
    parts = [
        str(row.get("account", "")),
        str(row.get("date", "")),
        str(row.get("time", "")),
        str(row.get("symbol", "")),
        str(row.get("type_raw", "")),
        str(row.get("quantity", "")),
        str(row.get("price", "")),
        str(row.get("cash_flow", "")),
        str(occurrence),
    ]
    key = "|".join(parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()
