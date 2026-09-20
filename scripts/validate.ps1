$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$functionRoot = Join-Path $repositoryRoot 'src\cloud-pc-monitor'

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string] $Description)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw 'Azure CLI is required for Bicep validation.'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python is required for source and fixture validation.'
}

Write-Host 'Validating Bicep compilation...'
az bicep build --file (Join-Path $repositoryRoot 'infra\main.bicep') --stdout | Out-Null
Assert-NativeSuccess -Description 'Bicep compilation'

Write-Host 'Validating PowerShell syntax...'
$powershellFiles = @(
    Get-ChildItem -Path (Join-Path $repositoryRoot 'scripts') -Filter '*.ps1' -File
)
foreach ($file in $powershellFiles) {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $file.FullName,
        [ref]$tokens,
        [ref]$errors
    ) | Out-Null
    if ($errors.Count -gt 0) {
        throw "PowerShell syntax errors were found in '$($file.FullName)'."
    }
}

Write-Host 'Validating Python compilation and deterministic tests...'
Push-Location $functionRoot
try {
    python -m compileall -q .
    Assert-NativeSuccess -Description 'Python compilation'
}
finally {
    Pop-Location
}

Push-Location $repositoryRoot
try {
    python -m unittest discover -s tests -p 'test_*.py'
    Assert-NativeSuccess -Description 'Python unit tests'
}
finally {
    Pop-Location
}

Write-Host 'Repository validation completed. No Azure or Microsoft Graph mutation was performed.'
