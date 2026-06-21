# portfolio-transactions

A [Claude Code](https://claude.com/claude-code) **skill** that converts broker
transaction exports / statements into a canonical internal record (one CSV per
account) and exports them to other formats — currently
[Wealthfolio](https://wealthfolio.app) activity CSV.

It is a deterministic Python pipeline (reproducible, auditable); `SKILL.md` tells
Claude how to drive it, but the scripts also run standalone.

## Features

- **Ingest** broker exports into a canonical schema; account inferred from the
  filename. Incremental & idempotent — re-running only appends new transactions.
- **Pluggable parsers** — each broker owns its transaction-type vocabulary
  (`scripts/parsers/`). Ships with `tzzb` (同花顺投资账本 / Tonghuashun
  Investment Ledger) for Huabao Securities-style xlsx exports.
- **Pluggable converters** — `scripts/converters/`. Ships with Wealthfolio.
- **Opening-balance synthesis** so partial (e.g. last-3-years) history doesn't
  produce negative positions on import, with optional `--opening-date` rollup.

## Install

Clone into your Claude Code skills directory:

```bash
# personal (all projects)
git clone <repo-url> ~/.claude/skills/portfolio-transactions
# or per-project
git clone <repo-url> <project>/.claude/skills/portfolio-transactions
```

The only dependency is `openpyxl` (used by ingest). Two ways to run:

- **With [`uv`](https://docs.astral.sh/uv/) (recommended, no setup):** the entry
  scripts declare their deps inline (PEP 723), so `uv run <script>` installs them
  on demand.
- **With plain Python:** `pip install -r requirements.txt` (or `pip install
  openpyxl`), then run the scripts with `python <script>`.

## Usage

Data lives in your **working directory** (or `$PORTFOLIO_DATA_DIR`), separate
from the skill: `input/` (raw exports), `transactions/` (canonical records),
`output/` (generated exports).

```bash
# 1. Ingest a broker export -> transactions/<account>.csv
uv run path/to/skill/scripts/ingest.py input/tzzb_huabao.xlsx

# 2. Export -> output/<account>.wealthfolio.csv
uv run path/to/skill/scripts/export.py --account huabao
```

Without uv, use `python` instead (after installing `openpyxl`):

```bash
python path/to/skill/scripts/ingest.py input/tzzb_huabao.xlsx
python path/to/skill/scripts/export.py --account huabao
```

See [USAGE.md](USAGE.md) for the full guide (flags, opening-balance synthesis,
extending, troubleshooting), [SKILL.md](SKILL.md) for how Claude drives it, and
[reference/](reference/) for the format specs.

## Layout

```
SKILL.md          driving instructions for Claude
scripts/          the pipeline (schema, ingest, export, positions, parsers, converters)
reference/        canonical + output format specs
pyproject.toml    package metadata / dependencies
```

Your `input/`, `transactions/`, and `output/` data are git-ignored and never
committed.

## License

[MIT](LICENSE)
