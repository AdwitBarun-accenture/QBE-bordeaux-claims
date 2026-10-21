"""Password vault for password-protected coverholder files.

The mockup stored passwords in browser localStorage (unsafe). Here:
  - Azure: secrets in Azure Key Vault, named 'bdx-pw-<coverholder-slug>'
  - Local: Fernet-encrypted values in the app_settings table
"""
import re
from functools import lru_cache

from app.core.config import get_settings
from app.db.models import AppSetting
from app.db.session import session_scope


def _slug(name: str) -> str:
    return "bdx-pw-" + re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")


class PasswordVault:
    def get(self, coverholder: str) -> str | None: ...
    def set(self, coverholder: str, password: str) -> None: ...
    def delete(self, coverholder: str) -> None: ...
    def list(self) -> list[str]: ...


class KeyVaultPasswordVault(PasswordVault):
    def __init__(self, url: str):
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        self.client = SecretClient(vault_url=url, credential=DefaultAzureCredential())

    def get(self, coverholder):
        try:
            return self.client.get_secret(_slug(coverholder)).value
        except Exception:
            return None

    def set(self, coverholder, password):
        self.client.set_secret(_slug(coverholder), password, tags={"coverholder": coverholder})

    def delete(self, coverholder):
        try:
            self.client.begin_delete_secret(_slug(coverholder))
        except Exception:
            pass

    def list(self):
        return [p.tags.get("coverholder", p.name) for p in self.client.list_properties_of_secrets()
                if p.name.startswith("bdx-pw-") and p.enabled]


class LocalPasswordVault(PasswordVault):
    KEY = "password_vault"

    def __init__(self, key: str):
        from cryptography.fernet import Fernet
        self.f = Fernet(key.encode() if key else Fernet.generate_key())

    def _load(self, db) -> dict:
        row = db.get(AppSetting, self.KEY)
        return dict(row.value) if row else {}

    def _save(self, db, data: dict):
        row = db.get(AppSetting, self.KEY)
        if row:
            row.value = data
        else:
            db.add(AppSetting(key=self.KEY, value=data))

    def get(self, coverholder):
        with session_scope() as db:
            token = self._load(db).get(coverholder)
        if not token:
            return None
        try:
            return self.f.decrypt(token.encode()).decode()
        except Exception:
            return None

    def set(self, coverholder, password):
        with session_scope() as db:
            data = self._load(db)
            data[coverholder] = self.f.encrypt(password.encode()).decode()
            self._save(db, data)

    def delete(self, coverholder):
        with session_scope() as db:
            data = self._load(db)
            data.pop(coverholder, None)
            self._save(db, data)

    def list(self):
        with session_scope() as db:
            return sorted(self._load(db).keys())


@lru_cache
def get_vault() -> PasswordVault:
    s = get_settings()
    if s.key_vault_url:
        return KeyVaultPasswordVault(s.key_vault_url)
    return LocalPasswordVault(s.local_vault_key)
