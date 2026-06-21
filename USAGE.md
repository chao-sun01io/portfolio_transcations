# Usage

End-to-end guide for the `portfolio-transactions` skill. For the design overview
see [README.md](README.md); for the canonical/output formats see
[reference/](reference/).

## Prerequisites

The only dependency is `openpyxl` (used by ingest). Pick one:

- **With [`uv`](https://docs.astral.sh/uv/) (recommended):** nothing to install —
  the entry scripts declare deps inline (PEP 723), so `uv run <script>` fetches
  them automatically.
- **With plain Python:** `pip install -r requirements.txt`, then run the scripts
  with `python <script>` instead of `uv run <script>`.

The examples below use `uv run`; substitute `python` if you went the pip route.

## Data layout

Your data lives in a **working directory**, separate from the skill. The scripts
resolve these folders from the current directory (or `$PORTFOLIO_DATA_DIR`):

```
<your data dir>/
  input/          raw broker exports you drop in        (e.g. tzzb_huabao.xlsx)
  transactions/   canonical records, one CSV per account (generated)
  output/         exports, e.g. Wealthfolio CSV          (generated)
```

`input/` is the only one you populate; the other two are created for you. Run all
commands from `<your data dir>`. To keep data elsewhere:

```bash
export PORTFOLIO_DATA_DIR=/path/to/your/data
```

In the examples below, `SKILL=` points at wherever the skill is installed:

```bash
SKILL=.claude/skills/portfolio-transactions        # per-project install
# SKILL=~/.claude/skills/portfolio-transactions    # personal install
```

## 1. Ingest — build / update canonical records

```bash
uv run $SKILL/scripts/ingest.py input/tzzb_huabao.xlsx
```

- **Account** is inferred from the filename (`tzzb_huabao.xlsx` → `huabao`,
  `tzzb_huabao-margin.xlsx` → `huabao-margin`). Override with `--account NAME`.
- Writes/updates `transactions/<account>.csv`.
- **Incremental & idempotent:** re-running with an updated export appends only new
  transactions. Output reports `added / skipped (duplicates) / unknown-type`.

```bash
# explicit account name
uv run $SKILL/scripts/ingest.py input/some_export.xlsx --account huabao
```

### Unmapped transaction types

If ingest finds a transaction type it doesn't recognize, it keeps the row (as
`action=OTHER`) and lists it at the end:

```
UNMAPPED transaction types (...):
  - '调帐转入'  x2  e.g. 2025-08-19 082626 ...
```

Decide how each should map, then add it to that broker's `TYPE_TO_ACTION` in its
parser (e.g. `scripts/parsers/tzzb.py`) and re-ingest. `OTHER` rows are skipped on
export.

## 2. Export — convert to another format

```bash
uv run $SKILL/scripts/export.py --account huabao
```

Produces `output/huabao.wealthfolio.csv` — the formatted export. (The canonical
record stays in `transactions/huabao.csv`.)

### Options

| Flag | Effect |
|---|---|
| `--format wealthfolio` | Output format (default `wealthfolio`). |
| `--out FILE` | Custom output path. |
| `--opening-date YYYY-MM-DD` | Roll up all activity before the date into an opening snapshot (holdings + one combined cash deposit per currency). |
| `--no-opening-guard` | Disable opening synthesis; export raw canonical rows. |

### Opening-balance synthesis (avoiding negative positions)

Brokers that only provide recent statements report sells of shares bought before
the window, which would make positions go negative on import. By default an
**auto guard** injects the minimal opening `TRANSFER_IN` per symbol so the
end-of-day position never goes negative. Same-day offsetting events (e.g. a
transfer-out and matching buy) are treated as a settlement-timing artifact and
tolerated. Synthesized rows are priced from transaction prices for ~zero P&L and
marked `subtype=OPENING`. This is **export-only** — canonical records are never
modified.

```bash
# Clean snapshot start: collapse everything before 2025-01-01 into an opening
uv run $SKILL/scripts/export.py --account huabao --opening-date 2025-01-01

# Raw export, no synthesis (e.g. to inspect the unmodified data)
uv run $SKILL/scripts/export.py --account huabao --no-opening-guard
```

## Full example

```bash
cd ~/portfolio                     # your data dir with input/
SKILL=~/.claude/skills/portfolio-transactions

# ingest two accounts
uv run $SKILL/scripts/ingest.py input/tzzb_huabao.xlsx
uv run $SKILL/scripts/ingest.py input/tzzb_huabao-margin.xlsx

# export both to Wealthfolio
uv run $SKILL/scripts/export.py --account huabao
uv run $SKILL/scripts/export.py --account huabao-margin

# later: drop a newer export in input/ and re-run ingest (appends new rows only)
uv run $SKILL/scripts/ingest.py input/tzzb_huabao.xlsx
```

Then import each `output/<account>.wealthfolio.csv` into Wealthfolio.

## Driving it through Claude Code

You usually don't run the commands yourself — just ask Claude in this project:

- "Ingest `input/tzzb_huabao.xlsx`."
- "Convert my huabao transactions to Wealthfolio."
- "Add the new statement and re-export, rolling up everything before 2025."

Claude matches the skill from its description and runs the right commands.

## Extending

- **New broker:** add a module in `scripts/parsers/` exposing `NAME`,
  `matches(path)`, `parse(path, account, source_file)`, and its own
  `TYPE_TO_ACTION`; register it in `scripts/parsers/__init__.py`. Rows must emit
  an `action` from `schema.ACTIONS` and set `subtype` (e.g. `MARGIN`).
- **New output format:** add a module in `scripts/converters/` exposing `FORMAT`
  and `write(rows, out_path)`; register it in `scripts/converters/__init__.py`.
  Converters read canonical fields only — never broker-specific type strings.
- **New transaction type:** add it to that broker's `TYPE_TO_ACTION`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `no parser recognizes <file>` | The file isn't a known broker format. Add a parser (see Extending). |
| `no canonical records for account` | Run `ingest.py` first; check the account name matches the file. |
| Many `unknown-type` rows | Map them in the parser's `TYPE_TO_ACTION` and re-ingest. |
| Wrong exchange suffix / currency in output | Adjust the prefix rules in `scripts/symbols.py`. |
| Negative positions in Wealthfolio | Ensure the opening guard is on (default), or use `--opening-date`. |
| Data written to the wrong place | Run from your data dir, or set `$PORTFOLIO_DATA_DIR`. |
