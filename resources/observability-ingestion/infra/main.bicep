targetScope = 'resourceGroup'

@description('Environment name used as a prefix for all resources.')
@minLength(1)
@maxLength(12)
param environmentName string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Subscription ID used as the scope for Cost Management exports.')
param exportScope string = subscription().subscriptionId

var resourceToken = toLower(uniqueString(resourceGroup().id, environmentName))
var storageAccountName = 'st${replace(resourceToken, '-', '')}obs'
var workspaceName = 'law-${environmentName}-${resourceToken}'
var keyVaultName = 'kv-${environmentName}-${resourceToken}'
var managedIdentityName = 'id-${environmentName}-observability'
var costExportName = 'export-${environmentName}-focus-daily'

var tags = {
  environment: environmentName
  project: 'observability-platform'
  demo: 'demo-2-ingestion'
}

// ─── Managed Identity ────────────────────────────────────────────────────────

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: managedIdentityName
  location: location
  tags: tags
}

// ─── Storage Account (ADLS Gen2) ─────────────────────────────────────────────

module storage 'modules/storage.bicep' = {
  name: 'storageDeployment'
  params: {
    storageAccountName: storageAccountName
    location: location
    tags: tags
  }
}

// ─── Storage Blob Data Contributor Role Assignment ───────────────────────────

resource storageBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, managedIdentity.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: resourceGroup()
  properties: {
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
    )
  }
}

// ─── Log Analytics Workspace ─────────────────────────────────────────────────

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoringDeployment'
  params: {
    workspaceName: workspaceName
    location: location
    storageAccountId: storage.outputs.storageAccountId
    tags: tags
  }
}

// ─── Diagnostic Settings on Log Analytics Workspace ──────────────────────────

module diagnosticSettings 'modules/diagnostic-settings.bicep' = {
  name: 'diagnosticSettingsDeployment'
  params: {
    diagnosticSettingName: 'diag-${workspaceName}'
    targetWorkspaceName: monitoring.outputs.workspaceName
    workspaceId: monitoring.outputs.workspaceId
    storageAccountId: storage.outputs.storageAccountId
  }
}

// ─── Cost Management Export (Subscription Scope) ─────────────────────────────

module costExport 'modules/cost-export.bicep' = {
  name: 'costExportDeployment'
  scope: subscription()
  params: {
    exportName: costExportName
    storageAccountId: storage.outputs.storageAccountId
  }
}

// ─── Key Vault ───────────────────────────────────────────────────────────────

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: false
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

resource storageConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'storage-account-name'
  properties: {
    value: storage.outputs.storageAccountName
  }
}

resource workspaceIdSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'workspace-id'
  properties: {
    value: monitoring.outputs.workspaceCustomerId
  }
}

// ─── Outputs ─────────────────────────────────────────────────────────────────

output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.storageAccountName
output AZURE_STORAGE_ACCOUNT_ID string = storage.outputs.storageAccountId
output AZURE_LOG_ANALYTICS_WORKSPACE_NAME string = monitoring.outputs.workspaceName
output AZURE_LOG_ANALYTICS_WORKSPACE_ID string = monitoring.outputs.workspaceId
output AZURE_KEY_VAULT_NAME string = keyVault.name
output AZURE_MANAGED_IDENTITY_CLIENT_ID string = managedIdentity.properties.clientId
output AZURE_MANAGED_IDENTITY_NAME string = managedIdentity.name
