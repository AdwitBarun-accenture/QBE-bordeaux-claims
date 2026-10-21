from dataclasses import dataclass, field


class PasswordRequired(Exception):
    """File is encrypted and no (or a wrong) password was supplied."""


class UnsupportedFile(Exception):
    pass


@dataclass
class ParsedFile:
    headers: list[str]
    rows: list[dict]                       # every value is a string ('' for blank)
    fmt: str                               # csv | xlsx | xls
    sheet_name: str = ""
    sheets: list[str] = field(default_factory=list)
    header_row_index: int = 0              # 0-based row where headers were found
    encoding: str = ""
    delimiter: str = ""
    dropped_empty_rows: int = 0
    warnings: list[str] = field(default_factory=list)
