# Canonical internal transactions schema

One CSV per account at `transactions/<account>.csv`. This is the intermediate
format that every broker import is normalized into, and that every output
converter (e.g. Wealthfolio) reads from. The source of truth for the column list
is `COLUMNS` in `.claude/skills/portfolio-transactions/scripts/schema.py`; keep
this file in sync.

## Columns

| Column | Type | Description | Example |
|---|---|---|---|
| `txn_id` | string | Stable SHA1 dedup key from `account\|date\|time\|symbol\|type_raw\|quantity\|price\|cash_flow`. | `a1b2c3...` |
| `account` | string | Account name (inferred from filename or `--account`). | `huabao` |
| `date` | date | Trade date, `YYYY-MM-DD`. | `2026-03-12` |
| `time` | time | Trade time, `HH:MM:SS` (empty if unknown). | `14:38:55` |
| `symbol` | string | Raw broker code (no exchange suffix); `$CASH` for account-level cash actions (DEPOSIT/WITHDRAWAL/INTEREST/FEE). | `600036`, `01888`, `$CASH` |
| `name` | string | Security name from the broker. | `招商银行` |
| `type_raw` | string | **Original** broker transaction-type string (never lost). | `融资买入` |
| `action` | enum | Normalized action (see below). | `BUY` |
| `subtype` | string | Normalized subtype, e.g. `MARGIN`; `OPENING` appears only on export-synthesized rows (never in canonical). | `MARGIN` |
| `quantity` | number | Shares/units. | `1500` |
| `price` | number | Unit price. | `19.82` |
| `cash_flow` | number | Signed cash impact (negative = money out). | `-29730` |
| `gross_amount` | number | Gross trade amount (unsigned). | `29730` |
| `fee` | number | Total fees/commission. | `3.65` |
| `currency` | string | Detected from the market. | `CNY`, `HKD` |
| `note` | string | Broker remark (备注). | |
| `source_file` | string | Basename of the input file the row came from. | `tzzb_huabao.xlsx` |

## `action` vocabulary

`BUY`, `SELL`, `TRANSFER_IN`, `TRANSFER_OUT`, `DIVIDEND`, `INTEREST`,
`DEPOSIT`, `WITHDRAWAL`, `SPLIT`, `FEE`, `TAX`, `OTHER`.

`OTHER` means the broker type string is not yet mapped — the row is still stored
(with `type_raw` intact) and listed at ingest time. Add the mapping to that
broker's `TYPE_TO_ACTION` (in its parser module) to normalize it.

## Broker type mappings live in the parsers

Each broker owns its transaction-type vocabulary in its parser module (e.g.
`TYPE_TO_ACTION` and `action_for` in `scripts/parsers/tzzb.py`). `schema.py`
holds only the shared canonical contract (columns, `ACTIONS`, `txn_id`). The
table below documents the **tzzb / huabao** mapping as an example.

### tzzb / huabao

| 交易类别 (`type_raw`) | `action` |
|---|---|
| 买入 | BUY |
| 融资买入 | BUY (margin) |
| 卖出 | SELL |
| 融券卖出 | SELL (margin) |
| 股份转入 | TRANSFER_IN |
| 转债转入 (CB allotment) | BUY |
| 股份转出 / 转债转出 | TRANSFER_OUT |
| 卖券还款 (sell to repay margin) | SELL |
| 红利入账 / 股息 / 除权除息 | DIVIDEND |
| 利息 | INTEREST |
| 银证转入 / 入金 / 收入 | DEPOSIT |
| 银证转出 / 出金 | WITHDRAWAL |
| 拆股 (bonus shares) | TRANSFER_IN |
| 组合费用 (HKEX daily levy) | FEE |
| 股息个税征收 | TAX |
| 融券 / 融券购回 (reverse repo, 204xxx/1318xx) | BUY / SELL |
| 融券 / 融券购回 (true short sell) | SELL / BUY |

`融券` / `融券购回` are context-dependent on the security code: government-bond
reverse repos (e.g. GC001/204001, R-001/131810) are cash lending, so `融券`→BUY
and `融券购回`→SELL; for any other code they are short selling (`融券`→SELL,
`融券购回`→BUY). See `action_for` in `scripts/parsers/tzzb.py`.

Margin types (`融资买入`, `融券卖出`) keep their `type_raw`; on Wealthfolio export
they are tagged `subtype=MARGIN`.
