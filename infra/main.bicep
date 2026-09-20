targetScope = 'resourceGroup'

@minLength(1)
@maxLength(64)
@description('The azd environment name used to derive resource names.')
param environmentName string

@metadata({
  azd: {
    type: 'location'
    default: 'eastus'
  }
})
@description('Azure region for the resource group and monitoring resources.')
param location string

@description('Optional Function App name override.')
param functionAppName string = ''

@description('Optional storage account name override. It must be globally unique and contain only lowercase letters and numbers.')
param storageAccountName string = ''

@description('Optional App Service plan name override.')
param functionPlanName string = ''

@description('Optional Application Insights name override.')
param appInsightsName string = ''

@description('Optional Log Analytics workspace name override.')
param logAnalyticsWorkspaceName string = ''

@description('Run the collector without sending Teams notifications or executing remediation. Keep true for an initial validation run.')
param dryRun bool = true

@description('Enable the Teams notification path when a webhook URL is configured.')
param notificationsEnabled bool = true

@description('Allow Teams notifications while dry-run is true. This is false by default.')
param sendNotificationsInDryRun bool = false

@description('Enable the Cloud PC recommendation report collection. Microsoft documents this report action as requiring CloudPC.ReadWrite.All.')
param recommendationsEnabled bool = false

@allowed([
  'v1.0'
  'beta'
])
@description('Microsoft Graph API version used for Cloud PC inventory. beta exposes the status, connectivity, and last-login fields used by the first milestone.')
param graphApiVersion string = 'beta'

@description('Timer trigger schedule in NCRONTAB format. The default runs hourly at minute zero.')
param monitorSchedule string = '0 0 * * * *'

@minValue(1)
@description('Days without a recorded Cloud PC login before the unused rule becomes eligible.')
param unusedCloudPcDays int = 30

@minValue(1)
@description('Days without an Intune sync before the stale-device rule becomes eligible.')
param staleDeviceDays int = 14

@minValue(0)
@description('Minutes a provisioning failure must remain observed before notification.')
param provisioningFailureGraceMinutes int = 60

@minValue(0)
@description('Minutes an unhealthy or stale condition must remain observed before notification.')
param unhealthyDeviceGraceMinutes int = 60

@minValue(0)
@description('Hours before an active alert may be sent again.')
param notificationRenotifyHours int = 24

@minValue(7)
@maxValue(365)
@description('Days to retain JSON audit exports in Blob Storage.')
param reportRetentionDays int = 30

@minLength(3)
@description('Blob container used for compact audit exports.')
param reportContainerName string = 'reports'

@minLength(3)
@description('Table used for alert, observation, acknowledgement, and notification state.')
param stateTableName string = 'CloudPcState'

@description('Maximum concurrent Flex Consumption instances for the scheduled monitor.')
@minValue(1)
@maxValue(1000)
param maximumInstanceCount int = 1

@description('Optional JSON array that replaces the built-in rule definitions.')
param ruleConfigJson string = ''

@description('Comma-separated rule IDs or Cloud PC IDs to suppress.')
param alertSuppressions string = ''

@secure()
@description('Optional Teams Workflows webhook URL. Do not commit a value to source control.')
param teamsWebhookUrl string = ''

@description('URL included in alert cards for operator action. Set this to the tenant-specific Intune Cloud PC view when known.')
param intuneCloudPcUrl string = 'https://intune.microsoft.com/'

@description('Grant the Function App identity the Microsoft Graph application roles during the postprovision hook.')
param graphRoleAssignmentsEnabled bool = true

@description('Reserved future remediation switch. No remediation actions are implemented in this milestone.')
param remediationEnabled bool = false

@description('Require an explicit approval gate for any future remediation implementation.')
param remediationApprovalRequired bool = true

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var tags = {
  'azd-env-name': environmentName
  'managed-by': 'azd'
  workload: 'cloud-pc-recommendations'
}
var resolvedStorageName = empty(storageAccountName) ? take(replace('stcpc${resourceToken}', '-', ''), 24) : storageAccountName
var resolvedFunctionAppName = empty(functionAppName) ? 'func-cpc-${resourceToken}' : functionAppName
var resolvedPlanName = empty(functionPlanName) ? 'plan-cpc-${resourceToken}' : functionPlanName
var resolvedAppInsightsName = empty(appInsightsName) ? 'appi-cpc-${resourceToken}' : appInsightsName
var resolvedWorkspaceName = empty(logAnalyticsWorkspaceName) ? 'log-cpc-${resourceToken}' : logAnalyticsWorkspaceName
var deploymentContainerName = 'deployment'
var storageSuffix = environment().suffixes.storage
var storageBlobDataOwnerRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b')
var storageQueueDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
var storageTableDataContributorRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: resolvedStorageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  name: 'default'
  parent: storage
}

resource reportContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: reportContainerName
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  name: deploymentContainerName
  parent: blobService
  properties: {
    publicAccess: 'None'
  }
}

resource storageLifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2022-09-01' = {
  name: 'default'
  parent: storage
  properties: {
    policy: {
      rules: [
        {
          enabled: true
          name: 'delete-expired-audit-reports'
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${reportContainerName}/'
              ]
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: reportRetentionDays
                }
              }
            }
          }
        }
      ]
    }
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: resolvedWorkspaceName
  location: location
  tags: tags
  properties: {
    retentionInDays: reportRetentionDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: resolvedAppInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: resolvedPlanName
  location: location
  kind: 'functionapp'
  tags: tags
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: resolvedFunctionAppName
  location: location
  kind: 'functionapp,linux'
  dependsOn: [
    deploymentContainer
    reportContainer
  ]
  tags: union(tags, {
    'azd-service-name': 'monitor'
  })
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: plan.id
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: 'https://${storage.name}.blob.${storageSuffix}/${deploymentContainerName}'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        maximumInstanceCount: maximumInstanceCount
        instanceMemoryMB: 2048
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
    }
    httpsOnly: true
    clientAffinityEnabled: false
    siteConfig: {
      minTlsVersion: '1.2'
      http20Enabled: true
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: storage.name
        }
        {
          name: 'AzureWebJobsStorage__credential'
          value: 'managedidentity'
        }
        {
          name: 'AzureWebJobsStorage__blobServiceUri'
          value: 'https://${storage.name}.blob.${storageSuffix}'
        }
        {
          name: 'AzureWebJobsStorage__queueServiceUri'
          value: 'https://${storage.name}.queue.${storageSuffix}'
        }
        {
          name: 'AzureWebJobsStorage__tableServiceUri'
          value: 'https://${storage.name}.table.${storageSuffix}'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'STORAGE_ACCOUNT_URL'
          value: 'https://${storage.name}.blob.${storageSuffix}'
        }
        {
          name: 'REPORT_CONTAINER_NAME'
          value: reportContainerName
        }
        {
          name: 'STATE_TABLE_NAME'
          value: stateTableName
        }
        {
          name: 'MONITOR_SCHEDULE'
          value: monitorSchedule
        }
        {
          name: 'GRAPH_API_VERSION'
          value: graphApiVersion
        }
        {
          name: 'CLOUD_PC_RECOMMENDATIONS_ENABLED'
          value: string(recommendationsEnabled)
        }
        {
          name: 'DRY_RUN'
          value: string(dryRun)
        }
        {
          name: 'NOTIFICATIONS_ENABLED'
          value: string(notificationsEnabled)
        }
        {
          name: 'SEND_NOTIFICATIONS_IN_DRY_RUN'
          value: string(sendNotificationsInDryRun)
        }
        {
          name: 'UNUSED_CLOUD_PC_DAYS'
          value: string(unusedCloudPcDays)
        }
        {
          name: 'STALE_DEVICE_DAYS'
          value: string(staleDeviceDays)
        }
        {
          name: 'PROVISIONING_FAILURE_GRACE_MINUTES'
          value: string(provisioningFailureGraceMinutes)
        }
        {
          name: 'UNHEALTHY_DEVICE_GRACE_MINUTES'
          value: string(unhealthyDeviceGraceMinutes)
        }
        {
          name: 'NOTIFICATION_RENOTIFY_HOURS'
          value: string(notificationRenotifyHours)
        }
        {
          name: 'CLOUD_PC_RULES_JSON'
          value: ruleConfigJson
        }
        {
          name: 'ALERT_SUPPRESSIONS'
          value: alertSuppressions
        }
        {
          name: 'INTUNE_CLOUD_PC_URL'
          value: intuneCloudPcUrl
        }
        {
          name: 'REMEDIATION_ENABLED'
          value: string(remediationEnabled)
        }
        {
          name: 'REMEDIATION_APPROVAL_REQUIRED'
          value: string(remediationApprovalRequired)
        }
        {
          name: 'TEAMS_WEBHOOK_URL'
          value: teamsWebhookUrl
        }
      ]
    }
  }
}

resource ftpPublishingPolicy 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: functionApp
  name: 'ftp'
  properties: {
    allow: false
  }
}

resource scmPublishingPolicy 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2023-12-01' = {
  parent: functionApp
  name: 'scm'
  properties: {
    allow: false
  }
}

resource blobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, 'storage-blob-data-owner')
  scope: storage
  properties: {
    roleDefinitionId: storageBlobDataOwnerRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource queueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, 'storage-queue-data-contributor')
  scope: storage
  properties: {
    roleDefinitionId: storageQueueDataContributorRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource tableRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, functionApp.id, 'storage-table-data-contributor')
  scope: storage
  properties: {
    roleDefinitionId: storageTableDataContributorRoleId
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup().name
output AZURE_SUBSCRIPTION_ID string = subscription().subscriptionId
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_FUNCTION_APP_NAME string = functionApp.name
output MONITOR_FUNCTION_APP_NAME string = functionApp.name
output FUNCTION_PRINCIPAL_ID string = functionApp.identity.principalId
output STORAGE_ACCOUNT_NAME string = storage.name
output STORAGE_ACCOUNT_URL string = 'https://${storage.name}.blob.${storageSuffix}'
output REPORT_CONTAINER_NAME string = reportContainerName
output DEPLOYMENT_CONTAINER_NAME string = deploymentContainerName
output STATE_TABLE_NAME string = stateTableName
output GRAPH_API_VERSION string = graphApiVersion
output CLOUD_PC_RECOMMENDATIONS_ENABLED string = string(recommendationsEnabled)
output DRY_RUN string = string(dryRun)
output NOTIFICATIONS_ENABLED string = string(notificationsEnabled)
output GRAPH_ROLE_ASSIGNMENTS_ENABLED string = string(graphRoleAssignmentsEnabled)
output REMEDIATION_ENABLED string = string(remediationEnabled)
