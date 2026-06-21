"""Output converter registry.

Each converter exposes `FORMAT`, `write(rows, out_path) -> (written, skipped)`,
and a default file suffix via SUFFIXES below.
"""

from . import wealthfolio

CONVERTERS = {wealthfolio.FORMAT: wealthfolio}

SUFFIXES = {wealthfolio.FORMAT: "wealthfolio.csv"}


def get(fmt: str):
    return CONVERTERS.get(fmt)
