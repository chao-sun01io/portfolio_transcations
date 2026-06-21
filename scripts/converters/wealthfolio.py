"""Convert canonical records to Wealthfolio activity CSV.

Wealthfolio columns:
    date,symbol,instrumentType,quantity,activityType,unitPrice,currency,fee,amount,fxRate,subtype

See reference/wealthfolio.md and
https://wealthfolio.app/docs/concepts/activity-types/
"""

import csv

import symbols

FORMAT = "wealthfolio"

FIELDS = [
    "date", "symbol", "instrumentType", "quantity", "activityType",
    "unitPrice", "currency", "fee", "amount", "fxRate", "subtype", "comment",
]

# Canonical action -> Wealthfolio activityType.
ACTION_TO_ACTIVITY = {
    "BUY": "BUY",
    "SELL": "SELL",
    "TRANSFER_IN": "TRANSFER_IN",
    "TRANSFER_OUT": "TRANSFER_OUT",
    "DIVIDEND": "DIVIDEND",
    "INTEREST": "INTEREST",
    "DEPOSIT": "DEPOSIT",
    "WITHDRAWAL": "WITHDRAWAL",
    "SPLIT": "SPLIT",
    "FEE": "FEE",
    "TAX": "TAX",
}

# Activities driven by a quantity/price of a security.
SECURITY_ACTIVITIES = {"BUY", "SELL", "TRANSFER_IN", "TRANSFER_OUT", "SPLIT"}
# Cash activities tied to a specific holding (carry symbol + amount).
SECURITY_CASH_ACTIVITIES = {"DIVIDEND", "TAX"}
# Account-level cash activities (amount only, no symbol).
CASH_ACTIVITIES = {"INTEREST", "DEPOSIT", "WITHDRAWAL", "FEE"}


def _abs(value):
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return ""


def convert_row(row: dict):
    """Return a Wealthfolio dict for a canonical row, or None to skip it."""
    activity = ACTION_TO_ACTIVITY.get(row.get("action", ""))
    if activity is None:
        return None  # OTHER / unmapped: skip with caller's awareness

    out = {f: "" for f in FIELDS}
    out["date"] = row.get("date", "")
    out["instrumentType"] = "EQUITY"
    out["currency"] = row.get("currency", "") or "CNY"
    out["activityType"] = activity
    out["fee"] = _abs(row.get("fee"))
    out["subtype"] = row.get("subtype", "")
    out["comment"] = row.get("note", "")

    if activity in SECURITY_ACTIVITIES:
        out["symbol"] = symbols.to_yahoo(row.get("symbol", ""))
        out["quantity"] = _abs(row.get("quantity"))
        out["unitPrice"] = row.get("price", "")
        # amount left blank; Wealthfolio computes from qty * price.
    elif activity in SECURITY_CASH_ACTIVITIES:
        out["symbol"] = symbols.to_yahoo(row.get("symbol", ""))
        out["amount"] = _abs(row.get("cash_flow"))
    else:  # account-level cash (canonical symbol is already $CASH)
        out["symbol"] = row.get("symbol", "")
        out["amount"] = _abs(row.get("cash_flow"))

    return out


def write(rows, out_path):
    """Write rows to a Wealthfolio CSV. Returns (written, skipped)."""
    written = 0
    skipped = 0
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            conv = convert_row(row)
            if conv is None:
                skipped += 1
                continue
            writer.writerow(conv)
            written += 1
    return written, skipped
