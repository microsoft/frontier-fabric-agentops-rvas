targetScope = 'resourceGroup'

@description('Environment name used for resource naming.')
param environmentName string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Azure AI Foundry model deployment name.')
param openAiModelName string = 'gpt-5.4'

@description('Object ID of the user/principal running the deployment. Granted Foundry Owner on the Foundry resource.')
param principalId string = ''

var tags = {
  environment: environmentName
  project: 'observability-platform'
  'azd-env-name': environmentName
}

var foundryProjectName = '${environmentName}-project'
var foundryAgentName = '${environmentName}-agent'
var aiProjectEndpoint = 'https://${environmentName}-foundry.services.ai.azure.com/api/projects/${foundryProjectName}'

// ── User-Assigned Managed Identity ────────────────────────────────────────────

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${environmentName}-identity'
  location: location
  tags: tags
}

// ── Monitoring (Log Analytics + Application Insights) ─────────────────────────

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    environmentName: environmentName
    tags: tags
  }
}

// ── Cosmos DB ─────────────────────────────────────────────────────────────────

module cosmosDb 'modules/cosmos-db.bicep' = {
  name: 'cosmos-db'
  params: {
    location: location
    environmentName: environmentName
    tags: tags
  }
}

// ── Azure AI Foundry (AI Services) ────────────────────────────────────────────

resource cognitiveAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${environmentName}-foundry'
  location: location
  tags: tags
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: '${environmentName}-foundry'
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

resource openAiDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: cognitiveAccount
  name: openAiModelName
  sku: {
    name: 'GlobalStandard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: openAiModelName
      version: '2026-03-05'
    }
  }
}

// Attach the Foundry resource to Application Insights for agent tracing/observability
resource foundryAppInsightsConnection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  parent: cognitiveAccount
  name: 'appinsights-connection'
  properties: {
    category: 'AppInsights'
    target: monitoring.outputs.applicationInsightsId
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: monitoring.outputs.applicationInsightsConnectionString
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: monitoring.outputs.applicationInsightsId
    }
  }
}

// Foundry project – hosts the Agent Service where the agent runs on the deployed model
resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: cognitiveAccount
  name: foundryProjectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: '${environmentName} agent project'
    description: 'Foundry project hosting the observability demo agent.'
  }
}

// ── Key Vault ─────────────────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${environmentName}-kv'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    //enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
  }
}

// ── Container Apps (Environment, Registry, Apps) ──────────────────────────────

module containerApps 'modules/container-apps.bicep' = {
  name: 'container-apps'
  params: {
    location: location
    environmentName: environmentName
    tags: tags
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    applicationInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
    cosmosDbEndpoint: cosmosDb.outputs.cosmosDbEndpoint
    openAiEndpoint: cognitiveAccount.properties.endpoint
    openAiDeploymentName: openAiModelName
    aiProjectEndpoint: aiProjectEndpoint
    foundryAgentName: foundryAgentName
    managedIdentityId: managedIdentity.id
    managedIdentityClientId: managedIdentity.properties.clientId
    managedIdentityPrincipalId: managedIdentity.properties.principalId
  }
}

// ── API Management ────────────────────────────────────────────────────────────

module apiManagement 'modules/api-management.bicep' = {
  name: 'api-management'
  params: {
    location: location
    environmentName: environmentName
    tags: tags
    frontendFqdn: containerApps.outputs.frontendFqdn
    backendFqdn: containerApps.outputs.backendFqdn
    agentFqdn: containerApps.outputs.agentFqdn
  }
}

// ── Role Assignments ──────────────────────────────────────────────────────────

// Cosmos DB Data Contributor – allows managed identity to read/write Cosmos data
// Use deterministic name matching the cosmos-db module to avoid BCP120
var cosmosDbAccountName = '${environmentName}-cosmos'
var cosmosDbDataContributorRoleId = '00000000-0000-0000-0000-000000000002'

resource cosmosDbAccountRef 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = {
  name: cosmosDbAccountName
}

resource cosmosDbRoleAssignment 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-05-15' = {
  parent: cosmosDbAccountRef
  name: guid(cosmosDbAccountName, managedIdentity.id, cosmosDbDataContributorRoleId)
  properties: {
    roleDefinitionId: '${cosmosDbAccountRef.id}/sqlRoleDefinitions/${cosmosDbDataContributorRoleId}'
    principalId: managedIdentity.properties.principalId
    scope: cosmosDbAccountRef.id
  }
  dependsOn: [cosmosDb]
}

// Key Vault Secrets User – allows managed identity to read secrets
var keyVaultSecretsUserRoleDefinitionId = '4633458b-17de-408a-b874-0445c86b69e6'

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleDefinitionId)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services OpenAI User – allows managed identity to call the Foundry-hosted model
var cognitiveServicesOpenAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource openAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cognitiveAccount.id, managedIdentity.id, cognitiveServicesOpenAiUserRoleId)
  scope: cognitiveAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAiUserRoleId)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services User – grants the agents data action (AIServices/agents/*) used by the Responses API
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource cognitiveServicesUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cognitiveAccount.id, managedIdentity.id, cognitiveServicesUserRoleId)
  scope: cognitiveAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Azure AI Developer – allows managed identity to create and run agents in the Foundry project
var azureAiDeveloperRoleId = '64702f94-c441-49e6-a78b-ef80e0188fee'

resource aiDeveloperRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryProject.id, managedIdentity.id, azureAiDeveloperRoleId)
  scope: foundryProject
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', azureAiDeveloperRoleId)
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Foundry Owner – grants the deploying user full ownership of the Foundry resource
var foundryOwnerRoleId = 'c883944f-8b7b-4483-af10-35834be79c4a'

resource foundryOwnerRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(cognitiveAccount.id, principalId, foundryOwnerRoleId)
  scope: cognitiveAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', foundryOwnerRoleId)
    principalId: principalId
    principalType: 'User'
  }
}

// ── Outputs ───────────────────────────────────────────────────────────────────

output AZURE_CONTAINER_REGISTRY_NAME string = containerApps.outputs.containerRegistryName
output AZURE_CONTAINER_REGISTRY_LOGIN_SERVER string = containerApps.outputs.containerRegistryLoginServer
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerApps.outputs.containerRegistryLoginServer
output AZURE_COSMOS_DB_ENDPOINT string = cosmosDb.outputs.cosmosDbEndpoint
output AZURE_KEY_VAULT_NAME string = keyVault.name
output AZURE_OPENAI_ENDPOINT string = cognitiveAccount.properties.endpoint
output AZURE_OPENAI_DEPLOYMENT string = openAiModelName
output AZURE_AI_PROJECT_ENDPOINT string = aiProjectEndpoint
output AZURE_AI_AGENT_NAME string = foundryAgentName
output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.applicationInsightsConnectionString
output APPLICATIONINSIGHTS_NAME string = monitoring.outputs.applicationInsightsName
output AZURE_APIM_GATEWAY_URL string = apiManagement.outputs.apimGatewayUrl
output FRONTEND_FQDN string = containerApps.outputs.frontendFqdn
output BACKEND_FQDN string = containerApps.outputs.backendFqdn
output AGENT_FQDN string = containerApps.outputs.agentFqdn
output AZURE_MANAGED_IDENTITY_CLIENT_ID string = managedIdentity.properties.clientId
