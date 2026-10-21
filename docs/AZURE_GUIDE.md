# Azure guide — from zero to a running platform

Written for someone who has an Azure subscription but has never used it. Read
sections 1–3 once, then either run the script (section 5) or follow the portal
steps (section 6) to learn what each piece does.

---

## 1. Azure in five minutes

| Concept | What it is | Analogy |
|---|---|---|
| **Subscription** | The billing account everything is charged to | Your credit card |
| **Resource group (RG)** | A folder holding all resources for one project. Delete the RG = delete everything | A project folder |
| **Region** | Where the datacentre is (`uksouth` for London-market data) | — |
| **Resource** | One service instance (a database, a storage account…) | — |
| **Managed identity** | An identity Azure gives your app so it can reach other Azure services **without passwords in code** | A staff badge |
| **RBAC role** | Permission granted to an identity on a resource ("Storage Blob Data Contributor on storage X") | What the badge opens |
| **Key Vault** | Secure store for secrets (DB passwords, API keys, coverholder file passwords) | A safe |

Two tools you'll use:
* **Azure portal** — https://portal.azure.com (point and click)
* **Azure CLI** — `az` on your laptop. Install: https://learn.microsoft.com/cli/azure/install-azure-cli, then `az login`.

Check you're on the right subscription:
```bash
az account list -o table
az account set --subscription "<name or id>"
```

> **Corporate subscriptions (e.g. at HCLSoftware):** you may not have rights to create
> role assignments or Entra app registrations. If a step fails with
> `AuthorizationFailed`, ask your cloud admin for **Owner** (or Contributor +
> User Access Administrator) on a resource group you can use.

---

## 2. How the platform maps to Azure

```
                ┌──────────── Resource group rg-bdx ─────────────────────────────┐
 Coverholders   │                                                                 │
 email / SFTP ──┼─► Container App: bdx-api  (FastAPI + agents, scheduler)         │
                │      │  managed identity (no passwords in code)                 │
 Analyst ──────►│   Container App: bdx-ui (React via nginx) ──/api──► bdx-api     │
 browser        │      │                                                          │
                │      ├─► Blob Storage      bdx-raw (immutable originals)        │
                │      │                     bdx-staged (parsed/canonical/final)  │
                │      ├─► PostgreSQL        bdx      (files, runs, memory, audit)│
                │      │   Flexible Server   bdx_dwh  (LCRS warehouse table)      │
                │      ├─► Key Vault         secrets + coverholder file passwords │
                │      ├─► Microsoft Foundry Claude deployment (the AI)           │
                │      └─► (optional) Service Bus queue ──► bdx-worker (autoscale)│
                │   Log Analytics  ◄── all container logs (JSON, correlation ids) │
                └─────────────────────────────────────────────────────────────────┘
```

| Platform piece | Azure service | Code that uses it |
|---|---|---|
| API + agents | Container Apps | `backend/Dockerfile`, `app/main.py` |
| Web UI | Container Apps (nginx) | `frontend/Dockerfile` |
| Raw + staged files | Blob Storage | `app/storage/azure_blob.py` |
| Metadata, memory, audit | Azure Database for PostgreSQL | `app/db/` |
| Warehouse (mockup said Snowflake) | Same Postgres server, DB `bdx_dwh` — or Snowflake / Azure SQL / Fabric | `app/loaders/` |
| Secrets, file passwords | Key Vault | `app/security/vault.py` |
| AI | Claude in Microsoft Foundry | `app/llm/providers.py` |
| Background jobs at scale | Service Bus + worker app | `app/workers/` |
| M365 mailbox ingestion | Entra app registration + Microsoft Graph | `app/connectors/email_graph.py` |
| Logs/monitoring | Log Analytics / App Insights | `app/utils/logging.py` |

**Rough monthly cost (small team, UK South):** Postgres B1ms ≈ £12, Container Apps
(1 API + 1 UI always on) ≈ £30–50, storage/Key Vault/logs a few £, ACR Basic ≈ £4,
plus AI usage (tokens). Delete the resource group when experimenting to stop all charges.

---

## 3. Run it locally first (no Azure needed)

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # paste into LOCAL_VAULT_KEY
uvicorn app.main:app --reload                            # http://localhost:8000/docs

# frontend (new terminal)
cd frontend && npm install && npm run dev                # http://localhost:5173
```
Sign in as `analyst@lloyds.com` / `demo` and upload files from `sample_data/`
(`Beazley_Claims_Apr26_pw.xlsx` password: `beazley2026`). Run `pytest` in `backend/`.

Everything works with `LLM_PROVIDER=none` (deterministic agents). Add AI in section 4.

Optional: `docker compose up --build` runs Postgres + Azurite (local Blob emulator)
so you exercise the exact Azure code paths before deploying.

---

## 4. Set up Claude in Microsoft Foundry (the AI)

1. Portal search bar → **Microsoft Foundry** (or go to https://ai.azure.com) → create a
   **Foundry resource** in your resource group. Note the **resource name**.
2. In the Foundry portal: **Discover → Models** → search *Claude* → pick a model
   (e.g. Claude Sonnet) → **Deploy** → **Custom settings**.
   * First time: accept the Azure Marketplace terms.
   * **Deployment name**: keep the default (e.g. `claude-sonnet-5-5`) — this is what
     goes in `LLM_MODEL`. It can't be renamed later.
   * Region scope: Global (or Data Zone where offered).
3. Open the deployment → **Details** tab → copy **Key** and **Target URI**.
   The endpoint looks like `https://<resource>.services.ai.azure.com/anthropic/`.
4. Test from your laptop:
   ```bash
   pip install anthropic
   python - <<'PY'
   from anthropic import AnthropicFoundry
   c = AnthropicFoundry(api_key="<KEY>", resource="<resource-name>")
   print(c.messages.create(model="<deployment-name>", max_tokens=50,
         messages=[{"role":"user","content":"Say hello"}]).content[0].text)
   PY
   ```
5. Point the app at it (`backend/.env` locally; the deploy script does this in Azure):
   ```
   LLM_PROVIDER=anthropic_foundry
   ANTHROPIC_FOUNDRY_RESOURCE=<resource-name>
   ANTHROPIC_FOUNDRY_API_KEY=<key>
   LLM_MODEL=<deployment-name>
   ```
6. **Keyless (recommended in Azure):** set `ANTHROPIC_FOUNDRY_USE_ENTRA=true`, remove the
   key, and give the app's managed identity the **Foundry User** (formerly Azure AI User)
   or **Cognitive Services User** role on the Foundry resource:
   ```bash
   az role assignment create --assignee-object-id <identity principalId> \
     --assignee-principal-type ServicePrincipal --role "Cognitive Services User" \
     --scope $(az cognitiveservices account show -n <resource> -g <rg> --query id -o tsv)
   ```

Alternative: GPT models via Azure OpenAI — `LLM_PROVIDER=azure_openai`,
`AZURE_OPENAI_ENDPOINT`, `LLM_MODEL=<deployment>`. Agents don't change.

What the AI is used for (and what it is **not**): column mapping of ambiguous headers,
anomaly detection on top of the rule engine, free-text extraction, resolution guidance,
executive summaries, DUA email drafts, Q&A. Business rules, arithmetic, FX and loading
are deterministic code — so a model outage degrades gracefully instead of stopping loads.
Token usage per agent is visible on the Memory page.

---

## 5. Deploy everything with one script

Uses Azure Cloud Build for images, so you **don't need Docker** on your laptop.
```bash
az login
cd <repo root>
PREFIX=bdxdemo LOC=uksouth \
FOUNDRY_RESOURCE=<resource-name> FOUNDRY_KEY=<key> CLAUDE_DEPLOYMENT=<deployment-name> \
bash infra/azure/deploy.sh
```
~15 minutes. It prints the UI URL at the end. Options:
* `USE_WORKER=true` — adds Service Bus + an autoscaling worker (0→5 replicas on queue length).
* Leave `FOUNDRY_*` empty to deploy without AI.

Redeploy after code changes: `RG=rg-bdxdemo PREFIX=bdxdemo bash infra/azure/update.sh`
Delete everything: `az group delete -n rg-bdxdemo --yes`

**What the script does, in order** (each block is commented in the script):
1. Resource group + **user-assigned managed identity** (`bdx…-id`) — the app's badge.
2. **Container Registry** + cloud-builds both images; identity gets `AcrPull`.
3. **Storage account**, containers `bdx-raw` and `bdx-staged`; identity gets
   `Storage Blob Data Contributor`. The code refuses to overwrite raw blobs; add a
   time-based retention policy on `bdx-raw` for true WORM (portal → container → Access policy).
4. **PostgreSQL Flexible Server** with databases `bdx` and `bdx_dwh`.
5. **Key Vault** (RBAC mode) with `db-url`, `dwh-url`, `jwt-secret`, `foundry-key`;
   identity gets `Key Vault Secrets Officer` (it also stores coverholder file passwords there).
6. **Log Analytics** + **Container Apps environment**.
7. Optional **Service Bus** queue.
8. **bdx-api** container app — secrets are *Key Vault references*, so no secret ever
   appears in the app config. `AZURE_CLIENT_ID` tells `DefaultAzureCredential` which identity to use.
9. Optional **bdx-worker**, then **bdx-ui** (nginx proxies `/api` to the API).

---

## 6. The same thing by hand in the portal (to learn)

1. **Resource group:** Portal → *Resource groups* → Create → `rg-bdx`, region UK South.
2. **Storage:** *Storage accounts* → Create → Standard, LRS; *Advanced*: disable anonymous blob
   access. Then *Containers* → `bdx-raw`, `bdx-staged`.
3. **PostgreSQL:** *Azure Database for PostgreSQL flexible servers* → Create → Burstable B1ms,
   v16, admin user/password; *Networking*: allow Azure services. Then *Databases* → add `bdx`, `bdx_dwh`.
4. **Key Vault:** Create → *Access configuration*: Azure RBAC. *Access control (IAM)* → give
   yourself **Key Vault Secrets Officer** → *Secrets* → add `db-url`, `dwh-url`, `jwt-secret`.
5. **Managed identity:** *Managed Identities* → Create `bdx-id`. On the storage account and the
   key vault, *Access control (IAM)* → Add role assignment → Storage Blob Data Contributor /
   Key Vault Secrets Officer → *Members: managed identity* → `bdx-id`.
6. **Container Apps:** *Container Apps* → Create → new environment. For the API image, build it
   with `az acr build` (portal can't build). *Identity*: add `bdx-id`. *Secrets*: add each as
   **Key Vault reference** with identity `bdx-id`. *Environment variables*: as in `.env.example`,
   using `secretref:<name>` for secrets. *Ingress*: enabled, port 8000.

---

## 7. Connect the bordereaux mailbox (Microsoft 365)

1. Portal → **Microsoft Entra ID** → *App registrations* → New → `bdx-mail-reader`.
2. *API permissions* → Microsoft Graph → **Application** permissions → `Mail.ReadWrite` →
   **Grant admin consent** (needs an admin).
3. *Certificates & secrets* → New client secret → copy the value.
4. **Restrict the app to one mailbox** (important — otherwise it can read every mailbox).
   Exchange Online PowerShell:
   ```powershell
   New-ApplicationAccessPolicy -AppId <client-id> -PolicyScopeGroupId bordereaux@yourco.com `
     -AccessRight RestrictAccess -Description "BDX reader only"
   ```
5. Add to Key Vault and the API app settings: `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`,
   `GRAPH_CLIENT_SECRET` (secretref), `GRAPH_MAILBOX`, `ENABLE_SCHEDULER=true`.
   Unread mails with CSV/XLSX/ZIP attachments become inbox rows every `POLL_MINUTES`.

SFTP: set `SFTP_HOST`, `SFTP_USERNAME`, `SFTP_PASSWORD` (secretref), `SFTP_WATCH_DIR`.
Processed files are moved to `<watch dir>/processed`.

---

## 8. Verify the deployment

* `https://<api-fqdn>/api/health` → shows `llm_provider`, `storage: azure_blob`, `dwh: sql`.
* `https://<api-fqdn>/docs` → interactive API docs.
* UI → upload `sample_data/Markel_Premium_Apr26.csv` → watch *Agent activity*.
* Logs: Portal → Log Analytics workspace → *Logs*:
  ```kusto
  ContainerAppConsoleLogs_CL
  | where ContainerAppName_s == "bdx-api"
  | extend j = parse_json(Log_s)
  | project TimeGenerated, level=j.level, msg=j.msg, cid=j.correlation_id
  | order by TimeGenerated desc
  ```
  Filter by `cid` to see every step of one file across API and worker.

---

## 9. Hardening checklist before real data

- [ ] `SEED_DEMO_USERS=false`; replace local JWT login with **Entra ID SSO** (App registration
      for the UI; validate Entra tokens in `security/auth.py`; map Entra groups → `analyst` /
      `underwriter` roles). The role checks in the API stay as they are.
- [ ] Private networking: VNet-integrated Container Apps environment; Postgres, Storage,
      Key Vault and Foundry with **private endpoints**; disable public access on each.
- [ ] Immutability (time-based retention) on `bdx-raw`; soft delete + versioning on the account.
- [ ] Postgres: Entra authentication instead of password, automated backups, HA if needed.
- [ ] Replace placeholder reference data (`app/reference_data/README.md`): TMC/risk codes,
      FX rates (implement `RateProvider`), CRESTA zones + geocoder, and align
      `core/lcrs_schema.py` with the LCRS version your market uses.
- [ ] Alerts: failed jobs (`level == "error"`), files past SLA, token spend per day.
- [ ] Add Alembic migrations before changing tables (currently `create_all`).
- [ ] Data residency: keep resources in UK/EU regions; check your AI deployment's data zone.
