#!/usr/bin/env bash
# =============================================================================
# One-shot Azure deployment for the Bordereaux Intelligence Platform.
# Read docs/AZURE_GUIDE.md first - it explains every resource created here.
#
# Prereqs:  az login ; az account set --subscription "<your subscription>"
#           A Microsoft Foundry resource with a Claude deployment (portal steps
#           in the guide, section 4) - pass its name/key below, or leave
#           FOUNDRY_RESOURCE empty to run without AI (deterministic mode).
# Usage:    cd <repo root> && bash infra/azure/deploy.sh
# =============================================================================
set -euo pipefail

# ---------- 1. names (change PREFIX; must be globally unique-ish, lowercase) ----------
PREFIX="${PREFIX:-bdx$RANDOM}"
LOC="${LOC:-uksouth}"
RG="${RG:-rg-$PREFIX}"
ACR="${PREFIX}acr"
SA="${PREFIX}sa"
PG="${PREFIX}-pg"
KV="${PREFIX}-kv"
SB="${PREFIX}-sb"
ENV="${PREFIX}-env"
LAW="${PREFIX}-logs"
ID_NAME="${PREFIX}-id"
PG_ADMIN="bdxadmin"
PG_PW="${PG_PW:-$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 20)Aa1!}"
USE_WORKER="${USE_WORKER:-false}"          # true = Service Bus + autoscaling worker
FOUNDRY_RESOURCE="${FOUNDRY_RESOURCE:-}"   # e.g. my-foundry
FOUNDRY_KEY="${FOUNDRY_KEY:-}"             # from the deployment's Details tab
CLAUDE_DEPLOYMENT="${CLAUDE_DEPLOYMENT:-claude-sonnet-5-5}"
TAG="v$(date +%Y%m%d%H%M)"

echo ">> Deploying prefix=$PREFIX into $RG ($LOC)"
az extension add --name containerapp --upgrade -y >/dev/null
az provider register -n Microsoft.App --wait >/dev/null
az provider register -n Microsoft.OperationalInsights --wait >/dev/null

# ---------- 2. resource group + identity ----------
az group create -n "$RG" -l "$LOC" -o none
az identity create -n "$ID_NAME" -g "$RG" -o none
ID_ID=$(az identity show -n "$ID_NAME" -g "$RG" --query id -o tsv)
ID_PRINCIPAL=$(az identity show -n "$ID_NAME" -g "$RG" --query principalId -o tsv)
ID_CLIENT=$(az identity show -n "$ID_NAME" -g "$RG" --query clientId -o tsv)
ME=$(az ad signed-in-user show --query id -o tsv)

role() { # role <role name> <scope>
  az role assignment create --assignee-object-id "$ID_PRINCIPAL" --assignee-principal-type ServicePrincipal \
     --role "$1" --scope "$2" -o none 2>/dev/null || true
}

# ---------- 3. container registry + images ----------
az acr create -n "$ACR" -g "$RG" --sku Basic -o none
ACR_ID=$(az acr show -n "$ACR" --query id -o tsv)
role "AcrPull" "$ACR_ID"
echo ">> Building images in ACR (cloud build, no local Docker needed)"
az acr build -r "$ACR" -t "bdx-api:$TAG" ./backend -o none
az acr build -r "$ACR" -t "bdx-ui:$TAG" ./frontend -o none

# ---------- 4. storage (immutable raw files + staged datasets) ----------
az storage account create -n "$SA" -g "$RG" -l "$LOC" --sku Standard_LRS --kind StorageV2 \
   --allow-blob-public-access false --min-tls-version TLS1_2 -o none
SA_ID=$(az storage account show -n "$SA" -g "$RG" --query id -o tsv)
az role assignment create --assignee "$ME" --role "Storage Blob Data Contributor" --scope "$SA_ID" -o none 2>/dev/null || true
role "Storage Blob Data Contributor" "$SA_ID"
sleep 20  # RBAC propagation
az storage container create --account-name "$SA" -n bdx-raw --auth-mode login -o none
az storage container create --account-name "$SA" -n bdx-staged --auth-mode login -o none
echo "   (Optional WORM) Portal > $SA > Containers > bdx-raw > Access policy > Add time-based retention"

# ---------- 5. PostgreSQL (app metadata + LCRS warehouse) ----------
az postgres flexible-server create -g "$RG" -n "$PG" -l "$LOC" --admin-user "$PG_ADMIN" --admin-password "$PG_PW" \
   --sku-name Standard_B1ms --tier Burstable --storage-size 32 --version 16 --public-access 0.0.0.0 --yes -o none
az postgres flexible-server db create -g "$RG" -s "$PG" -d bdx -o none
az postgres flexible-server db create -g "$RG" -s "$PG" -d bdx_dwh -o none
PG_HOST="$PG.postgres.database.azure.com"
DB_URL="postgresql+psycopg://$PG_ADMIN:$PG_PW@$PG_HOST:5432/bdx?sslmode=require"
DWH_URL="postgresql+psycopg://$PG_ADMIN:$PG_PW@$PG_HOST:5432/bdx_dwh?sslmode=require"

# ---------- 6. Key Vault (all secrets live here) ----------
az keyvault create -n "$KV" -g "$RG" -l "$LOC" --enable-rbac-authorization true -o none
KV_ID=$(az keyvault show -n "$KV" --query id -o tsv)
KV_URI=$(az keyvault show -n "$KV" --query properties.vaultUri -o tsv)
az role assignment create --assignee "$ME" --role "Key Vault Secrets Officer" --scope "$KV_ID" -o none 2>/dev/null || true
role "Key Vault Secrets Officer" "$KV_ID"   # app reads secrets + stores coverholder file passwords
sleep 20
az keyvault secret set --vault-name "$KV" -n db-url --value "$DB_URL" -o none
az keyvault secret set --vault-name "$KV" -n dwh-url --value "$DWH_URL" -o none
az keyvault secret set --vault-name "$KV" -n jwt-secret --value "$(openssl rand -hex 32)" -o none
az keyvault secret set --vault-name "$KV" -n foundry-key --value "${FOUNDRY_KEY:-none}" -o none

# ---------- 7. logs + Container Apps environment ----------
az monitor log-analytics workspace create -g "$RG" -n "$LAW" -l "$LOC" -o none
LAW_ID=$(az monitor log-analytics workspace show -g "$RG" -n "$LAW" --query customerId -o tsv)
LAW_KEY=$(az monitor log-analytics workspace get-shared-keys -g "$RG" -n "$LAW" --query primarySharedKey -o tsv)
az containerapp env create -n "$ENV" -g "$RG" -l "$LOC" --logs-workspace-id "$LAW_ID" --logs-workspace-key "$LAW_KEY" -o none

# ---------- 8. optional Service Bus queue + worker ----------
QUEUE_ENV="QUEUE_BACKEND=inprocess"
if [ "$USE_WORKER" = "true" ]; then
  az servicebus namespace create -n "$SB" -g "$RG" -l "$LOC" --sku Standard -o none
  az servicebus queue create --namespace-name "$SB" -g "$RG" -n bdx-pipeline --lock-duration PT5M -o none
  SB_ID=$(az servicebus namespace show -n "$SB" -g "$RG" --query id -o tsv)
  role "Azure Service Bus Data Owner" "$SB_ID"
  SB_CONN=$(az servicebus namespace authorization-rule keys list -g "$RG" --namespace-name "$SB" -n RootManageSharedAccessKey --query primaryConnectionString -o tsv)
  QUEUE_ENV="QUEUE_BACKEND=servicebus SERVICEBUS_NAMESPACE=$SB.servicebus.windows.net SERVICEBUS_QUEUE=bdx-pipeline"
fi

LLM_ENV="LLM_PROVIDER=none"
if [ -n "$FOUNDRY_RESOURCE" ]; then
  LLM_ENV="LLM_PROVIDER=anthropic_foundry ANTHROPIC_FOUNDRY_RESOURCE=$FOUNDRY_RESOURCE LLM_MODEL=$CLAUDE_DEPLOYMENT ANTHROPIC_FOUNDRY_API_KEY=secretref:foundry-key"
fi

SECRETS="db-url=keyvaultref:${KV_URI}secrets/db-url,identityref:$ID_ID \
dwh-url=keyvaultref:${KV_URI}secrets/dwh-url,identityref:$ID_ID \
jwt-secret=keyvaultref:${KV_URI}secrets/jwt-secret,identityref:$ID_ID \
foundry-key=keyvaultref:${KV_URI}secrets/foundry-key,identityref:$ID_ID"

COMMON_ENV="ENVIRONMENT=prod AZURE_CLIENT_ID=$ID_CLIENT DATABASE_URL=secretref:db-url DWH_DATABASE_URL=secretref:dwh-url \
JWT_SECRET=secretref:jwt-secret STORAGE_BACKEND=azure_blob AZURE_STORAGE_ACCOUNT_URL=https://$SA.blob.core.windows.net \
KEY_VAULT_URL=$KV_URI DWH_LOADER=sql $QUEUE_ENV $LLM_ENV"

# ---------- 9. API container app ----------
# shellcheck disable=SC2086
az containerapp create -n bdx-api -g "$RG" --environment "$ENV" \
  --image "$ACR.azurecr.io/bdx-api:$TAG" --registry-server "$ACR.azurecr.io" --registry-identity "$ID_ID" \
  --user-assigned "$ID_ID" --target-port 8000 --ingress external --min-replicas 1 --max-replicas 1 \
  --cpu 1.0 --memory 2.0Gi --secrets $SECRETS --env-vars $COMMON_ENV ENABLE_SCHEDULER=true -o none
API_FQDN=$(az containerapp show -n bdx-api -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)

# ---------- 10. worker (only with Service Bus) ----------
if [ "$USE_WORKER" = "true" ]; then
  # shellcheck disable=SC2086
  az containerapp create -n bdx-worker -g "$RG" --environment "$ENV" \
    --image "$ACR.azurecr.io/bdx-api:$TAG" --registry-server "$ACR.azurecr.io" --registry-identity "$ID_ID" \
    --user-assigned "$ID_ID" --command "python" --args "-m" "app.workers.worker" \
    --min-replicas 0 --max-replicas 5 --cpu 1.0 --memory 2.0Gi \
    --secrets $SECRETS "sb-conn=$SB_CONN" --env-vars $COMMON_ENV \
    --scale-rule-name queue --scale-rule-type azure-servicebus \
    --scale-rule-metadata "queueName=bdx-pipeline" "namespace=$SB" "messageCount=5" \
    --scale-rule-auth "connection=sb-conn" -o none
fi

# ---------- 11. UI container app ----------
az containerapp create -n bdx-ui -g "$RG" --environment "$ENV" \
  --image "$ACR.azurecr.io/bdx-ui:$TAG" --registry-server "$ACR.azurecr.io" --registry-identity "$ID_ID" \
  --user-assigned "$ID_ID" --target-port 80 --ingress external --min-replicas 1 \
  --env-vars "API_UPSTREAM=https://$API_FQDN" -o none
UI_FQDN=$(az containerapp show -n bdx-ui -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
az containerapp update -n bdx-api -g "$RG" --set-env-vars "CORS_ORIGINS=https://$UI_FQDN" -o none

cat <<OUT

================================================================
 Done.
   UI:   https://$UI_FQDN        (analyst@lloyds.com / demo  -> change! set SEED_DEMO_USERS=false)
   API:  https://$API_FQDN/docs
   Postgres admin password: $PG_PW   (also inside Key Vault secret db-url)
 Next: docs/AZURE_GUIDE.md section 8 (verify) and section 9 (hardening).
 Tear down everything:  az group delete -n $RG --yes
================================================================
OUT
