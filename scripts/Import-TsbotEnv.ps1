param(
    [string]$Path = (Join-Path (Split-Path $PSScriptRoot -Parent) 'tsbot.env')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path $Path)) {
    return
}

$pattern = '^(?:export\s+)?(?<key>[A-Za-z_][A-Za-z0-9_]*)=(?<value>.*)$'

foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
    $trimmed = $line.Trim()
    if (-not $trimmed) {
        continue
    }
    if ($trimmed.StartsWith('#')) {
        continue
    }

    $match = [regex]::Match($trimmed, $pattern)
    if (-not $match.Success) {
        continue
    }

    $key = $match.Groups['key'].Value
    $value = $match.Groups['value'].Value.Trim()

    if ($value.Length -ge 2) {
        $doubleQuote = [string][char]34
        $singleQuote = [string][char]39
        $startsWithDouble = $value.StartsWith($doubleQuote)
        $endsWithDouble = $value.EndsWith($doubleQuote)
        $startsWithSingle = $value.StartsWith($singleQuote)
        $endsWithSingle = $value.EndsWith($singleQuote)
        if (($startsWithDouble -and $endsWithDouble) -or ($startsWithSingle -and $endsWithSingle)) {
            $value = $value.Substring(1, $value.Length - 2)
        }
    }

    [Environment]::SetEnvironmentVariable($key, $value, 'Process')
}
