$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $projectPython)) {
    py -3 -m venv (Join-Path $PSScriptRoot '.venv')
}

& $projectPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
& $projectPython -m PyInstaller --noconfirm --clean --onefile --windowed --name CoCFarmBot --specpath (Join-Path $PSScriptRoot 'build') --workpath (Join-Path $PSScriptRoot 'build') --distpath (Join-Path $PSScriptRoot 'dist') --collect-all winrt (Join-Path $PSScriptRoot 'main.py')
