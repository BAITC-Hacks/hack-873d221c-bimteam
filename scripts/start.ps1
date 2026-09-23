param([switch]$Check)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$venvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    $chosenCommand = $null
    $chosenArguments = @()
    foreach ($candidate in @('py', 'python3', 'python')) {
        if (Get-Command $candidate -ErrorAction SilentlyContinue) {
            $candidateArguments = @()
            if ($candidate -eq 'py') { $candidateArguments = @('-3') }
            try {
                # Windows PowerShell 5.1 treats stderr from Store aliases as an error.
                # An unavailable candidate must not prevent trying the next Python.
                $probeOutput = & $candidate @candidateArguments -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>&1
            } catch {
                continue
            }
            if ($LASTEXITCODE -eq 0) {
                $chosenCommand = $candidate
                $chosenArguments = $candidateArguments
                break
            }
        }
    }
    if (-not $chosenCommand) {
        throw 'Нужен Python 3.11+. Установите его с python.org, включите Add Python to PATH и откройте терминал заново. Python 2.6 не подходит.'
    }
    & $chosenCommand @chosenArguments -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать .venv' }
}
& $venvPython -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Существующее .venv требует Python 3.11+. Оно не изменено.' }
& $venvPython -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Зависимости не установлены. Проверьте доступ к сети.' }
if ($Check) {
    & $venvPython scripts/run.py --check
} else {
    & $venvPython scripts/run.py
}
exit $LASTEXITCODE
