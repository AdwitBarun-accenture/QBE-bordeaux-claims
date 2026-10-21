"""Turn a raw 2-D grid (from CSV or Excel) into headers + row dicts."""
from app.parsers.header_detect import find_header_row
from app.utils.text import clean_str, dedupe_headers


def grid_to_records(grid: list[list]) -> tuple[list[str], list[dict], int, int]:
    grid = [[("" if c is None else c) for c in r] for r in grid]
    grid = [r for r in grid if any(clean_str(c) for c in r)] if grid else []
    if not grid:
        return [], [], 0, 0
    h_idx = find_header_row(grid)
    raw_headers = grid[h_idx]
    width = max(len(r) for r in grid)
    raw_headers = list(raw_headers) + [""] * (width - len(raw_headers))
    # drop columns with no header and no data
    keep = [j for j in range(width)
            if clean_str(raw_headers[j]) or any(j < len(r) and clean_str(r[j]) for r in grid[h_idx + 1:])]
    headers = dedupe_headers([clean_str(raw_headers[j]) for j in keep])
    rows, dropped = [], 0
    for r in grid[h_idx + 1:]:
        vals = [(_cell(r[j]) if j < len(r) else "") for j in keep]
        if not any(vals):
            dropped += 1
            continue
        rows.append(dict(zip(headers, vals)))
    return headers, rows, h_idx, dropped


def _cell(v) -> str:
    from datetime import date, datetime
    if isinstance(v, datetime):
        return v.date().isoformat() if (v.hour, v.minute, v.second) == (0, 0, 0) else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return clean_str(v)
