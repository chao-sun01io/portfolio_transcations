# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Compute current holdings (positions + cash) from an account's canonical records.

Usage:
    uv run python holdings.py --account NAME [--out FILE]
        [--opening-date YYYY-MM-DD] [--no-opening-guard]

Replays the canonical transaction stream:
  - per security: FIFO lots -> quantity still held and the cost basis of those
    remaining lots (avg_cost = cost_basis / quantity);
  - per currency: a $CASH holding whose quantity is the net of every signed
    cash_flow (buys, sells, deposits, dividends, fees, interest, ...).

By default the same opening-balance synthesis used by export.py is applied so
positions/cash don't go negative when the broker only exported recent history
(see positions.py). `--no-opening-guard` replays the raw canonical rows untouched;
`--opening-date D` rolls all pre-D activity into an opening snapshot first.

Default output: output/<account>.holdings.csv.
"""

import argparse
import csv
import os
from collections import defaultdict, deque

import common
import positions
import schema
import symbols

FIELDS = [
    "account", "symbol", "yahoo_symbol", "name", "currency",
    "quantity", "avg_cost", "cost_basis",
]

PLUS = positions.PLUS    # {"BUY", "TRANSFER_IN"}
MINUS = positions.MINUS  # {"SELL", "TRANSFER_OUT"}
EPS = 1e-9


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _sort_key(row):
    return (row.get("date", ""), row.get("time", ""))


def _apply(inv, signed_delta, price):
    """Merge a signed quantity (+ buy / - sell) into a FIFO lot deque.

    Lots are signed and the deque always holds a single sign (long *or* short):
    an event of the opposite sign first covers existing lots from the front, and
    only any remainder opens a new lot. This makes the result independent of
    same-day timestamp ordering (e.g. a disposal stamped 00:00:00 that lands
    before its covering buy on the same day nets out instead of leaving a phantom
    position). A leftover short lot means disposals genuinely exceed known
    acquisitions (partial history).
    """
    d = signed_delta
    while abs(d) > EPS and inv and (inv[0][0] > 0) != (d > 0):
        lot = inv[0]
        take = min(abs(d), abs(lot[0]))
        lot[0] += (1 if lot[0] < 0 else -1) * take
        d += (1 if d < 0 else -1) * take
        if abs(lot[0]) <= EPS:
            inv.popleft()
    if abs(d) > EPS:
        inv.append([d, price])


def compute(rows):
    """Return (holdings, report) from a canonical row stream.

    holdings: list of dicts (FIELDS); cash rows use symbol "$CASH".
    """
    rows = sorted(rows, key=_sort_key)

    # Per-security signed FIFO lots: symbol -> deque of [signed_qty, unit_price].
    lots = defaultdict(deque)
    sym_name, sym_ccy = {}, {}
    cash = defaultdict(float)  # currency -> net cash

    for r in rows:
        sym = r.get("symbol", "")
        ccy = r.get("currency", "")
        action = r.get("action", "")

        # Share transfers / splits carry a book value in cash_flow but move no
        # actual cash, so they must not shift the cash balance.
        if action not in schema.NON_CASH_ACTIONS:
            cash[ccy] += _num(r.get("cash_flow"))

        if sym and sym != schema.CASH_SYMBOL:
            if r.get("name"):
                sym_name[sym] = r["name"]
            sym_ccy.setdefault(sym, ccy)
            q = _num(r.get("quantity"))
            if q > EPS and action in PLUS:
                _apply(lots[sym], q, _num(r.get("price")))
            elif q > EPS and action in MINUS:
                _apply(lots[sym], -q, _num(r.get("price")))

    oversold = []  # symbols left net-short after replay (partial history)
    excluded = []  # held codes that don't resolve to a real market
    holdings = []
    for sym in sorted(lots):
        qty = sum(lot[0] for lot in lots[sym])
        if qty < -EPS:
            oversold.append((sym, -qty))
        if qty <= EPS:
            continue
        # Drop subscription/allotment placeholder codes (e.g. 715162): they
        # carry no exchange and the broker never tracks them as a position.
        if not symbols.market_of(sym):
            excluded.append((sym, qty))
            continue
        cost_basis = sum(lot[0] * lot[1] for lot in lots[sym])
        holdings.append({
            "account": rows[0].get("account", "") if rows else "",
            "symbol": sym,
            "yahoo_symbol": symbols.to_yahoo(sym, warn=False),
            "name": sym_name.get(sym, ""),
            "currency": sym_ccy.get(sym, ""),
            "quantity": round(qty, 6),
            "avg_cost": round(cost_basis / qty, 6),
            "cost_basis": round(cost_basis, 6),
        })

    # Cash as $CASH holdings (unit price 1), one per currency with a balance.
    for ccy in sorted(cash):
        bal = cash[ccy]
        if abs(bal) <= EPS:
            continue
        holdings.append({
            "account": rows[0].get("account", "") if rows else "",
            "symbol": schema.CASH_SYMBOL,
            "yahoo_symbol": schema.CASH_SYMBOL,
            "name": "Cash",
            "currency": ccy,
            "quantity": round(bal, 6),
            "avg_cost": 1,
            "cost_basis": round(bal, 6),
        })

    report = {
        "positions": sum(1 for h in holdings if h["symbol"] != schema.CASH_SYMBOL),
        "cash_currencies": sum(1 for h in holdings if h["symbol"] == schema.CASH_SYMBOL),
        "oversold": oversold,
        "excluded": excluded,
    }
    return holdings, report


def write(holdings, out_path):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for h in holdings:
            writer.writerow(h)
    return len(holdings)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compute holdings from canonical records.")
    ap.add_argument("--account", required=True, help="account name")
    ap.add_argument("--out", help="output path (default: output/<account>.holdings.csv)")
    ap.add_argument("--opening-date", metavar="YYYY-MM-DD",
                    help="roll up all activity before this date into an opening snapshot")
    ap.add_argument("--no-opening-guard", action="store_true",
                    help="disable opening synthesis; replay raw canonical rows")
    args = ap.parse_args(argv)

    rows = common.read_canonical(args.account)
    if not rows:
        ap.error(f"no canonical records for account {args.account!r}; run ingest first")

    if not args.no_opening_guard:
        rows, _ = positions.synthesize_openings(rows, args.opening_date)

    holdings, report = compute(rows)

    out_path = args.out or os.path.join(common.OUTPUT_DIR, f"{args.account}.holdings.csv")
    n = write(holdings, out_path)
    print(f"wrote {out_path}: {n} holdings "
          f"({report['positions']} positions, {report['cash_currencies']} cash)")
    if report["oversold"]:
        syms = ", ".join(f"{s} ({need:g})" for s, need in report["oversold"][:8])
        print(f"warning: {len(report['oversold'])} disposals exceeded known "
              f"acquisitions (partial history): {syms}")
    if report["excluded"]:
        syms = ", ".join(f"{s} ({q:g})" for s, q in report["excluded"])
        print(f"excluded {len(report['excluded'])} non-market codes "
              f"(subscription/allotment placeholders): {syms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
