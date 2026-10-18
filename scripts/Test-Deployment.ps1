#Requires -Version 7.6
[CmdletBinding()]
param(
    [switch] $Plan,
    [switch] $TestDelivery,
    [string] $OutputPath = 'reports/deployment-validation.json',
    [switch] $PassThru,
    [string] $TenantId,
    [string] $SubscriptionId,
    [string] $ResourceGroup,
    [string] $FunctionAppName,
    [string] $StorageAccountName,
    [string] $TableName
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$moduleRoot = Join-Path $PSScriptRoot 'vendor/Azd.DeploymentValidation'
Import-Module (Join-Path $moduleRoot 'Azd.DeploymentValidation.psd1') -Force

function New-SafeFailure {
    param([Parameter(Mandatory)][string] $Code, [Parameter(Mandatory)][string] $Summary, [string] $Remediation)
    New-AzdCheckFailure -Code $Code -Summary $Summary -Remediation ($Remediation ?? 'Review the target and rerun the read-only validation.')
}

function Invoke-AzureCliJson {
    param([Parameter(Mandatory)][string[]] $Arguments)
    $start = [System.Diagnostics.ProcessStartInfo]::new()
    $azPath = (Get-Command az -ErrorAction Stop).Source
    $isBatch = [System.IO.Path]::GetExtension($azPath) -ieq '.cmd'
    if ($isBatch) {
        # The Windows MSI launcher delegates directly to this interpreter.
        $cliPython = Join-Path (Split-Path $azPath) '../python.exe'
        if (Test-Path -LiteralPath $cliPython -PathType Leaf) {
            $start.FileName = [IO.Path]::GetFullPath($cliPython)
            foreach ($argument in @('-IBm', 'azure.cli') + $Arguments) { [void]$start.ArgumentList.Add($argument) }
            $start.Environment['AZ_INSTALLER'] = 'MSI'
        }
        else {
            # Other trusted local launchers (including test fixtures). No shell
            # expansion characters or quotes may cross this boundary.
            foreach ($argument in @($azPath) + $Arguments) {
                if ($argument -match '["%&|<>^!\r\n]') { throw 'unsupported-launcher-argument' }
            }
            $start.FileName = $env:ComSpec
            $start.Arguments = '/d /s /c ""' + $azPath + '" ' + (($Arguments | ForEach-Object { '"' + $_ + '"' }) -join ' ') + '"'
        }
    }
    else { $start.FileName = $azPath; foreach ($argument in $Arguments) { [void]$start.ArgumentList.Add($argument) } }
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($name in 'AZURE_STORAGE_KEY', 'AZURE_STORAGE_CONNECTION_STRING', 'AZURE_STORAGE_SAS_TOKEN', 'AZURE_STORAGE_ACCOUNT', 'AZURE_STORAGE_SERVICE_ENDPOINT', 'AZURE_STORAGE_BLOB_ENDPOINT', 'AZURE_STORAGE_QUEUE_ENDPOINT', 'AZURE_STORAGE_TABLE_ENDPOINT', 'AZURE_STORAGE_AUTH_MODE',
        'AZURE_CLIENT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_TENANT_ID', 'AZURE_CLIENT_CERTIFICATE_PATH', 'AZURE_CLIENT_CERTIFICATE_PASSWORD', 'AZURE_CLIENT_SEND_CERTIFICATE_CHAIN', 'AZURE_FEDERATED_TOKEN_FILE', 'AZURE_AUTHORITY_HOST', 'AZURE_USERNAME', 'AZURE_PASSWORD') {
        [void]$start.Environment.Remove($name)
    }
    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'start-failed' }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(30000)) {
            $process.Kill($true)
            $process.WaitForExit()
            throw 'timeout'
        }
        $stdout = $stdoutTask.GetAwaiter().GetResult()
        [void] $stderrTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw 'command-failed' }
        if ([string]::IsNullOrWhiteSpace($stdout)) { throw 'empty-json' }
        $stdout | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        throw [System.InvalidOperationException]::new('azure-cli-read-failed')
    }
    finally { $process.Dispose() }
}

function Get-TargetContext {
    param([Parameter(Mandatory)][object] $Account)
    $enabled = [string]$Account.state -eq 'Enabled'
    $tenantMatches = [string]::Equals([string]$Account.tenantId, $TenantId, [System.StringComparison]::OrdinalIgnoreCase)
    $subscriptionMatches = [string]::Equals([string]$Account.id, $SubscriptionId, [System.StringComparison]::OrdinalIgnoreCase)
    $cloudMatches = [string]$Account.environmentName -eq 'AzureCloud'
    if (-not ($enabled -and $tenantMatches -and $subscriptionMatches -and $cloudMatches)) {
        return New-SafeFailure -Code 'context.identityMismatch' -Summary 'Cached Azure CLI context does not exactly match the requested enabled tenant and subscription.' -Remediation 'Select the requested tenant and subscription in the normal browser or cached Azure CLI session, then rerun.'
    }
    New-AzdCheckOutcome -Status pass -Summary 'Cached Azure CLI context exactly matches the requested enabled tenant and subscription.' `
        -Expected ([ordered]@{ tenantId = $TenantId; subscriptionId = $SubscriptionId; state = 'Enabled'; azureCloud = 'AzureCloud' }) `
        -Actual ([ordered]@{ tenantId = [string]$Account.tenantId; subscriptionId = [string]$Account.id; state = [string]$Account.state; azureCloud = [string]$Account.environmentName })
}

function Get-ResourceId {
    param([Parameter(Mandatory)][string] $Provider, [Parameter(Mandatory)][string] $Name)
    '/subscriptions/{0}/resourceGroups/{1}/providers/{2}/{3}' -f $SubscriptionId, $ResourceGroup, $Provider, $Name
}

function Invoke-ResourceRead {
    param([Parameter(Mandatory)][string] $ResourceId)
    Invoke-AzureCliJson @('resource', 'show', '--ids', $ResourceId, '--include-response-body', 'true', '--subscription', $SubscriptionId, '--output', 'json', '--only-show-errors')
}

if ($TestDelivery) {
    $startTime = [datetimeoffset]::UtcNow
    $check = Invoke-AzdValidationCheck -Id 'delivery.unsupported' -Phase delivery -Title 'Delivery smoke test' `
        -Summary 'Delivery testing is unsupported for this non-remediating Cloud PC monitor wrapper.' -SideEffect none `
        -Action { New-SafeFailure -Code 'delivery.unsupported' -Summary 'Delivery testing is explicitly unsupported and no CLI or authentication call was made.' -Remediation 'Use a separately authorized application delivery pilot with recipient-visible evidence.' }
    $report = New-AzdValidationReport -TemplateName 'azd-cloud-pc-recommendations' -TemplateVersion 'cpc-wrapper-1.0' `
        -Mode delivery -StartedAt $startTime -Checks @($check) -Requirements @{ tools = @('Azure CLI'); modules = @('PowerShell 7.6+'); permissions = @() } `
        -NextSteps @('Delivery requires a separately authorized application pilot and recipient-visible evidence.')
    if ($OutputPath) { Write-AzdValidationReport -Report $report -OutputPath $OutputPath -RepositoryRoot $repositoryRoot }
    if ($PassThru) { $report }
    exit 1
}

$verifyParameters = @{
    TenantId = $TenantId; SubscriptionId = $SubscriptionId; ResourceGroup = $ResourceGroup
    FunctionAppName = $FunctionAppName; StorageAccountName = $StorageAccountName
}
if (-not $Plan) {
    foreach ($name in $verifyParameters.Keys) {
        if ([string]::IsNullOrWhiteSpace([string]$verifyParameters[$name])) { throw "-$name is required for read-only verification." }
    }
    if ($TenantId -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' -or $SubscriptionId -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') { throw 'TenantId and SubscriptionId must be UUIDs.' }
    if ($ResourceGroup -notmatch '^[A-Za-z0-9._()-]{1,90}$') { throw 'ResourceGroup contains unsupported characters.' }
    if ($FunctionAppName -notmatch '^[A-Za-z0-9-]{2,60}$') { throw 'FunctionAppName contains unsupported characters.' }
    if ($StorageAccountName -notmatch '^[a-z0-9]{3,24}$') { throw 'StorageAccountName must be 3-24 lowercase letters or digits.' }
    if ($TableName -and $TableName -notmatch '^[A-Za-z][A-Za-z0-9]{2,62}$') { throw 'TableName contains unsupported characters.' }
}

$startedAt = [datetimeoffset]::UtcNow
$functionId = if ($Plan) { '/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Web/sites/{functionAppName}' } else { Get-ResourceId -Provider 'Microsoft.Web/sites' -Name $FunctionAppName }
$storageId = if ($Plan) { '/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Storage/storageAccounts/{storageAccountName}' } else { Get-ResourceId -Provider 'Microsoft.Storage/storageAccounts' -Name $StorageAccountName }
$ctx = [ordered]@{ functionId = $functionId; storageId = $storageId; principalId = $null }

$checks = [System.Collections.Generic.List[object]]::new()
$checks.Add((New-AzdValidationCheckDefinition -Id 'context.azure-session' -Phase context -Title 'Azure CLI context' -Summary 'Verify the cached Azure CLI context before any target cloud request.' -Action ([scriptblock] {
    $account = Invoke-AzureCliJson @('account', 'show', '--output', 'json', '--only-show-errors')
    $result = Get-TargetContext -Account $account
    $result
}) -SideEffect readOnly))
$checks.Add((New-AzdValidationCheckDefinition -Id 'infrastructure.function' -Phase infrastructure -Title 'Function App shape' -Summary 'Verify the exact Function App resource, Linux Python runtime, and system identity.' -DependsOn @('context.azure-session') -Action ([scriptblock] {
    $resource = Invoke-ResourceRead -ResourceId $ctx.functionId
    $ctx.principalId = [string]$resource.identity.principalId
    if ($ctx.principalId -notmatch '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$') { return New-SafeFailure -Code 'resource.identityMissing' -Summary 'The Function system identity has no valid principal ID.' }
    $ctx.function = $resource
    $kind = [string]$resource.kind
    $runtime = $resource.properties.functionAppConfig.runtime
    $ok = [string]::Equals([string]$resource.id, $ctx.functionId, [System.StringComparison]::OrdinalIgnoreCase) -and $kind -ceq 'functionapp,linux' -and [string]$runtime.name -eq 'python' -and [string]$runtime.version -eq '3.11' -and [string]$resource.identity.type -eq 'SystemAssigned'
    if (-not $ok) { return New-SafeFailure -Code 'resource.functionShape' -Summary 'Function App resource shape does not match the identity-only Python 3.11 contract.' -Remediation 'Inspect the exact Function App runtime, kind, and identity configuration.' }
    New-AzdCheckOutcome -Status pass -Summary 'Exact Function App uses Linux Python 3.11 with a system-assigned identity.' -Evidence @{ resourceId = $ctx.functionId; runtime = 'python3.11'; identity = 'SystemAssigned' }
}) -SideEffect readOnly))
$checks.Add((New-AzdValidationCheckDefinition -Id 'infrastructure.storage' -Phase infrastructure -Title 'Storage security' -Summary 'Verify the exact storage account disables shared keys and public blob access.' -DependsOn @('context.azure-session') -Action ([scriptblock] {
    $resource = Invoke-ResourceRead -ResourceId $ctx.storageId
    $p = $resource.properties
    if (-not ([string]::Equals([string]$resource.id, $ctx.storageId, [System.StringComparison]::OrdinalIgnoreCase) -and $p.allowSharedKeyAccess -is [bool] -and -not $p.allowSharedKeyAccess -and $p.allowBlobPublicAccess -is [bool] -and -not $p.allowBlobPublicAccess -and $p.supportsHttpsTrafficOnly -is [bool] -and $p.supportsHttpsTrafficOnly -and [string]$p.minimumTlsVersion -eq 'TLS1_2')) {
        return New-SafeFailure -Code 'resource.storageSecurity' -Summary 'Storage account security settings do not match the identity-only HTTPS contract.' -Remediation 'Set shared-key access and public blob access to false and require TLS 1.2 or newer.'
    }
    New-AzdCheckOutcome -Status pass -Summary 'Exact storage account disables shared keys and public blob access and requires HTTPS TLS 1.2.' -Evidence @{ resourceId = $ctx.storageId }
}) -SideEffect readOnly))
$checks.Add((New-AzdValidationCheckDefinition -Id 'configuration.deployment-storage' -Phase configuration -Title 'Deployment storage binding' -Summary 'Verify deployment storage uses system-assigned authentication and the selected storage account.' -DependsOn @('infrastructure.function', 'infrastructure.storage') -Action ([scriptblock] {
    $resource = $ctx.function
    $deployment = $resource.properties.functionAppConfig.deployment.storage
    $expectedUrl = 'https://{0}.blob.core.windows.net/deployment' -f $StorageAccountName
    if ([string]$deployment.type -ne 'blobContainer' -or [string]$deployment.authentication.type -ne 'SystemAssignedIdentity' -or [string]$deployment.value -cne $expectedUrl) {
        return New-SafeFailure -Code 'configuration.deploymentStorage' -Summary 'Function deployment storage is not bound to the selected account with system-assigned authentication.' -Remediation 'Configure the deployment blob container with SystemAssignedIdentity authentication.'
    }
    New-AzdCheckOutcome -Status pass -Summary 'Deployment storage points to the selected account and uses system-assigned identity authentication.' -Evidence @{ storageAccount = $StorageAccountName; authentication = 'SystemAssignedIdentity' }
}) -SideEffect readOnly))
$checks.Add((New-AzdValidationCheckDefinition -Id 'configuration.host-storage' -Phase configuration -Title 'Host storage identity settings' -Summary 'Verify host storage settings use managed identity and selected storage endpoints.' -DependsOn @('infrastructure.function', 'infrastructure.storage') -Action ([scriptblock] {
    $settings = Invoke-AzureCliJson @('functionapp', 'config', 'appsettings', 'list', '--name', $FunctionAppName, '--resource-group', $ResourceGroup, '--subscription', $SubscriptionId, '--output', 'json', '--only-show-errors')
    $map = @{}
    foreach ($setting in @($settings)) {
        $name = [string]$setting.name
        if ($map.ContainsKey($name)) { return New-SafeFailure -Code 'configuration.duplicateSetting' -Summary 'Function app settings contain duplicate names.' }
        $map[$name] = [string]$setting.value
    }
    $ok = $map['AzureWebJobsStorage__accountName'] -eq $StorageAccountName -and $map['AzureWebJobsStorage__credential'] -eq 'managedidentity'
    foreach ($service in 'blob', 'queue', 'table') {
        $ok = $ok -and $map["AzureWebJobsStorage__${service}ServiceUri"] -ceq "https://$StorageAccountName.$service.core.windows.net"
    }
    foreach ($override in 'AzureWebJobsStorage', 'AzureWebJobsStorage__clientId', 'AzureWebJobsStorage__managedIdentityResourceId') {
        $ok = $ok -and -not $map.ContainsKey($override)
    }
    if (-not $ok) { return New-SafeFailure -Code 'configuration.hostStorage' -Summary 'Function host storage settings are missing the selected account or identity-only endpoints.' -Remediation 'Configure AzureWebJobsStorage identity-based account and blob, queue, and table service URIs.' }
    New-AzdCheckOutcome -Status pass -Summary 'Function host storage uses managed identity and endpoints for the selected account.' -Evidence @{ account = $StorageAccountName; credential = 'managedidentity' }
}) -SideEffect readOnly))
$checks.Add((New-AzdValidationCheckDefinition -Id 'identity.storage-roles' -Phase identity -Title 'Storage role assignments' -Summary 'Verify direct unconditional storage data roles for the Function identity at exact storage scope.' -DependsOn @('infrastructure.function', 'infrastructure.storage') -Action ([scriptblock] {
    $assignments = Invoke-AzureCliJson @('role', 'assignment', 'list', '--scope', $ctx.storageId, '--assignee-object-id', $ctx.principalId, '--fill-principal-name', 'false', '--fill-role-definition-name', 'false', '--subscription', $SubscriptionId, '--output', 'json', '--only-show-errors')
    $required = @{ 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' = 'Storage Blob Data Owner'; '974c5e8b-45b9-4653-ba55-5f855dd0fb88' = 'Storage Queue Data Contributor'; '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3' = 'Storage Table Data Contributor' }
    $missing = [System.Collections.Generic.List[string]]::new()
    foreach ($roleId in $required.Keys) {
        $found = @($assignments | Where-Object {
            $conditionProperty = $_.PSObject.Properties['condition']
            $conditionIsUnconditional = $null -eq $conditionProperty -or $null -eq $conditionProperty.Value -or
                ($conditionProperty.Value -is [string] -and [string]::IsNullOrWhiteSpace($conditionProperty.Value))
            [string]$_.roleDefinitionId -match ('/roleDefinitions/{0}$' -f [regex]::Escape($roleId)) -and [string]$_.scope -eq $ctx.storageId -and $conditionIsUnconditional -and [string]$_.principalId -eq $ctx.principalId
        })
        if ($found.Count -eq 0) { $missing.Add($required[$roleId]) }
    }
    if ($missing.Count -gt 0) { return New-SafeFailure -Code 'identity.storageRoles' -Summary ('Required direct storage roles are missing or conditional: ' + ($missing -join ', ') + '.') -Remediation 'Review the exact storage-scope role assignments for the Function system-assigned identity.' }
    New-AzdCheckOutcome -Status pass -Summary 'Function identity has the three required direct unconditional data roles at exact storage scope.' -Evidence @{ scope = $ctx.storageId; roleCount = 3 }
}) -SideEffect readOnly))
$auditSkipReason = if ($TableName) { $null } else { 'No explicit TableName was supplied; runtime audit state is not inferred or queried.' }
$auditAction = if ($TableName) {
    [scriptblock] {
        $rowKey = 'latest' # TableStateStore.record_run writes this exact key.
        $row = Invoke-AzureCliJson @('storage', 'entity', 'show', '--account-name', $StorageAccountName, '--table-endpoint', "https://$StorageAccountName.table.core.windows.net", '--table-name', $TableName, '--partition-key', 'run', '--row-key', $rowKey, '--auth-mode', 'login', '--select', 'PartitionKey', 'RowKey', '--subscription', $SubscriptionId, '--output', 'json', '--only-show-errors')
        if ([string]$row.PartitionKey -ne 'run' -or [string]$row.RowKey -ne $rowKey) {
            return New-SafeFailure -Code 'runtime.auditRowMismatch' -Summary 'The bounded audit read returned an unexpected row identity.' -Remediation 'Verify the explicitly selected state table and the run/latest audit row.'
        }
        New-AzdCheckOutcome -Status pass -Summary 'The explicitly selected table exposes the bounded run/latest audit row.' -Evidence @{ table = $TableName; partitionKey = 'run'; rowKey = 'latest' }
    }
} else { { New-AzdCheckOutcome -Status skipped -Summary 'Audit state was not requested.' } }
$checks.Add((New-AzdValidationCheckDefinition -Id 'audit.table-read' -Phase runtime -Title 'Existing audit state' -Summary 'Read one explicitly selected run/latest audit row without retrieving payload or PII.' -DependsOn @('infrastructure.storage') -Action $auditAction -SideEffect readOnly -SkipReason $auditSkipReason))

$mode = if ($Plan) { 'plan' } else { 'verify' }
$results = Invoke-AzdValidationSet -Definitions @($checks) -Plan:$Plan
$report = New-AzdValidationReport -TemplateName 'azd-cloud-pc-recommendations' -TemplateVersion 'cpc-wrapper-1.0' -Mode $mode -StartedAt $startedAt `
    -Checks @($results) -Environment @{ tenantId = if ($Plan) { 'planned' } else { $TenantId }; subscriptionId = if ($Plan) { 'planned' } else { $SubscriptionId }; resourceGroup = if ($Plan) { 'planned' } else { $ResourceGroup }; azureCloud = 'AzureCloud' } `
    -Requirements @{ tools = @('Azure CLI'); modules = @('PowerShell 7.6+'); permissions = @('Resource and role-assignment read access', 'Microsoft.Web/sites/config/list/action', 'Optional selected-table data read access') } `
    -NextSteps @('This wrapper proves selected control-plane state only; it does not prove Graph collection, Python report generation, runtime telemetry, or recipient-visible delivery.')
if ($OutputPath) { Write-AzdValidationReport -Report $report -OutputPath $OutputPath -RepositoryRoot $repositoryRoot }
Write-AzdValidationSummary -Report $report
if ($PassThru) { $report }
if ($report.outcome -eq 'failed') { exit 1 }
