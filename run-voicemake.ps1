$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$repoRoot = $PSScriptRoot
. (Join-Path $repoRoot 'scripts/Import-TsbotEnv.ps1')

$ToolPathHints = @{
    Cargo = @(
        $env:TSBOT_CARGO,
        'cargo'
    )
    CMake = @(
        $env:TSBOT_CMAKE,
        $env:CMAKE,
        'C:\Cmake\bin\cmake.exe'
    )
    MinGWBin = @(
        $env:TSBOT_MINGW_BIN,
        'C:\mingw64\bin'
    )
    FFmpeg = @(
        $env:TSBOT_FFMPEG,
        'ffmpeg',
        $(if ($env:ProgramFiles) { Join-Path $env:ProgramFiles 'ffmpeg\bin\ffmpeg.exe' }),
        $(if ($env:LocalAppData) { Join-Path $env:LocalAppData 'Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-*\bin\ffmpeg.exe' }),
        $(if ($env:ChocolateyInstall) { Join-Path $env:ChocolateyInstall 'bin\ffmpeg.exe' })
    )
}

function Resolve-RepoRelativePath {
    param(
        [string]$Value,
        [string]$Fallback = ''
    )

    $candidate = if ($Value -and $Value.Trim()) { $Value.Trim() } else { $Fallback }
    if (-not $candidate) {
        return ''
    }

    if ([System.IO.Path]::IsPathRooted($candidate)) {
        return $candidate
    }

    $trimmed = $candidate -replace '^[.][\\/]+', ''
    return (Join-Path $repoRoot $trimmed)
}

function Resolve-CommandPath {
    param(
        [string]$Value
    )

    if (-not $Value -or -not $Value.Trim()) {
        return $null
    }

    $candidate = $Value.Trim()
    if ([System.IO.Path]::IsPathRooted($candidate) -or $candidate.Contains('\') -or $candidate.Contains('/')) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
        return $null
    }

    $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    return $null
}

function Resolve-GlobPath {
    param(
        [string]$Value
    )

    if (-not $Value -or -not $Value.Trim()) {
        return $null
    }

    $matches = @(Get-ChildItem -Path $Value -File -ErrorAction SilentlyContinue)
    if ($matches.Count -gt 0) {
        return $matches[0].FullName
    }

    return $null
}

function Find-ToolPath {
    param(
        [string[]]$Candidates
    )

    foreach ($candidate in $Candidates) {
        $resolved = Resolve-CommandPath $candidate
        if ($resolved) {
            return $resolved
        }

        $resolved = Resolve-GlobPath $candidate
        if ($resolved) {
            return $resolved
        }
    }

    return $null
}

function Expand-BinToolCandidates {
    param(
        [string[]]$BinHints,
        [string]$FileName
    )

    $candidates = @()
    foreach ($binHint in $BinHints) {
        if (-not $binHint -or -not $binHint.Trim()) {
            continue
        }

        $trimmed = $binHint.Trim()
        if ([System.IO.Path]::GetExtension($trimmed)) {
            $candidates += $trimmed
        } else {
            $candidates += (Join-Path $trimmed $FileName)
        }
    }

    return $candidates
}

$cargo = Find-ToolPath -Candidates $ToolPathHints.Cargo
if (-not $cargo) {
    throw 'Missing cargo.exe. Set TSBOT_CARGO, install Rust, or add cargo.exe to PATH before starting voice-service.'
}

$gccCandidates = @(
    $env:TSBOT_GCC,
    $env:CC,
    'gcc'
) + (Expand-BinToolCandidates -BinHints $ToolPathHints.MinGWBin -FileName 'gcc.exe')
$gcc = Find-ToolPath -Candidates $gccCandidates
if (-not $gcc) {
    throw 'Missing gcc.exe. Set TSBOT_GCC or TSBOT_MINGW_BIN, install MinGW-w64, or add gcc.exe to PATH before starting voice-service.'
}

$gxxCandidates = @(
    $env:TSBOT_GXX,
    $env:CXX,
    'g++'
) + (Expand-BinToolCandidates -BinHints $ToolPathHints.MinGWBin -FileName 'g++.exe')
$gxx = Find-ToolPath -Candidates $gxxCandidates
if (-not $gxx) {
    throw 'Missing g++.exe. Set TSBOT_GXX or TSBOT_MINGW_BIN, install MinGW-w64, or add g++.exe to PATH before starting voice-service.'
}

$makeCandidates = @(
    $env:TSBOT_MAKE,
    $env:CMAKE_MAKE_PROGRAM,
    'mingw32-make'
) + (Expand-BinToolCandidates -BinHints $ToolPathHints.MinGWBin -FileName 'mingw32-make.exe')
$mingwMake = Find-ToolPath -Candidates $makeCandidates
if (-not $mingwMake) {
    throw 'Missing mingw32-make.exe. Set TSBOT_MAKE or TSBOT_MINGW_BIN, install MinGW-w64, or add mingw32-make.exe to PATH before starting voice-service.'
}

$ffmpeg = Find-ToolPath -Candidates $ToolPathHints.FFmpeg
if (-not $ffmpeg) {
    throw 'Missing ffmpeg.exe. Set TSBOT_FFMPEG, install FFmpeg, or add ffmpeg.exe to PATH before starting voice-service.'
}

$cmake = Find-ToolPath -Candidates $ToolPathHints.CMake
if (-not $cmake) {
    throw 'Missing cmake.exe. Set TSBOT_CMAKE, set CMAKE, install CMake, or add cmake.exe to PATH before building voice-service on Windows.'
}

$grpcAddr = if ($env:TSBOT_VOICE_GRPC_ADDR) {
    $env:TSBOT_VOICE_GRPC_ADDR.Trim()
} else {
    '127.0.0.1:50051'
}

if ($grpcAddr -notmatch '^(?<host>[^:]+):(?<port>\d+)$') {
    throw "Invalid TSBOT_VOICE_GRPC_ADDR: $grpcAddr"
}

$port = [int]$Matches['port']
$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $ownerText = if ($owner) { "$($owner.ProcessName) (PID $($owner.Id))" } else { "PID $($listener.OwningProcess)" }
    throw "Port $port is already in use by $ownerText. Change TSBOT_VOICE_GRPC_ADDR in tsbot.env first."
}

$identityFile = Resolve-RepoRelativePath -Value $env:TSBOT_TS3_IDENTITY_FILE -Fallback './logs/identity.json'
$avatarDir = Resolve-RepoRelativePath -Value $env:TSBOT_TS3_AVATAR_DIR -Fallback './logs/'

[Environment]::SetEnvironmentVariable('TSBOT_TS3_IDENTITY_FILE', $identityFile, 'Process')
[Environment]::SetEnvironmentVariable('TSBOT_TS3_AVATAR_DIR', $avatarDir, 'Process')
[Environment]::SetEnvironmentVariable('TSBOT_FFMPEG', $ffmpeg, 'Process')
[Environment]::SetEnvironmentVariable('CMAKE', $cmake, 'Process')
[Environment]::SetEnvironmentVariable('CC', $gcc, 'Process')
[Environment]::SetEnvironmentVariable('CXX', $gxx, 'Process')
[Environment]::SetEnvironmentVariable('CMAKE_GENERATOR', 'MinGW Makefiles', 'Process')
[Environment]::SetEnvironmentVariable('CMAKE_MAKE_PROGRAM', $mingwMake, 'Process')
[Environment]::SetEnvironmentVariable('CMAKE_SH', 'CMAKE_SH-NOTFOUND', 'Process')

$toolDirs = @(
    (Split-Path $cargo),
    (Split-Path $cmake),
    (Split-Path $gcc),
    (Split-Path $gxx),
    (Split-Path $mingwMake),
    (Split-Path $ffmpeg)
) | Where-Object { $_ } | Select-Object -Unique
[Environment]::SetEnvironmentVariable('PATH', (($toolDirs + @($env:PATH)) -join ';'), 'Process')

Push-Location (Join-Path $repoRoot 'voice-service')
try {
    $profile = if ($env:TSBOT_VOICE_PROFILE -and $env:TSBOT_VOICE_PROFILE.Trim().ToLower() -eq 'debug') {
        'debug'
    } else {
        'release'
    }

    $targetDir = Join-Path $repoRoot (Join-Path 'voice-service\target\x86_64-pc-windows-gnu' $profile)
    $exe = Join-Path $targetDir 'voice-service.exe'

    $cargoArgs = @('build', '--target', 'x86_64-pc-windows-gnu')
    if ($profile -eq 'release') {
        $cargoArgs += '--release'
    }
    & $cargo @cargoArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    if (-not (Test-Path $exe)) {
        throw "voice-service executable not found after build: $exe"
    }

    & $exe $grpcAddr
}
finally {
    Pop-Location
}
