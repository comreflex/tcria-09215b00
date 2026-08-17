# Azure Deployment

The TCRIA MCP gateway is a stateless FastAPI service packaged in
`Dockerfile.mcp`. It runs on any Azure container platform without code
changes. The container honors `$PORT` (falling back to `8000`), so it
works out-of-the-box on Azure App Service, Container Apps, and Container
Instances.

## Option A — Azure Container Apps (recommended)

Serverless containers with scale-to-zero and built-in HTTPS ingress.

```bash
# 1. Prerequisites: az login; az extension add --name containerapp
RG=tcria-rg
LOCATION=eastus
ACR=tcriaacr
ENV=tcria-env
APP=tcria-mcp-gateway

az group create --name $RG --location $LOCATION

az acr create --resource-group $RG --name $ACR --sku Basic --admin-enabled true

# 2. Build & push image
az acr build --registry $ACR --image tcria-mcp-gateway:latest \
  --file Dockerfile.mcp .

# 3. Create Container Apps environment
az containerapp env create --name $ENV --resource-group $RG --location $LOCATION

# 4. Deploy (edit deploy/azure/containerapp.yaml first, replacing
#    <ACR_NAME> and <IMAGE_TAG>)
az containerapp create --name $APP --resource-group $RG \
  --environment $ENV --yaml deploy/azure/containerapp.yaml

# 5. Set the required secrets
az containerapp secret set --name $APP --resource-group $RG \
  --secrets tcria-mcp-jwt-secret=... tcria-mcp-signing-secret=...
```

CI/CD is wired up via `.github/workflows/azure-container-apps.yml`.

## Option B — Azure App Service for Containers

```bash
RG=tcria-rg
ACR=tcriaacr
PLAN=tcria-plan
APP=tcria-mcp-gateway

az acr build --registry $ACR --image tcria-mcp-gateway:latest \
  --file Dockerfile.mcp .

az appservice plan create --name $PLAN --resource-group $RG \
  --is-linux --sku B1

az webapp create --resource-group $RG --plan $PLAN --name $APP \
  --deployment-container-image-name $ACR.azurecr.io/tcria-mcp-gateway:latest

az webapp config appsettings set --resource-group $RG --name $APP \
  --settings WEBSITES_PORT=8000 TCRIA_MCP_REQUIRE_AUTH=true
```

Set `TCRIA_MCP_JWT_SECRET` and `TCRIA_MCP_SIGNING_SECRET` as app settings
(or Key Vault references).

## Option C — Azure Container Instances (one-off)

```bash
az container create --resource-group $RG --name tcria-mcp-gateway \
  --image $ACR.azurecr.io/tcria-mcp-gateway:latest \
  --registry-login-server $ACR.azurecr.io \
  --dns-name-label tcria-mcp --ports 8000 \
  --environment-variables PORT=8000 TCRIA_MCP_REQUIRE_AUTH=true
```

## Required environment variables

| Variable | Required | Notes |
|---|---|---|
| `PORT` | no | Injected by platform; container falls back to `8000` |
| `TCRIA_MCP_REQUIRE_AUTH` | yes | Set to `true` in production |
| `TCRIA_MCP_PUBLIC_URL` | yes | Public HTTPS URL of the deployment |
| `TCRIA_MCP_JWT_SECRET` | yes | Store as a secret / Key Vault reference |
| `TCRIA_MCP_SIGNING_SECRET` | yes | Store as a secret / Key Vault reference |

## Storage

The container filesystem is ephemeral. For generated PDF artifacts that
must persist, mount Azure Files onto the container or write output to
Azure Blob Storage.
