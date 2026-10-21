"""Central configuration. Every value can be overridden with an environment
variable (or a .env file). On Azure these are set as Container App settings,
and secrets are pulled from Key Vault (see security/vault.py)."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- App ----
    app_name: str = "Bordereaux Intelligence Platform"
    environment: Literal["local", "dev", "test", "prod"] = "local"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ---- Auth ----
    jwt_secret: str = "change-me-in-production"
    jwt_expiry_minutes: int = 480
    seed_demo_users: bool = True

    # ---- Database (app metadata: files, runs, memory, audit) ----
    # local: sqlite. Azure: postgresql+psycopg://user:pw@host:5432/bdx?sslmode=require
    database_url: str = "sqlite:///./bdx_local.db"

    # ---- Storage (immutable raw files + staged datasets) ----
    storage_backend: Literal["local", "azure_blob"] = "local"
    local_storage_root: str = "./data"
    azure_storage_account_url: str = ""          # https://<acct>.blob.core.windows.net
    azure_storage_connection_string: str = ""    # alternative to managed identity
    azure_raw_container: str = "bdx-raw"
    azure_staged_container: str = "bdx-staged"

    # ---- LLM provider ----
    # none              -> deterministic fallbacks only (no AI calls). Good for tests.
    # anthropic         -> Claude API direct (ANTHROPIC_API_KEY)
    # anthropic_foundry -> Claude deployed in Microsoft Foundry on Azure
    # azure_openai      -> GPT deployment in Azure OpenAI
    llm_provider: Literal["none", "anthropic", "anthropic_foundry", "azure_openai"] = "none"
    llm_model: str = "claude-sonnet-5-5"     # for Foundry/Azure OpenAI: the *deployment name*
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3
    anthropic_api_key: str = ""
    anthropic_foundry_api_key: str = ""
    anthropic_foundry_resource: str = ""     # e.g. "my-foundry-resource"
    anthropic_foundry_use_entra: bool = False  # use managed identity instead of key
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-10-21"

    # ---- Pipeline behaviour (defaults; overridable at runtime in Settings UI) ----
    auto_approve_threshold: int = 85         # mapping confidence for auto-approval
    review_threshold: int = 50               # below this -> unmapped
    freetext_merge_threshold: int = 70       # extracted values below this are not merged
    max_rows_to_llm: int = 25                # rows sampled into prompts (cost control)
    schema_version: str = "LCRS v3.2"

    # ---- Data warehouse loader ----
    # sql       -> any SQLAlchemy URL (Azure SQL, Postgres, SQLite)
    # snowflake -> Snowflake (as in the mockup)
    # csv       -> write CSV files to storage (dev only)
    dwh_loader: Literal["sql", "snowflake", "csv"] = "sql"
    dwh_database_url: str = "sqlite:///./bdx_dwh.db"   # Azure: postgresql+psycopg://... or mssql+pyodbc://...
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = ""
    snowflake_database: str = ""
    snowflake_schema: str = "LCRS"

    # ---- Job queue ----
    queue_backend: Literal["inprocess", "sync", "servicebus"] = "inprocess"   # sync = run inline (tests/debug)
    servicebus_connection_string: str = ""
    servicebus_namespace: str = ""           # <ns>.servicebus.windows.net (managed identity)
    servicebus_queue: str = "bdx-pipeline"

    # ---- Secrets ----
    key_vault_url: str = ""                  # https://<vault>.vault.azure.net/
    local_vault_key: str = ""                # Fernet key for local password vault

    # ---- Connectors ----
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_mailbox: str = ""                  # bordereaux@yourco.com
    sftp_host: str = ""
    sftp_port: int = 22
    sftp_username: str = ""
    sftp_password: str = ""
    sftp_watch_dir: str = "/inbound/bordereaux"
    poll_minutes: int = 15
    enable_scheduler: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
