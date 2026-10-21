"""Azure Blob Storage implementation.

Auth: managed identity (DefaultAzureCredential) when AZURE_STORAGE_ACCOUNT_URL is
set, or a connection string for local dev against Azurite.
For true WORM storage enable a time-based *immutability policy* on the bdx-raw
container in the portal (Container -> Access policy -> Add policy).
"""
from app.storage.base import BlobStore, ImmutableBlobError


class AzureBlobStore(BlobStore):
    def __init__(self, account_url: str, connection_string: str, raw_container: str, staged_container: str):
        from azure.storage.blob import BlobServiceClient

        if connection_string:
            self.svc = BlobServiceClient.from_connection_string(connection_string)
        else:
            from azure.identity import DefaultAzureCredential
            self.svc = BlobServiceClient(account_url=account_url, credential=DefaultAzureCredential())
        self.raw = self.svc.get_container_client(raw_container)
        self.staged = self.svc.get_container_client(staged_container)
        for c in (self.raw, self.staged):
            try:
                c.create_container()
            except Exception:
                pass  # already exists

    def put_raw(self, key: str, data: bytes) -> str:
        from azure.core.exceptions import ResourceExistsError
        blob = self.raw.get_blob_client(key)
        try:
            blob.upload_blob(data, overwrite=False)
        except ResourceExistsError as e:
            raise ImmutableBlobError(f"raw blob already exists: {key}") from e
        return blob.url

    def get_raw(self, key: str) -> bytes:
        return self.raw.get_blob_client(key).download_blob().readall()

    def put_staged(self, key: str, data: bytes) -> str:
        blob = self.staged.get_blob_client(key)
        blob.upload_blob(data, overwrite=True)
        return blob.url

    def get_staged(self, key: str) -> bytes:
        return self.staged.get_blob_client(key).download_blob().readall()

    def exists_staged(self, key: str) -> bool:
        return self.staged.get_blob_client(key).exists()
