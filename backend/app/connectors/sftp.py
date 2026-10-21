"""SFTP watcher: downloads new files from the watch directory and moves them
to <watch>/processed after successful intake."""
import io
import posixpath

from app.connectors.base import ALLOWED_EXT, IncomingFile
from app.core.config import get_settings


class SftpWatcher:
    def __init__(self, host=None, port=None, username=None, password=None, watch_dir=None):
        s = get_settings()
        self.host, self.port = host or s.sftp_host, port or s.sftp_port
        self.username, self.password = username or s.sftp_username, password or s.sftp_password
        self.watch_dir = watch_dir or s.sftp_watch_dir
        if not self.host:
            raise RuntimeError("SFTP not configured (SFTP_HOST)")

    def _connect(self):
        import paramiko
        t = paramiko.Transport((self.host, self.port))
        t.connect(username=self.username, password=self.password)
        return t, paramiko.SFTPClient.from_transport(t)

    def test(self) -> dict:
        t, c = self._connect()
        try:
            files = [f for f in c.listdir(self.watch_dir) if f.lower().endswith(ALLOWED_EXT)]
            return {"ok": True, "files_waiting": len(files)}
        finally:
            c.close()
            t.close()

    def fetch_new(self, seen: set[str]) -> list[IncomingFile]:
        t, c = self._connect()
        out = []
        try:
            for attr in c.listdir_attr(self.watch_dir):
                name = attr.filename
                path = posixpath.join(self.watch_dir, name)
                ext_id = f"{path}:{attr.st_mtime}:{attr.st_size}"
                if ext_id in seen or not name.lower().endswith(ALLOWED_EXT):
                    continue
                buf = io.BytesIO()
                c.getfo(path, buf)
                out.append(IncomingFile(ext_id, name, buf.getvalue(), "sftp", source_ref=path))
            return out
        finally:
            c.close()
            t.close()

    def archive(self, path: str) -> None:
        t, c = self._connect()
        try:
            dest_dir = posixpath.join(self.watch_dir, "processed")
            try:
                c.mkdir(dest_dir)
            except IOError:
                pass
            c.rename(path, posixpath.join(dest_dir, posixpath.basename(path)))
        finally:
            c.close()
            t.close()
