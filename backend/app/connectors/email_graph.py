"""Microsoft 365 shared mailbox via Microsoft Graph (app-only auth).

Azure setup (docs/AZURE_GUIDE.md section 7):
  1. Entra ID -> App registrations -> New (bdx-mail-reader)
  2. API permissions -> Microsoft Graph -> Application -> Mail.ReadWrite -> Grant admin consent
  3. Restrict it to the bordereaux mailbox with an Exchange ApplicationAccessPolicy
  4. Put tenant id / client id / secret into Key Vault -> GRAPH_* settings
"""
import base64

import httpx

from app.connectors.base import ALLOWED_EXT, IncomingFile
from app.core.config import get_settings

GRAPH = "https://graph.microsoft.com/v1.0"


class GraphMailbox:
    def __init__(self):
        s = get_settings()
        if not (s.graph_tenant_id and s.graph_client_id and s.graph_client_secret and s.graph_mailbox):
            raise RuntimeError("Graph mailbox not configured (GRAPH_TENANT_ID / CLIENT_ID / CLIENT_SECRET / MAILBOX)")
        self.s = s

    def _token(self) -> str:
        import msal
        app = msal.ConfidentialClientApplication(self.s.graph_client_id, client_credential=self.s.graph_client_secret,
                                                 authority=f"https://login.microsoftonline.com/{self.s.graph_tenant_id}")
        tok = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in tok:
            raise RuntimeError(f"Graph auth failed: {tok.get('error_description')}")
        return tok["access_token"]

    def fetch_new(self, seen: set[str]) -> list[IncomingFile]:
        h = {"Authorization": f"Bearer {self._token()}"}
        url = (f"{GRAPH}/users/{self.s.graph_mailbox}/mailFolders/inbox/messages"
               "?$filter=hasAttachments eq true and isRead eq false&$select=id,subject,from,receivedDateTime&$top=25")
        out = []
        with httpx.Client(timeout=60) as c:
            msgs = c.get(url, headers=h).raise_for_status().json().get("value", [])
            for m in msgs:
                sender = m.get("from", {}).get("emailAddress", {}).get("address", "")
                atts = c.get(f"{GRAPH}/users/{self.s.graph_mailbox}/messages/{m['id']}/attachments", headers=h).raise_for_status().json()
                for a in atts.get("value", []):
                    ext_id = f"{m['id']}:{a['id']}"
                    name = a.get("name", "")
                    if ext_id in seen or not name.lower().endswith(ALLOWED_EXT) or "contentBytes" not in a:
                        continue
                    out.append(IncomingFile(ext_id, name, base64.b64decode(a["contentBytes"]), "email", sender, m.get("subject", "")))
                c.patch(f"{GRAPH}/users/{self.s.graph_mailbox}/messages/{m['id']}", headers=h, json={"isRead": True})
        return out


class GmailMailbox:
    """Placeholder for the mockup's Gmail option. Implement with the Gmail API
    (google-api-python-client, service account + domain-wide delegation)."""

    def fetch_new(self, seen):
        raise NotImplementedError("Gmail connector not implemented - see docstring")
