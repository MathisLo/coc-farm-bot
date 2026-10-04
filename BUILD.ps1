param([switch]$SkipDependencyInstall)

$ErrorActionPreference = 'Stop'
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $projectPython)) {
    py -3 -m venv (Join-Path $PSScriptRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw "Création de l’environnement Python échouée." }
}

if (-not $SkipDependencyInstall) {
    & $projectPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Installation des dépendances échouée.' }
}
& $projectPython -c 'import webview; assert callable(webview.create_window)'
if ($LASTEXITCODE -ne 0) { throw 'pywebview absent : installer les dépendances avant de construire le lanceur.' }

Push-Location $PSScriptRoot
try {
    & $projectPython -B -m unittest -v test_main test_regressions test_storage test_windows_integration test_stats test_upgrades test_runtime test_auto_update
    if ($LASTEXITCODE -ne 0) { throw 'Tests échoués : aucun exécutable remplacé.' }

    $buildDirectory = Join-Path $PSScriptRoot 'build'
    $stagingDirectory = Join-Path $buildDirectory 'release'
    New-Item -ItemType Directory -Path $buildDirectory -Force | Out-Null
    $sourceNames = @('main.py', 'app_meta.py', 'auto_update.py', 'calibration.py', 'farm_stats.py', 'dashboard.py', 'dashboard_layout.py', 'ui_theme.py', 'ui_widgets.py', 'modern_dashboard.py', 'web_dashboard.html', 'upgrades.py', 'requirements.txt')
    $sourceNames += Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'assets') -File -Recurse | ForEach-Object { $_.FullName.Substring($PSScriptRoot.Length + 1).Replace('\','/') }
    $sourceNames += Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot 'ui') -File -Recurse | ForEach-Object { $_.FullName.Substring($PSScriptRoot.Length + 1).Replace('\','/') }
    $sourceNames = @($sourceNames | Sort-Object -Unique)
    $sourceHashes = [ordered]@{}
    foreach ($sourceName in $sourceNames) {
        $sourceHashes[$sourceName] = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $sourceName) -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $buildInfoPath = Join-Path $buildDirectory 'build_info.json'
    [ordered]@{ built_at_utc = [DateTime]::UtcNow.ToString('o'); sources = $sourceHashes } |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $buildInfoPath -Encoding UTF8

    $versionInfoPath = Join-Path $buildDirectory 'version_info.txt'
    & $projectPython (Join-Path $PSScriptRoot 'tools\build_version_info.py') $versionInfoPath
    if ($LASTEXITCODE -ne 0) { throw 'Ressource de version Windows invalide.' }
    $appIcon = Join-Path $PSScriptRoot 'assets\kit\app\app.ico'
    & $projectPython -m PyInstaller --noconfirm --onefile --windowed --name CoCFarmBot --specpath $buildDirectory --workpath $buildDirectory --distpath $stagingDirectory --icon $appIcon --version-file $versionInfoPath --collect-all winrt --collect-all webview --add-data "$buildInfoPath;." --add-data "$(Join-Path $PSScriptRoot 'assets');assets" --add-data "$(Join-Path $PSScriptRoot 'ui');ui" --add-data "$(Join-Path $PSScriptRoot 'web_dashboard.html');." (Join-Path $PSScriptRoot 'main.py')
    if ($LASTEXITCODE -ne 0) { throw 'Construction échouée : ancien exécutable conservé.' }
    foreach ($sourceName in $sourceNames) {
        if ((Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $sourceName) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sourceHashes[$sourceName]) {
            throw 'Sources modifiées pendant la construction : reconstruire avant de publier.'
        }
    }

    $stagedExecutable = Join-Path $stagingDirectory 'CoCFarmBot.exe'
    $reportPath = Join-Path $buildDirectory ('release-check-' + [guid]::NewGuid().ToString('N') + '.json')
    $releaseCheck = Start-Process -FilePath $stagedExecutable -ArgumentList @('--self-test-report', ('"' + $reportPath + '"')) -PassThru -WindowStyle Hidden
    if (-not $releaseCheck.WaitForExit(45000)) {
        # This is only the verification process started here, never a running bot.
        $releaseCheck.Kill()
        throw "Autotest de l’exécutable expiré : ancien exécutable conservé."
    }
    $releaseCheck.Refresh()
    if ($releaseCheck.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $reportPath)) { throw "Autotest de l’exécutable échoué." }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if (-not $report.ok -or -not $report.frozen) { throw 'Rapport de validation invalide.' }
    foreach ($sourceName in $sourceNames) {
        if ($report.build.sources.$sourceName -ne $sourceHashes[$sourceName]) { throw "Source embarquée incorrecte : $sourceName" }
    }
    $distDirectory = Join-Path $PSScriptRoot 'dist'
    New-Item -ItemType Directory -Path $distDirectory -Force | Out-Null
    $finalExecutable = Join-Path $distDirectory 'CoCFarmBot.exe'
    Copy-Item -LiteralPath $stagedExecutable -Destination $finalExecutable -Force
    Copy-Item -LiteralPath $reportPath -Destination (Join-Path $distDirectory 'release-check.json') -Force
    $executableHash = (Get-FileHash -LiteralPath $finalExecutable -Algorithm SHA256).Hash.ToLowerInvariant()
    [ordered]@{ executable_sha256 = $executableHash; sources = $sourceHashes } |
        ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $distDirectory 'build-manifest.json') -Encoding UTF8
    Write-Output "Exécutable testé et à jour : $finalExecutable"
} finally {
    Pop-Location
}
