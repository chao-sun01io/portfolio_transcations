---
name: portfolio-transactions
description: >-
  Convert broker transaction exports / statements into a canonical per-account
  transactions record and export to other formats (e.g. Wealthfolio CSV). Use
  when the user wants to ingest a brokerage export (xlsx), build or incrementally
  update their transactions history, or convert transactions to another format.
---

# Portfolio Transactions

A deterministic pipeline that turns broker exports into a canonical internal
transactions schema (one CSV per account) and exports them to other formats.
All work is done by the Python scripts in `scripts/` — run them, don't hand-edit
the data. Recommended: `uv run <script>` (the entry scripts carry PEP 723 inline
deps, so uv auto-installs `openpyxl` — no setup). uv is optional: with `openpyxl`
installed (`pip install -r requirements.txt`) you can use `python <script>`
instead. Run from your data directory (or set `$PORTFOLIO_DATA_DIR`).

## Layout

- `input/` — raw broker exports (e.g. `tzzb_huabao.xlsx`). `tzzb` = 同花顺投资账本
  (Tonghuashun Investment Ledger), the source app these xlsx files are exported from.
- `transactions/<account>.csv` — canonical records, one file per account.
- `output/<account>.<format>` — generated exports.
- `reference/canonical.md` — canonical schema reference.
- `reference/wealthfolio.md` — Wealthfolio output spec.

Data dirs (`input/`, `transactions/`, `output/`) live in the working directory
(or `$PORTFOLIO_DATA_DIR`), separate from the skill so it can be shared/installed
independently.

## 1. Ingest (build / incrementally update)

```
uv run .claude/skills/portfolio-transactions/scripts/ingest.py <input-file> [--account NAME]
```

- The account is **inferred from the filename** when `--account` is omitted: the
  `tzzb_` prefix and extension are stripped (`input/tzzb_huabao-margin.xlsx` → `huabao-margin`).
- The parser is auto-detected from the file (registry in `scripts/parsers/`).
- **Incremental & idempotent**: existing rows are kept; only rows with a new
  `txn_id` are appended. Re-running on the same or an updated export is safe.
- Prints `added N, skipped M (duplicates), unknown-type K`.

### Unmapped transaction types

When ingest finds a transaction type it doesn't recognize, it stores the row
(with `type_raw` preserved) as `action=OTHER` and lists the unmapped types at the
end of its output, e.g.:

```
UNMAPPED transaction types (...):
  - '调帐转入'  x2  e.g. 2025-08-19 082626 ...
```

**Do not guess these mappings.** When the summary reports any unmapped types,
**ask the user in chat** how each one should map (BUY / SELL / TRANSFER_IN /
TRANSFER_OUT / DIVIDEND / INTEREST / DEPOSIT / WITHDRAWAL / SPLIT / FEE / TAX, or
leave as OTHER). Then add the agreed mapping to that broker's `TYPE_TO_ACTION` in
its parser module (e.g. `scripts/parsers/tzzb.py`) and re-ingest. Leave a type as
`OTHER` only if the user says so; `OTHER` rows are skipped on export.

## 2. Export

```
uv run .claude/skills/portfolio-transactions/scripts/export.py --account NAME \
    [--format wealthfolio] [--out FILE] [--opening-date YYYY-MM-DD] [--no-opening-guard]
```

- Default output: `output/<account>.wealthfolio.csv`. (The canonical record is
  already in `transactions/<account>.csv`.)
- Wealthfolio mapping: codes → Yahoo symbols (`600036.SS`, `000657.SZ`,
  `1888.HK`), currency per market (CNY/HKD); BUY/SELL/TRANSFER_IN carry
  quantity + unitPrice (+ fee, amount left blank for Wealthfolio to compute);
  DEPOSIT/WITHDRAWAL/DIVIDEND/INTEREST carry `amount`; margin trades get
  `subtype=MARGIN`. Rows with unmapped actions are skipped (and counted).
- `fxRate` is left blank by default. For HKD securities in a CNY-base account you
  can fill it with the HKD→CNY rate if you want Wealthfolio to convert.

### Opening-balance synthesis (avoiding negative positions)

Brokers that only provide recent statements report sells of shares bought before
the window, which would make positions go negative on import. Export handles this
(see `scripts/positions.py`); the transform is **export-only** — canonical records
are never modified:

- **Auto guard (default, always on):** per symbol, the minimal opening
  `TRANSFER_IN` is injected so the running position never goes below zero.
- **`--opening-date D` (rollup):** all activity before `D` is collapsed into
  opening holdings plus one combined `DEPOSIT`/`WITHDRAWAL` per currency (seeding
  the opening cash balance); only rows on/after `D` are exported individually.
- **`--no-opening-guard`:** disables synthesis and exports the raw canonical rows.
- Synthesized rows are priced from transaction prices for ~zero P&L and are marked
  `subtype=OPENING` with `source_file=(synthesized)`.

## 3. Holdings

```
uv run .claude/skills/portfolio-transactions/scripts/holdings.py --account NAME \
    [--out FILE] [--opening-date YYYY-MM-DD] [--no-opening-guard]
```

Replays the canonical stream into a current snapshot at `output/<account>.holdings.csv`:

- **Per security:** short-covering FIFO lots → `quantity` still held and the
  `cost_basis` of those remaining lots (`avg_cost = cost_basis / quantity`). The
  FIFO nets correctly regardless of same-day timestamp order (a disposal stamped
  `00:00:00` before its covering buy doesn't leave a phantom position). This is
  raw acquisition cost, *not* the broker's 摊薄成本 (diluted cost). Subscription/
  allotment placeholder codes that resolve to no exchange (e.g. `715162`) are
  excluded and reported.
- **Per currency:** a `$CASH` holding whose `quantity` is the net `cash_flow` of
  the cash-moving actions only. Share transfers / splits (`schema.NON_CASH_ACTIONS`)
  are excluded: a broker stamps an inter-account share transfer (股份转入/转出)
  with its book value, but no money moves. Negative cash is meaningful — e.g.
  margin debt in a 两融 account, or an FX/partial-history gap.
- Uses the **same opening synthesis as export** (guard on by default) so positions
  don't go negative on partial history; `--opening-date` / `--no-opening-guard`
  behave as in export. Disposals that still exceed known acquisitions are reported.

## Schema

See `reference/canonical.md`. The column list lives in `scripts/schema.py`
(`COLUMNS`) — the single source of truth.

## Extending

- **New broker**: add a module in `scripts/parsers/` exposing `NAME`,
  `matches(path)`, `parse(path, account, source_file)`, and its own
  `TYPE_TO_ACTION` mapping (each broker owns its transaction-type vocabulary;
  `schema.py` only defines the shared canonical contract). Register it in
  `scripts/parsers/__init__.py` (`PARSERS`). The parser must emit rows whose
  `action` is one of `schema.ACTIONS` and set `subtype` (e.g. `MARGIN`).
- **New output format**: add a module in `scripts/converters/` exposing `FORMAT`
  and `write(rows, out_path)`; register it in `scripts/converters/__init__.py`
  (`CONVERTERS`, `SUFFIXES`). Converters read canonical fields only — never
  broker-specific type strings.
- **New transaction type**: add it to that broker's `TYPE_TO_ACTION` in its
  parser module.
