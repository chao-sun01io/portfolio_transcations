"""Map raw broker security codes to Yahoo-style symbols and their market/currency.

Used at export time (e.g. Wealthfolio) where symbols need an exchange suffix and
a currency. Rules are approximate and table-driven so they're easy to correct.
Unknown codes are passed through unchanged with a warning and currency CNY.
"""

import sys

# Market -> currency.
MARKET_CURRENCY = {"SS": "CNY", "SZ": "CNY", "BJ": "CNY", "HK": "HKD"}

# 6-digit A-share prefixes. Longest-prefix-wins lookup against these.
# Shanghai Stock Exchange.
SH_PREFIXES = (
    "60",   # SSE main board stocks
    "68",   # STAR market
    "90",   # SSE B-shares
    "5",    # SSE funds/ETF (50/51/52/56/58...)
    "11",   # SSE convertible bonds
    "113",  # SSE convertible bonds
    "204",  # SSE government-bond reverse repo (GC series)
)
# Shenzhen Stock Exchange.
SZ_PREFIXES = (
    "00",   # SZSE main board stocks
    "30",   # ChiNext
    "200",  # SZSE B-shares
    "15",   # SZSE funds/ETF
    "16",   # SZSE funds
    "18",   # SZSE funds
    "12",   # SZSE convertible bonds
    "13",   # SZSE bonds
)
# Beijing Stock Exchange.
BJ_PREFIXES = (
    "920",  # BSE stocks (current numbering)
    "43",   # BSE stocks (legacy NEEQ-select)
    "83",   # BSE stocks
    "87",   # BSE stocks
    "88",   # BSE stocks
)


def is_reverse_repo(code: str) -> bool:
    """True for government-bond reverse-repo codes (SH 204xxx, SZ 1318xx)."""
    code = (code or "").strip()
    return code.startswith("204") or code.startswith("1318")


def market_of(code: str) -> str:
    """Return the market code: SS (Shanghai), SZ (Shenzhen), HK, or "" if unknown."""
    code = (code or "").strip()
    if not code:
        return ""
    if len(code) == 5 and code.isdigit():
        return "HK"
    if len(code) == 6 and code.isdigit():
        # Longest matching prefix wins so "11" beats "1".
        sh = max((p for p in SH_PREFIXES if code.startswith(p)), key=len, default="")
        sz = max((p for p in SZ_PREFIXES if code.startswith(p)), key=len, default="")
        bj = max((p for p in BJ_PREFIXES if code.startswith(p)), key=len, default="")
        best = max((sh, "SS"), (sz, "SZ"), (bj, "BJ"), key=lambda t: len(t[0]))
        if best[0]:
            return best[1]
    return ""


def currency_of(code: str) -> str:
    """Detected currency for a code (defaults to CNY when market is unknown)."""
    return MARKET_CURRENCY.get(market_of(code), "CNY")


def to_yahoo(code: str, warn: bool = True) -> str:
    """Convert a broker code to a Yahoo-style symbol (e.g. 600036.SS, 1888.HK).

    HK 5-digit codes are reduced to Yahoo's 4-digit form (01888 -> 1888.HK).
    Unknown codes are returned unchanged (with a warning on stderr).
    """
    code = (code or "").strip()
    market = market_of(code)
    if market in ("SS", "SZ", "BJ"):
        return f"{code}.{market}"
    if market == "HK":
        return f"{int(code):04d}.HK"
    if warn:
        print(f"warning: unknown market for code {code!r}; passing through",
              file=sys.stderr)
    return code
