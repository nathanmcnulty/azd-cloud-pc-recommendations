$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-Command {
    param([Parameter(Mandatory = $true)][string] $Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found. Install it before provisioning."
    }
}

function Import-AzdEnvironment {
    $values = azd env get-values 2>$null
    foreach ($line in $values) {
        if ([string]::IsNullOrWhiteSpace($line) -or -not $line.Contains('=')) {
            continue
        }

        $parts = $line.Split('=', 2)
        $name = $parts[0]
        $value = $parts[1].Trim('"')
        Set-Item -Path "env:$name" -Value $value
    }
}

function Set-AzdValue {
    param(
        [Parameter(Mandatory = $true)][string] $Name,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string] $Value
    )

    azd env set $Name $Value | Out-Null
    Set-Item -Path "env:$Name" -Value $Value
}

Assert-Command -Name 'azd'
Assert-Command -Name 'az'
Import-AzdEnvironment

$defaults = [ordered]@{
    'DRY_RUN' = 'true'
    'NOTIFICATIONS_ENABLED' = 'true'
    'SEND_NOTIFICATIONS_IN_DRY_RUN' = 'false'
    'CLOUD_PC_RECOMMENDATIONS_ENABLED' = 'false'
    'GRAPH_API_VERSION' = 'beta'
    'MONITOR_SCHEDULE' = '0 0 * * * *'
    'UNUSED_CLOUD_PC_DAYS' = '30'
    'STALE_DEVICE_DAYS' = '14'
    'PROVISIONING_FAILURE_GRACE_MINUTES' = '60'
    'UNHEALTHY_DEVICE_GRACE_MINUTES' = '60'
    'NOTIFICATION_RENOTIFY_HOURS' = '24'
    'REPORT_RETENTION_DAYS' = '30'
    'REPORT_CONTAINER_NAME' = 'reports'
    'STATE_TABLE_NAME' = 'CloudPcState'
    'CLOUD_PC_RULES_JSON' = ''
    'ALERT_SUPPRESSIONS' = ''
    'TEAMS_WEBHOOK_URL' = ''
    'INTUNE_CLOUD_PC_URL' = 'https://intune.microsoft.com/'
    'GRAPH_ROLE_ASSIGNMENTS_ENABLED' = 'true'
    'REMEDIATION_ENABLED' = 'false'
    'REMEDIATION_APPROVAL_REQUIRED' = 'true'
    'FUNCTION_APP_NAME' = ''
    'STORAGE_ACCOUNT_NAME' = ''
    'FUNCTION_PLAN_NAME' = ''
    'APP_INSIGHTS_NAME' = ''
    'LOG_ANALYTICS_WORKSPACE_NAME' = ''
}

foreach ($entry in $defaults.GetEnumerator()) {
    $current = [Environment]::GetEnvironmentVariable($entry.Key)
    if ($null -eq $current) {
        Set-AzdValue -Name $entry.Key -Value ([string]$entry.Value)
    }
}

Write-Host 'Prepared Cloud PC recommendations defaults.'
Write-Host "  DRY_RUN=$([Environment]::GetEnvironmentVariable('DRY_RUN'))"
Write-Host "  CLOUD_PC_RECOMMENDATIONS_ENABLED=$([Environment]::GetEnvironmentVariable('CLOUD_PC_RECOMMENDATIONS_ENABLED'))"
Write-Host "  GRAPH_ROLE_ASSIGNMENTS_ENABLED=$([Environment]::GetEnvironmentVariable('GRAPH_ROLE_ASSIGNMENTS_ENABLED'))"
if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable('TEAMS_WEBHOOK_URL'))) {
    Write-Warning 'TEAMS_WEBHOOK_URL is empty. Collection and audit exports will work, but outbound Teams delivery will remain skipped.'
}
