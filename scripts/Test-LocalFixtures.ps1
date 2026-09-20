$ErrorActionPreference = 'Stop'
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$functionRoot = Join-Path $repositoryRoot 'src\cloud-pc-monitor'

Push-Location $functionRoot
try {
    $env:PYTHONPATH = $functionRoot
    python -m cloudpc_monitor.cli --fixtures (Join-Path $repositoryRoot 'tests\fixtures')
    if ($LASTEXITCODE -ne 0) {
        throw "Fixture validation failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
