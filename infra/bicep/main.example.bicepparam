using './main.bicep'

// Resource group region for App Service resources.
param location = 'japaneast'

// Logical app name used for default resource names.
param appName = 'rag-demo-dev'

// Free App Service plans often fail with "Free VMs quota = 0".
param appServicePlanSkuName = 'B1'

// If the Static Web App already exists, keep its original region here.
// If you want a brand new frontend resource, change the name below as well.
param staticWebAppLocation = 'eastasia'

// Deploy backend first. Switch to true only after deciding whether to reuse
// the existing Static Web App in eastasia or create a new unique one.
param deployStaticWebApp = false

// Set this to an existing Static Web App name in eastasia, or a new unique name.
param staticWebAppName = 'swa-rag-demo-dev-frontend'

// Fill in your actual Azure resource values before deployment.
param azureOpenAiEndpoint = 'https://<your-openai-resource>.openai.azure.com/'
param azureOpenAiApiKey = '<your-openai-api-key>'
param azureOpenAiChatDeployment = 'gpt-4o'
param azureOpenAiEmbeddingDeployment = 'text-embedding-3-large'
param azureSearchEndpoint = 'https://<your-search-resource>.search.windows.net'
param azureSearchApiKey = '<your-search-api-key>'
param azureSearchIndexName = 'knowledge-index'

// Optional. Set this after the frontend URL is known if you want locked-down CORS.
param frontendUrl = ''
