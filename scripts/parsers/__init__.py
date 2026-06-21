"""Parser registry for broker exports.

Each parser module exposes `NAME`, `matches(path) -> bool`, and
`parse(path, account, source_file) -> iterable[dict]`. Register new brokers by
appending to PARSERS.
"""

from . import tzzb

PARSERS = [tzzb]


def detect_parser(path: str):
    """Return the first parser whose `matches` accepts `path`, else None."""
    for parser in PARSERS:
        if parser.matches(path):
            return parser
    return None
