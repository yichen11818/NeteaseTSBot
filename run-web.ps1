$ErrorActionPreference = 'Stop'

$repoRoot = $PSScriptRoot
. (Join-Path $repoRoot 'scripts/Import-TsbotEnv.ps1')

$vite = Join-Path $repoRoot 'web/node_modules/.bin/vite.cmd'
if (-not (Test-Path $vite)) {
    throw 'Missing web/node_modules/.bin/vite.cmd. Run npm.cmd --prefix web install first.'
}

$hostAddr = if ($env:VITE_DEV_HOST) {
    $env:VITE_DEV_HOST.Trim()
} else {
    '127.0.0.1'
}

$port = if ($env:VITE_DEV_PORT) {
    $env:VITE_DEV_PORT.Trim().TrimStart(':')
} else {
    '5173'
}

Push-Location (Join-Path $repoRoot 'web')
try {
    & $vite --host $hostAddr --port $port
}
finally {
    Pop-Location
}
