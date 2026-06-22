targetScope = 'resourceGroup'

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------

@minLength(1)
@maxLength(64)
@description('Name of the environment (e.g. dev, staging, prod). Used as a suffix in resource names.')
param environmentName string

@description('Primary Azure region for all resources.')
param location string = resourceGroup().location

@description('Tags applied to every resource.')
param tags object = {}

// ---------------------------------------------------------------------------
// Variables
// ---------------------------------------------------------------------------

var abbrs = {
  storageAccount: 'st'
  keyVault: 'kv'
  managedIdentity: 'id'
}

var resourceToken = uniqueString(resourceGroup().id, environmentName)

var defaultTags = union(tags, {
  'azd-env-name': environmentName
})

// ---------------------------------------------------------------------------
// Managed Identity
// ---------------------------------------------------------------------------

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${abbrs.managedIdentity}-fabric-${resourceToken}'
  location: location
  tags: defaultTags
}

// ---------------------------------------------------------------------------
// ADLS Gen2 Storage Account (for Fabric external shortcuts)
// ---------------------------------------------------------------------------

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${abbrs.storageAccount}fabric${resourceToken}'
  location: location
  tags: defaultTags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    isHnsEnabled: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }

  resource blobServices 'blobServices' = {
    name: 'default'

    resource container 'containers' = {
      name: 'fabric-shortcuts'
      properties: {
        publicAccess: 'None'
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Storage Blob Data Contributor role assignment for managed identity
// ---------------------------------------------------------------------------

var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource storageBlobRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, storageBlobDataContributorRoleId)
  scope: storageAccount
  properties: {
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
  }
}

// ---------------------------------------------------------------------------
// Key Vault (for connection strings & secrets)
// ---------------------------------------------------------------------------

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: '${abbrs.keyVault}-fabric-${resourceToken}'
  location: location
  tags: defaultTags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Key Vault Secrets Officer role for the managed identity
var keyVaultSecretsOfficerRoleId = 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

resource keyVaultRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, keyVaultSecretsOfficerRoleId)
  scope: keyVault
  properties: {
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsOfficerRoleId)
  }
}

// Store the ADLS connection string in Key Vault
resource storageConnectionSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'adls-storage-account-name'
  properties: {
    value: storageAccount.name
    contentType: 'text/plain'
  }
}

resource storageDfsEndpointSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'adls-dfs-endpoint'
  properties: {
    value: storageAccount.properties.primaryEndpoints.dfs
    contentType: 'text/plain'
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output MANAGED_IDENTITY_NAME string = managedIdentity.name
output MANAGED_IDENTITY_PRINCIPAL_ID string = managedIdentity.properties.principalId
output MANAGED_IDENTITY_CLIENT_ID string = managedIdentity.properties.clientId
output STORAGE_ACCOUNT_NAME string = storageAccount.name
output STORAGE_ACCOUNT_DFS_ENDPOINT string = storageAccount.properties.primaryEndpoints.dfs
output STORAGE_CONTAINER_NAME string = storageAccount::blobServices::container.name
output KEY_VAULT_NAME string = keyVault.name
output KEY_VAULT_URI string = keyVault.properties.vaultUri
