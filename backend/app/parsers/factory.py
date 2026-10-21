"""Single entry point: bytes + filename (+ password, sheet) -> ParsedFile."""
from app.parsers.base import ParsedFile, PasswordRequired, UnsupportedFile
from app.parsers.csv_parser import parse_csv
from app.parsers.decrypt import decrypt_office, is_encrypted_office, unzip_single
from app.parsers.excel_parser import parse_excel


def needs_password(filename: str, data: bytes) -> bool:
    if is_encrypted_office(data):
        return True
    if filename.lower().endswith(".zip"):
        try:
            unzip_single(data, None)
        except PasswordRequired:
            return True
        except Exception:
            return False
    return False


def parse_bytes(filename: str, data: bytes, password: str | None = None, sheet: str | None = None) -> ParsedFile:
    name = filename.lower()
    if name.endswith(".zip"):
        inner_name, data = unzip_single(data, password)
        return parse_bytes(inner_name, data, password, sheet)
    if is_encrypted_office(data):
        data = decrypt_office(data, password)
        return parse_excel(data, sheet)
    if name.endswith((".xlsx", ".xlsm")):
        return parse_excel(data, sheet)
    if name.endswith(".xls"):
        import io
        import pandas as pd
        try:
            df = pd.read_excel(io.BytesIO(data), sheet_name=sheet or 0, header=None, dtype=str, engine="xlrd")
        except Exception as e:
            raise UnsupportedFile(f"legacy .xls needs 'xlrd' installed: {e}") from e
        from app.parsers.grid import grid_to_records
        headers, rows, h, d = grid_to_records(df.fillna("").values.tolist())
        return ParsedFile(headers, rows, "xls", header_row_index=h, dropped_empty_rows=d)
    if name.endswith((".csv", ".txt", ".tsv")):
        return parse_csv(data)
    raise UnsupportedFile(f"unsupported file type: {filename}")
