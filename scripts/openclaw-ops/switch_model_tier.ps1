param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ArgsText
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "switch_model_tier.py"

if (-not (Test-Path $PythonScript)) {
    Write-Error "script not found: $PythonScript"
    exit 1
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Error "python command not found in PATH"
    exit 1
}

& python $PythonScript @ArgsText
exit $LASTEXITCODE
