$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $projectPython)) {
    py -3 -m venv (Join-Path $PSScriptRoot '.venv')
}

& $projectPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
& $projectPython -m PyInstaller --noconfirm --clean --onefile --windowed --name CoCFarmBot --collect-all winrt (Join-Path $PSScriptRoot 'main.py')
