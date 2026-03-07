param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
$scriptPath = Join-Path $PSScriptRoot "remote_safe_update.py"

if (-not (Test-Path $scriptPath)) {
    throw "script not found: $scriptPath"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source $scriptPath @Args
    exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $scriptPath @Args
    exit $LASTEXITCODE
}

throw "python runtime not found (checked: python, py -3)"
