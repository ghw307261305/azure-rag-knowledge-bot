// Azure RAG Knowledge Bot infrastructure
// Deploys:
// - Linux App Service Plan
// - Linux App Service for the FastAPI backend
// - Azure Static Web Apps for the React frontend

@description('Primary location for the resource group scoped resources.')
param location string = resourceGroup().location

@description('Logical application name used when explicit resource names are not supplied.')
param appName string = 'rag-demo-dev'

@description('Python runtime version for the backend app.')
param pythonVersion string = '3.11'

@description('Azure OpenAI endpoint.')
param azureOpenAiEndpoint string

@description('Azure OpenAI API key.')
@secure()
param azureOpenAiApiKey string

@description('Azure OpenAI chat deployment name.')
param azureOpenAiChatDeployment string = 'gpt-4o'

@description('Azure OpenAI embedding deployment name.')
param azureOpenAiEmbeddingDeployment string = 'text-embedding-3-large'

@description('Azure AI Search endpoint.')
param azureSearchEndpoint string

@description('Azure AI Search API key.')
@secure()
param azureSearchApiKey string

@description('Azure AI Search index name.')
param azureSearchIndexName string = 'knowledge-index'

@description('Allowed frontend origin for CORS. Leave empty to allow all origins.')
param frontendUrl string = ''

@description('Optional explicit App Service Plan name.')
param appServicePlanName string = ''

@description('Optional explicit backend App Service name.')
param backendAppName string = ''

@description('Optional explicit Static Web App name.')
param staticWebAppName string = ''

@allowed([
  'F1'
  'B1'
  'B2'
  'B3'
])
@description('App Service Plan SKU. Use B1 or above when the subscription has no Free VM quota in the target region.')
param appServicePlanSkuName string = 'B1'

@description('Location for the Static Web App. Keep this aligned with the existing resource location when redeploying the same name.')
param staticWebAppLocation string = 'eastasia'

@description('Set to false when you want to deploy only the backend or reuse an existing Static Web App.')
param deployStaticWebApp bool = true

var resolvedAppServicePlanName = empty(appServicePlanName) ? 'asp-${appName}' : appServicePlanName
var resolvedBackendAppName = empty(backendAppName) ? 'app-${appName}-backend' : backendAppName
var resolvedStaticWebAppName = empty(staticWebAppName) ? 'swa-${appName}-frontend' : staticWebAppName
var corsOrigins = empty(frontendUrl) ? '*' : frontendUrl
var appServicePlanSkuTier = {
  F1: 'Free'
  B1: 'Basic'
  B2: 'Basic'
  B3: 'Basic'
}[appServicePlanSkuName]
var enableAlwaysOn = appServicePlanSkuName != 'F1'

resource appServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: resolvedAppServicePlanName
  location: location
  sku: {
    name: appServicePlanSkuName
    tier: appServicePlanSkuTier
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource appService 'Microsoft.Web/sites@2023-12-01' = {
  name: resolvedBackendAppName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'PYTHON|${pythonVersion}'
      appCommandLine: 'uvicorn main:app --host 0.0.0.0 --port 8000'
      alwaysOn: enableAlwaysOn
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'APP_ENV', value: 'production' }
        { name: 'LOG_LEVEL', value: 'INFO' }
        { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
        { name: 'AZURE_OPENAI_API_KEY', value: azureOpenAiApiKey }
        { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: azureOpenAiChatDeployment }
        { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: azureOpenAiEmbeddingDeployment }
        { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
        { name: 'AZURE_SEARCH_API_KEY', value: azureSearchApiKey }
        { name: 'AZURE_SEARCH_INDEX_NAME', value: azureSearchIndexName }
        { name: 'TOP_K', value: '5' }
        { name: 'MAX_CHUNKS', value: '5' }
        { name: 'CORS_ORIGIN', value: corsOrigins }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1' }
      ]
    }
  }
}

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = if (deployStaticWebApp) {
  name: resolvedStaticWebAppName
  location: staticWebAppLocation
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    buildProperties: {
      appLocation: 'frontend'
      outputLocation: 'dist'
    }
  }
}

output backendUrl string = 'https://${appService.properties.defaultHostName}'
output frontendUrl string = deployStaticWebApp ? 'https://${staticWebApp!.properties.defaultHostname}' : ''
output appServicePlanName string = resolvedAppServicePlanName
output backendAppName string = resolvedBackendAppName
output frontendAppName string = deployStaticWebApp ? resolvedStaticWebAppName : ''
