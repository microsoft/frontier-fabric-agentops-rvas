targetScope = 'resourceGroup'

@description('Environment name used as a prefix for all resources.')
@minLength(1)
@maxLength(12)
param environmentName string

@description('Azure region for all resources.')
param location string = resourceGroup().location

@description('Subscription ID used as the scope for Cost Management exports.')
param exportScope string = subscription().subscriptionId

@description('Object ID of the user or principal running the deployment. Granted Storage Blob Data Contributor so it can read/write blobs (e.g. running resource_graph_export.py). Populated automatically by azd via AZURE_PRINCIPAL_ID.')
param deploymentUserPrincipalId string = ''

@description('Resource group of the OTHER (agent-workload) deployment whose Log Analytics workspace should also export App telemetry to this observability storage account. azd prompts for this at provision time; leave blank to skip the cross-resource-group export.')
param agentWorkloadResourceGroupName string

@description('Name of the agent-workload Log Analytics workspace (created as "<agentWorkloadEnvName>-log") to attach the export rule to. azd prompts for this at provision time; leave blank to skip the cross-resource-group export.')
param agentWorkloadWorkspaceName string

//var resourceToken = toLower(uniqueString(resourceGroup().id, environmentName))

var resourceToken = substring(toLower(uniqueString(resourceGroup().id, environmentName)),0,12)

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

// ─── Storage Blob Data Contributor for the deploying user ────────────────────

resource userStorageBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deploymentUserPrincipalId)) {
  name: guid(resourceGroup().id, deploymentUserPrincipalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: resourceGroup()
  properties: {
    principalId: deploymentUserPrincipalId
    principalType: 'User'
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
// DISABLED (commented, not deleted): configuring diagnostic settings across
// resources is no longer used. We rely ONLY on the Log Analytics Data Export
// rule (see modules/monitoring.bicep) to land App telemetry into the
// observability storage account. See also the disabled src/scripts/
// setup_diagnostic_settings.py which stamped diagnostics on ALL resources.
//
// module diagnosticSettings 'modules/diagnostic-settings.bicep' = {
//   name: 'diagnosticSettingsDeployment'
//   params: {
//     diagnosticSettingName: 'diag-${workspaceName}'
//     targetWorkspaceName: monitoring.outputs.workspaceName
//     workspaceId: monitoring.outputs.workspaceId
//     storageAccountId: storage.outputs.storageAccountId
//   }
// }

// ─── Data Export on the agent-workload workspace (OTHER resource group) ───────
// Adds the App-telemetry Data Export rule to the agent-workload Log Analytics
// workspace (in its own resource group) so BOTH workspaces land data in the
// observability storage account during THIS deployment. Skipped automatically
// when the resource group / workspace name are left blank.

module agentWorkloadExport 'modules/agent-workload-export.bicep' = if (!empty(agentWorkloadResourceGroupName) && !empty(agentWorkloadWorkspaceName)) {
  name: 'agentWorkloadExportDeployment'
  scope: resourceGroup(agentWorkloadResourceGroupName)
  params: {
    workspaceName: agentWorkloadWorkspaceName
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
    //enablePurgeProtection: false
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
output AGENT_WORKLOAD_RESOURCE_GROUP string = agentWorkloadResourceGroupName
output AGENT_WORKLOAD_WORKSPACE_NAME string = agentWorkloadWorkspaceName
