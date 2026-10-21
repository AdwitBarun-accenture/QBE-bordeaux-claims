"""Coverholder spreadsheets often have title rows ('Markel Intl - April 2026 BDX')
above the real header row. Find the most header-like row in the first 20."""
from app.utils.numbers import parse_decimal
from app.utils.text import clean_str


def score_header_row(cells: list) -> float:
    vals = [clean_str(c) for c in cells]
    non_empty = [v for v in vals if v]
    if len(non_empty) < 2:
        return 0.0
    texty = sum(1 for v in non_empty if parse_decimal(v) is None and len(v) <= 40)
    unique = len(set(v.lower() for v in non_empty)) / len(non_empty)
    fill = len(non_empty) / max(len(vals), 1)
    return (texty / len(non_empty)) * 0.5 + unique * 0.2 + fill * 0.3


def find_header_row(grid: list[list], max_scan: int = 20) -> int:
    best, best_i = -1.0, 0
    widest = max((len([c for c in r if clean_str(c)]) for r in grid[:max_scan]), default=0)
    for i, row in enumerate(grid[:max_scan]):
        filled = len([c for c in row if clean_str(c)])
        if widest and filled < widest * 0.5:
            continue  # title rows are narrow
        s = score_header_row(row)
        if s > best + 0.05:
            best, best_i = s, i
    return best_i
