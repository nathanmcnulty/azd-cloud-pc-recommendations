$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

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

function Get-Boolean {
    param([Parameter(Mandatory = $true)][string] $Name)

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $false
    }

    switch ($value.Trim().ToLowerInvariant()) {
        '1' { return $true }
        'true' { return $true }
        'yes' { return $true }
        '0' { return $false }
        'false' { return $false }
        'no' { return $false }
        default { throw "$Name must be a boolean value." }
    }
}

function Get-RequiredEnvironmentValue {
    param([Parameter(Mandatory = $true)][string] $Name)

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Required azd environment value '$Name' is missing."
    }
    return $value
}

function Get-GraphToken {
    $tenantId = Get-RequiredEnvironmentValue -Name 'AZURE_TENANT_ID'
    $token = az account get-access-token --tenant $tenantId --resource-type ms-graph --query accessToken --output tsv --only-show-errors
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
        throw "Unable to acquire a Microsoft Graph token for tenant '$tenantId'. Use a normal cached Azure CLI or browser sign-in and verify the selected tenant."
    }
    return $token.Trim()
}

function Invoke-GraphJson {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('GET', 'POST')][string] $Method,
        [Parameter(Mandatory = $true)][string] $Uri,
        [object] $Body
    )

    $token = Get-GraphToken
    $request = @{
        Method = $Method
        Uri = $Uri
        Headers = @{
            Authorization = "Bearer $token"
            Accept = 'application/json'
        }
        ErrorAction = 'Stop'
    }
    if ($PSBoundParameters.ContainsKey('Body')) {
        $request.Body = $Body | ConvertTo-Json -Depth 10 -Compress
        $request.ContentType = 'application/json'
    }
    return Invoke-RestMethod @request
}

function Ensure-GraphApplicationRole {
    param(
        [Parameter(Mandatory = $true)][string] $PrincipalId,
        [Parameter(Mandatory = $true)][string] $RoleValue
    )

    $graphAppId = '00000003-0000-0000-c000-000000000000'
    $graphResponse = Invoke-GraphJson -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals?`$filter=appId eq '$graphAppId'&`$select=id,appRoles"
    $graphServicePrincipal = @($graphResponse.value) | Select-Object -First 1
    if ($null -eq $graphServicePrincipal) {
        throw 'The Microsoft Graph service principal was not found in the selected tenant.'
    }

    $role = @($graphServicePrincipal.appRoles | Where-Object {
        $_.value -eq $RoleValue -and $_.allowedMemberTypes -contains 'Application'
    }) | Select-Object -First 1
    if ($null -eq $role) {
        throw "Microsoft Graph application role '$RoleValue' was not found."
    }

    $assignments = Invoke-GraphJson -Method GET -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$PrincipalId/appRoleAssignments?`$select=resourceId,appRoleId"
    $existing = @($assignments.value | Where-Object {
        $_.resourceId -eq $graphServicePrincipal.id -and $_.appRoleId -eq $role.id
    }) | Select-Object -First 1
    if ($null -ne $existing) {
        Write-Host "Managed identity already has $RoleValue."
        return
    }

    Invoke-GraphJson `
        -Method POST `
        -Uri "https://graph.microsoft.com/v1.0/servicePrincipals/$PrincipalId/appRoleAssignments" `
        -Body @{
            principalId = $PrincipalId
            resourceId = $graphServicePrincipal.id
            appRoleId = $role.id
        } | Out-Null

    Write-Host "Assigned $RoleValue to the monitor managed identity."
}

Import-AzdEnvironment

if (-not (Get-Boolean -Name 'GRAPH_ROLE_ASSIGNMENTS_ENABLED')) {
    Write-Warning 'GRAPH_ROLE_ASSIGNMENTS_ENABLED=false; no Microsoft Graph application roles were changed.'
    return
}

$principalId = Get-RequiredEnvironmentValue -Name 'FUNCTION_PRINCIPAL_ID'
$roles = [System.Collections.Generic.List[string]]::new()
if (Get-Boolean -Name 'CLOUD_PC_RECOMMENDATIONS_ENABLED') {
    Write-Warning 'Recommendation report collection requires the broader CloudPC.ReadWrite.All application role according to the current Microsoft Graph contract.'
    $roles.Add('CloudPC.ReadWrite.All')
}
else {
    $roles.Add('CloudPC.Read.All')
}
$roles.Add('DeviceManagementManagedDevices.Read.All')

foreach ($role in $roles) {
    Ensure-GraphApplicationRole -PrincipalId $principalId -RoleValue $role
}

Write-Host 'Post-provision bootstrap complete.'
Write-Host "  Function App: $([Environment]::GetEnvironmentVariable('MONITOR_FUNCTION_APP_NAME'))"
Write-Host "  Resource Group: $([Environment]::GetEnvironmentVariable('AZURE_RESOURCE_GROUP'))"
Write-Host "  Graph roles: $($roles -join ', ')"
Write-Host "  Dry run: $([Environment]::GetEnvironmentVariable('DRY_RUN'))"
