@description('Name of the Log Analytics workspace.')
param workspaceName string

@description('Azure region for the workspace.')
param location string

@description('Resource ID of the destination storage account for data export.')
param storageAccountId string

@description('Tags to apply to all resources.')
param tags object = {}

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 90
    features: {
      enableDataExport: true
    }
    workspaceCapping: {
      dailyQuotaGb: 5
    }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource dataExportRule 'Microsoft.OperationalInsights/workspaces/dataExports@2020-08-01' = {
  parent: workspace
  name: 'exportToStorage'
  properties: {
    destination: {
      resourceId: storageAccountId
    }
    tableNames: [
      'AppRequests'
      'AppDependencies'
      'AppTraces'
      'AppExceptions'
      'AppMetrics'
    ]
    enable: true
  }
}

@description('The resource ID of the Log Analytics workspace.')
output workspaceId string = workspace.id

@description('The name of the Log Analytics workspace.')
output workspaceName string = workspace.name

@description('The customer ID (workspace ID GUID) for the Log Analytics workspace.')
output workspaceCustomerId string = workspace.properties.customerId
