# Bordereaux Intelligence Platform

Full-scale build of the `bordereaux_platform.html` mockup: a multi-agent pipeline that
ingests coverholder bordereaux (premium and claims), maps them to the LCRS canonical
model, validates, cleanses, extracts free text, reconciles and loads them to a warehouse,
with three human review gates and a learning memory layer.

```
backend/      Python 3.12 · FastAPI · SQLAlchemy · agents, rules, enrichment, connectors
frontend/     React 18 · Vite · the analyst/underwriter UI
infra/azure/  deploy.sh (one-shot Azure deployment) · update.sh (redeploy)
docs/         ARCHITECTURE.md (how it works) · AZURE_GUIDE.md (step-by-step Azure)
sample_data/  The mockup's sample files as real CSV/XLSX (+ an encrypted one)
docker-compose.yml   Local stack with Postgres + Azurite (Azure Blob emulator)
```

## Quick start (no Azure, no AI key needed)

```bash
# 1. backend
cd backend
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   -> paste the output into LOCAL_VAULT_KEY in .env
uvicorn app.main:app --reload                              # API docs: http://localhost:8000/docs

# 2. frontend (second terminal)
cd frontend
npm install
npm run dev                                                # http://localhost:5173

# 3. tests
cd backend && pytest                                       # 17 tests
```

Sign in with `analyst@lloyds.com` / `demo` (full pipeline) or `underwriter@lloyds.com` /
`demo` (insights only). Upload files from `sample_data/`; the encrypted one
(`Beazley_Claims_Apr26_pw.xlsx`) has password `beazley2026`.

With `LLM_PROVIDER=none` every agent runs on its deterministic path. To switch the AI on,
see `docs/AZURE_GUIDE.md` section 4 (Claude in Microsoft Foundry) or set
`LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`.

## Deploy to Azure

```bash
az login
PREFIX=bdxdemo FOUNDRY_RESOURCE=<name> FOUNDRY_KEY=<key> CLAUDE_DEPLOYMENT=<deployment> \
  bash infra/azure/deploy.sh
```
Read `docs/AZURE_GUIDE.md` first: it explains every resource the script creates.

## Where to start reading the code

1. `backend/app/agents/orchestrator.py` – the state machine: stages + 3 gates.
2. `backend/app/agents/*_agent.py` – one file per agent, each with a header explaining
   what the mockup did and what this version does.
3. `backend/app/rules/` – every business rule as a small class.
4. `backend/app/core/lcrs_schema.py` – the canonical data model (single source of truth).
5. `docs/ARCHITECTURE.md` – the full walkthrough.
