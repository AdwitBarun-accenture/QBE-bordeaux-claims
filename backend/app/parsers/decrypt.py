"""Password-protected Office files (Excel 'Encrypt with password') and zip archives.
The mockup only simulated this; here we actually decrypt using msoffcrypto-tool."""
import io
import zipfile

from app.parsers.base import PasswordRequired

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"   # encrypted OOXML is wrapped in OLE


def is_encrypted_office(data: bytes) -> bool:
    if not data.startswith(OLE_MAGIC):
        return False
    try:
        import msoffcrypto
        return msoffcrypto.OfficeFile(io.BytesIO(data)).is_encrypted()
    except Exception:
        return False


def decrypt_office(data: bytes, password: str | None) -> bytes:
    import msoffcrypto
    if not password:
        raise PasswordRequired("file is password protected")
    office = msoffcrypto.OfficeFile(io.BytesIO(data))
    out = io.BytesIO()
    try:
        office.load_key(password=password)
        office.decrypt(out)
    except Exception as e:
        raise PasswordRequired("incorrect password") from e
    return out.getvalue()


def unzip_single(data: bytes, password: str | None) -> tuple[str, bytes]:
    """Return the first bordereaux-like member of a zip (ZipCrypto passwords supported)."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = [m for m in z.infolist() if not m.is_dir() and m.filename.lower().endswith((".csv", ".xlsx", ".xlsm", ".xls"))]
        if not members:
            raise ValueError("zip contains no csv/xlsx")
        m = members[0]
        encrypted = m.flag_bits & 0x1
        if encrypted and not password:
            raise PasswordRequired("zip is password protected")
        try:
            return m.filename, z.read(m, pwd=password.encode() if password else None)
        except RuntimeError as e:
            raise PasswordRequired("incorrect zip password") from e
