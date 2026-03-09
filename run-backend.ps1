$ErrorActionPreference = 'Stop'

$repoRoot = $PSScriptRoot
. (Join-Path $repoRoot 'scripts/Import-TsbotEnv.ps1')

$python = Join-Path $repoRoot 'backend/.venv/Scripts/python.exe'
if (-not (Test-Path $python)) {
    throw 'Missing backend/.venv/Scripts/python.exe. Create the virtual environment first and install backend dependencies.'
}

$hostAddr = if ($env:TSBOT_HOST) {
    $env:TSBOT_HOST.Trim() -replace '^https?://', '' -replace '/.*$', '' -replace ':.+$', ''
} else {
    '127.0.0.1'
}

$port = if ($env:TSBOT_PORT) {
    $env:TSBOT_PORT.Trim().TrimStart(':')
} else {
    '8009'
}

Push-Location $repoRoot
try {
    & $python -m uvicorn backend.main:app --host $hostAddr --port $port
}
finally {
    Pop-Location
}
