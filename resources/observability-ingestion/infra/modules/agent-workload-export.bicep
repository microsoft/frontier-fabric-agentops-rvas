// Adds a Log Analytics Data Export rule to an EXISTING workspace that lives in
// ANOTHER resource group (the agent-workload deployment), pointing at the
// observability storage account. This lets observability-ingestion wire up the
// agent-workload workspace export even though that workspace was created by a
// separate deployment before this storage account existed.
//
// NOTE: Log Analytics Data Export requires the destination storage account to be
// in the SAME region as the source workspace.

@description('Name of the existing agent-workload Log Analytics workspace to attach the export rule to.')
param workspaceName string

@description('Resource ID of the destination (observability) storage account.')
param storageAccountId string

@description('Name of the data export rule.')
param dataExportName string = 'exportToObsStorage'

@description('Tables to export.')
param tableNames array = [
  'AppRequests'
  'AppDependencies'
  'AppTraces'
  'AppMetrics'
]

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource dataExportRule 'Microsoft.OperationalInsights/workspaces/dataExports@2020-08-01' = {
  parent: workspace
  name: dataExportName
  properties: {
    destination: {
      resourceId: storageAccountId
    }
    tableNames: tableNames
    enable: true
  }
}

@description('The name of the data export rule created on the agent-workload workspace.')
output dataExportName string = dataExportRule.name
