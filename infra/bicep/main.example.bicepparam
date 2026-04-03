using './main.bicep'

// Resource group region for App Service resources.
param location = 'japaneast'

// Logical app name used for default resource names.
param appName = 'rag-demo-dev'

// Default to the free App Service plan in Japan East.
param appServicePlanSkuName = 'F1'

// Deploy the frontend into the same Japan East App Service plan.
param deployFrontendApp = true

// Set a unique frontend web app name if the default name is already in use.
param frontendAppName = 'app-rag-demo-dev-frontend'

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
