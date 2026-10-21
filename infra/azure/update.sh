#!/usr/bin/env bash
# Redeploy new code after changes:  RG=rg-xxx PREFIX=xxx bash infra/azure/update.sh
set -euo pipefail
: "${RG:?set RG}" "${PREFIX:?set PREFIX}"
ACR="${PREFIX}acr"; TAG="v$(date +%Y%m%d%H%M)"
az acr build -r "$ACR" -t "bdx-api:$TAG" ./backend -o none
az acr build -r "$ACR" -t "bdx-ui:$TAG" ./frontend -o none
az containerapp update -n bdx-api -g "$RG" --image "$ACR.azurecr.io/bdx-api:$TAG" -o none
az containerapp show -n bdx-worker -g "$RG" -o none 2>/dev/null && \
  az containerapp update -n bdx-worker -g "$RG" --image "$ACR.azurecr.io/bdx-api:$TAG" -o none
az containerapp update -n bdx-ui -g "$RG" --image "$ACR.azurecr.io/bdx-ui:$TAG" -o none
echo "updated to $TAG"
