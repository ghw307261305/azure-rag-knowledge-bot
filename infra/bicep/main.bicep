// Azure RAG Knowledge Bot infrastructure
// Deploys:
// - Shared Linux App Service Plan
// - Linux App Service for the FastAPI backend
// - Linux App Service for the React frontend

@description('Primary location for the resource group scoped resources. Defaults to Japan East.')
param location string = 'japaneast'

@description('Logical application name used when explicit resource names are not supplied.')
param appName string = 'rag-demo-dev'

@description('Python runtime version for the backend app.')
param pythonVersion string = '3.11'

@description('Node.js runtime version for the frontend app.')
param nodeVersion string = '20-lts'

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

@description('Optional explicit frontend App Service name.')
param frontendAppName string = ''

@allowed([
  'F1'
  'B1'
  'B2'
  'B3'
])
@description('App Service Plan SKU. Defaults to the Free tier (F1) for the Linux backend.')
param appServicePlanSkuName string = 'F1'

@description('Set to false when you want to deploy only the backend or reuse an existing frontend app.')
param deployFrontendApp bool = true

var resolvedAppServicePlanName = empty(appServicePlanName) ? 'asp-${appName}' : appServicePlanName
var resolvedBackendAppName = empty(backendAppName) ? 'app-${appName}-backend' : backendAppName
var resolvedFrontendAppName = empty(frontendAppName) ? 'app-${appName}-frontend' : frontendAppName
var appServicePlanSkuTier = {
  F1: 'Free'
  B1: 'Basic'
  B2: 'Basic'
  B3: 'Basic'
}[appServicePlanSkuName]
var enableAlwaysOn = appServicePlanSkuName != 'F1'
var resolvedFrontendOrigin = !empty(frontendUrl) ? frontendUrl : (deployFrontendApp ? 'https://${frontendApp!.properties.defaultHostName}' : '*')

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
        { name: 'CORS_ORIGIN', value: resolvedFrontendOrigin }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1' }
      ]
    }
  }
}

resource frontendApp 'Microsoft.Web/sites@2023-12-01' = if (deployFrontendApp) {
  name: resolvedFrontendAppName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'NODE|${nodeVersion}'
      appCommandLine: 'pm2 serve /home/site/wwwroot 8080 --no-daemon --spa'
      alwaysOn: enableAlwaysOn
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'NODE_ENV', value: 'production' }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'false' }
        { name: 'WEBSITE_RUN_FROM_PACKAGE', value: '1' }
      ]
    }
  }
}

output backendUrl string = 'https://${appService.properties.defaultHostName}'
output frontendUrl string = deployFrontendApp ? 'https://${frontendApp!.properties.defaultHostName}' : ''
output appServicePlanName string = resolvedAppServicePlanName
output backendAppName string = resolvedBackendAppName
output frontendAppName string = deployFrontendApp ? resolvedFrontendAppName : ''
