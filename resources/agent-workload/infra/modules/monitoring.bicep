@description('Azure region for all resources.')
param location string

@description('Environment name used for resource naming.')
param environmentName string

@description('Tags to apply to all resources.')
param tags object = {}

@description('Resource ID of the observability storage account for App telemetry data export. Empty disables the export rule.')
param dataExportStorageAccountId string = ''

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${environmentName}-log'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
      enableDataExport: true
    }
    workspaceCapping: {
      dailyQuotaGb: 1
    }
  }
}

// Export App telemetry tables to the observability storage account (Fabric landing zone).
resource appTelemetryExport 'Microsoft.OperationalInsights/workspaces/dataExports@2020-08-01' = if (!empty(dataExportStorageAccountId)) {
  parent: logAnalyticsWorkspace
  name: 'exportToStorage'
  properties: {
    destination: {
      resourceId: dataExportStorageAccountId
    }
    tableNames: [
      'AppRequests'
      'AppDependencies'
      'AppTraces'
      'AppMetrics'
    ]
    enable: true
  }
}

resource applicationInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${environmentName}-appinsights'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    RetentionInDays: 30
  }
}

@description('Resource ID of the Log Analytics workspace.')
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id

@description('Application Insights connection string.')
output applicationInsightsConnectionString string = applicationInsights.properties.ConnectionString

@description('Application Insights instrumentation key.')
output applicationInsightsInstrumentationKey string = applicationInsights.properties.InstrumentationKey

@description('Application Insights resource name.')
output applicationInsightsName string = applicationInsights.name

@description('Resource ID of the Application Insights component.')
output applicationInsightsId string = applicationInsights.id
