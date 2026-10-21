from dataclasses import dataclass


@dataclass
class IncomingFile:
    external_id: str     # message-id + attachment id, or sftp path + mtime
    filename: str
    data: bytes
    source: str          # email | sftp
    sender: str = ""
    source_ref: str = ""


ALLOWED_EXT = (".csv", ".xlsx", ".xlsm", ".xls", ".zip", ".txt")
