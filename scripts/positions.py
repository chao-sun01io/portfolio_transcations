"""Export-time opening-balance synthesis for partial broker history.

When a broker only exports the last few years, the canonical record contains
disposals (SELL / TRANSFER_OUT) for shares whose acquisitions predate the window.
Exporting those as-is produces negative positions. `synthesize_openings` rebuilds
a plausible opening portfolio so positions never go negative:

  - auto guard (always): inject the minimal opening TRANSFER_IN per symbol so the
    running position never drops below zero;
  - rollup (optional `opening_date`): collapse all pre-date activity per symbol
    into an opening holding plus one combined cash DEPOSIT/WITHDRAWAL per currency.

Opening lots are priced from transaction prices so they introduce ~zero P&L (no
external price feed exists). This is purely an export transform; canonical records
are never modified.
"""

import datetime as dt
from collections import defaultdict, deque

import schema

PLUS = {"BUY", "TRANSFER_IN"}
MINUS = {"SELL", "TRANSFER_OUT"}
EPS = 1e-9


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _day_before(date_str: str) -> str:
    try:
        d = dt.date.fromisoformat(date_str)
        return (d - dt.timedelta(days=1)).isoformat()
    except ValueError:
        return date_str


def _sort_key(row):
    return (row.get("date", ""), row.get("time", ""))


def synthesize_openings(rows, opening_date=None):
    """Return (out_rows, report).

    out_rows = synthetic opening rows + retained canonical rows, sorted by date.
    report = counts for the caller to print.
    """
    rows = sorted(rows, key=_sort_key)
    if not rows:
        return [], {"opening_lots": 0, "guard_symbols": 0, "deposits": 0,
                    "guard_shares": 0.0}

    account = rows[0].get("account", "")
    open_date = opening_date or _day_before(rows[0]["date"])

    # symbol -> display name, symbol -> currency, symbol -> last known price
    sym_name, sym_ccy, sym_last_price = {}, {}, {}
    for r in rows:
        s = r["symbol"]
        if r.get("name"):
            sym_name[s] = r["name"]
        sym_ccy.setdefault(s, r.get("currency", ""))
        p = _num(r.get("price"))
        if p > EPS:
            sym_last_price[s] = p  # ascending order -> latest wins

    # 1. Rollup: split pre-date activity out of the export stream.
    kept = []
    pre_qty = defaultdict(float)        # symbol -> net pre-date quantity
    pre_cash = defaultdict(float)       # currency -> net pre-date cash flow
    for r in rows:
        if opening_date and r["date"] < opening_date:
            a = r["action"]
            q = _num(r.get("quantity"))
            if a in PLUS:
                pre_qty[r["symbol"]] += q
            elif a in MINUS:
                pre_qty[r["symbol"]] -= q
            pre_cash[r.get("currency", "")] += _num(r.get("cash_flow"))
        else:
            kept.append(r)

    opening_qty = {s: q for s, q in pre_qty.items() if q > EPS}
    rollup_symbols = set(opening_qty)

    # 2. Auto guard: bump openings so the END-OF-DAY position never goes below
    #    zero. Same-day events are netted first, so a transient intraday dip from
    #    settlement-timing (e.g. a transfer-out stamped 00:00:00 ahead of the
    #    matching buy on the same day) is tolerated and its negative is retained.
    day_delta = defaultdict(lambda: defaultdict(float))  # symbol -> date -> delta
    for r in kept:
        a = r["action"]
        if a not in PLUS and a not in MINUS:
            continue
        q = _num(r.get("quantity"))
        day_delta[r["symbol"]][r["date"]] += q if a in PLUS else -q
    guard_symbols = 0
    for s, deltas in day_delta.items():
        bal = opening_qty.get(s, 0.0)
        minbal = bal
        for d in sorted(deltas):
            bal += deltas[d]
            if bal < minbal:
                minbal = bal
        if minbal < -EPS:
            opening_qty[s] = opening_qty.get(s, 0.0) + (-minbal)
            guard_symbols += 1

    # 3. Price each opening lot for ~zero P&L via FIFO (opening lot consumed
    #    first by later disposals).
    open_rows = []
    for s, qty in opening_qty.items():
        price = _opening_price(s, qty, kept, sym_last_price)
        open_rows.append(_make_open_row(account, open_date, s,
                                        sym_name.get(s, s), qty, price,
                                        sym_ccy.get(s, "")))

    # 4. Combined cash seed per currency (rollup only).
    deposits = 0
    if opening_date:
        for ccy, amount in pre_cash.items():
            if abs(amount) <= EPS:
                continue
            open_rows.append(_make_cash_row(account, open_date, ccy, amount))
            deposits += 1

    out_rows = sorted(open_rows + kept, key=_sort_key)
    report = {
        "opening_lots": len(open_rows) - deposits,
        "guard_symbols": guard_symbols,
        "rollup_symbols": len(rollup_symbols),
        "deposits": deposits,
        "guard_shares": sum(opening_qty.values()),
    }
    return out_rows, report


def _opening_price(symbol, qty, kept, sym_last_price):
    """Blended unit price: disposed opening shares at their sell prices (zero
    realized P&L), residual held shares at the last known price (~zero
    unrealized)."""
    queue = deque()
    opening_lot = [qty, None]            # price None marks the opening lot
    queue.append(opening_lot)
    disposed_qty = 0.0
    disposed_cost = 0.0
    for r in kept:
        if r["symbol"] != symbol:
            continue
        a = r["action"]
        if a in PLUS:
            queue.append([_num(r.get("quantity")), _num(r.get("price"))])
        elif a in MINUS:
            need = _num(r.get("quantity"))
            sell_price = _num(r.get("price"))
            while need > EPS and queue:
                lot = queue[0]
                take = min(need, lot[0])
                if lot is opening_lot:
                    disposed_qty += take
                    disposed_cost += take * sell_price
                lot[0] -= take
                need -= take
                if lot[0] <= EPS:
                    queue.popleft()
    residual = qty - disposed_qty
    residual_price = sym_last_price.get(symbol, 0.0)
    total_cost = disposed_cost + max(residual, 0.0) * residual_price
    return round(total_cost / qty, 6) if qty > EPS else 0.0


def _blank_row():
    return {c: "" for c in schema.COLUMNS}


def _make_open_row(account, date, symbol, name, qty, price, currency):
    row = _blank_row()
    row.update({
        "txn_id": f"opening-{account}-{symbol}",
        "account": account,
        "date": date,
        "time": "00:00:00",
        "symbol": symbol,
        "name": name,
        "type_raw": "OPENING",
        "action": "TRANSFER_IN",
        "subtype": "OPENING",
        "quantity": qty,
        "price": price,
        "cash_flow": 0,
        "gross_amount": round(qty * price, 6),
        "fee": 0,
        "currency": currency,
        "note": "synthesized opening balance",
        "source_file": "(synthesized)",
    })
    return row


def _make_cash_row(account, date, currency, amount):
    row = _blank_row()
    row.update({
        "txn_id": f"opening-cash-{account}-{currency}",
        "account": account,
        "date": date,
        "time": "00:00:00",
        "type_raw": "OPENING",
        "action": "DEPOSIT" if amount > 0 else "WITHDRAWAL",
        "subtype": "OPENING",
        "cash_flow": round(amount, 6),
        "currency": currency,
        "note": "synthesized opening cash balance",
        "source_file": "(synthesized)",
    })
    return row
