import csv
import io

from charset_normalizer import from_bytes

from app.parsers.base import ParsedFile
from app.parsers.grid import grid_to_records


def parse_csv(data: bytes) -> ParsedFile:
    best = from_bytes(data).best()
    encoding = best.encoding if best else "utf-8"
    text = data.decode(encoding, errors="replace").lstrip("\ufeff")
    try:
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    grid = list(csv.reader(io.StringIO(text), delimiter=delim))
    headers, rows, h_idx, dropped = grid_to_records(grid)
    pf = ParsedFile(headers=headers, rows=rows, fmt="csv", header_row_index=h_idx,
                    encoding=encoding, delimiter=delim, dropped_empty_rows=dropped)
    if h_idx:
        pf.warnings.append(f"{h_idx} title row(s) above the header were skipped")
    return pf
