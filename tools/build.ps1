#requires -Version 5.1
<#
.SYNOPSIS
Build both Windows release layouts in dist using an isolated Python environment.
.EXAMPLE
.\tools\build.ps1
.EXAMPLE
.\tools\build.ps1 -Version '1.0.1' -Python 'C:\Python313\python.exe' -SkipInstall
#>
[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?$')]
    [string]$Version,
    [string]$Python = 'python',
    [switch]$SkipInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit $LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
}

if ($env:OS -ne 'Windows_NT') {
    throw 'Run this script on Windows to build Windows executables.'
}

$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $PSBoundParameters.ContainsKey('Version')) {
    do {
        $Version = (Read-Host 'Enter release version (for example, 1.0.0)').Trim()
        $validVersion = $Version -match '^\d+\.\d+\.\d+(?:-[A-Za-z0-9]+(?:[.-][A-Za-z0-9]+)*)?$'
        if (-not $validVersion) {
            Write-Host 'Use a version such as 1.0.0 or 1.1.0-beta.1.' -ForegroundColor Yellow
        }
    } until ($validVersion)
}
$releaseName = "v$Version"
$buildRoot = Join-Path (Join-Path $projectRoot 'build') $releaseName
$distRoot = Join-Path (Join-Path $projectRoot 'dist') $releaseName
$environmentRoot = Join-Path $projectRoot '.venv-build'
$buildPython = Join-Path $environmentRoot 'Scripts\python.exe'

Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath $buildPython -PathType Leaf)) {
        Invoke-Checked $Python @('-c', 'import sys; assert sys.version_info >= (3, 10), "Python 3.10 or newer is required"')
        Invoke-Checked $Python @('-m', 'venv', $environmentRoot)
    }

    if (-not $SkipInstall) {
        # Also repairs pip if a previous environment creation was interrupted.
        Invoke-Checked $buildPython @('-m', 'ensurepip', '--upgrade')
        Invoke-Checked $buildPython @('-m', 'pip', 'install', '-r', (Join-Path $projectRoot 'requirements.txt'))
    }
    Invoke-Checked $buildPython @('-m', 'pip', 'check')
    Invoke-Checked $buildPython @('-c', 'import tkinter, tkinterdnd2, cryptography, fontTools, PIL, qrcode, PyInstaller; import main, modules.alphabet_print')
    Invoke-Checked $buildPython @('-m', 'unittest', 'discover', '-s', 'tests', '-t', '.', '-v')

    $commonArguments = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--noupx',
        '--name', 'BOneTool',
        '--add-data', "$(Join-Path $projectRoot 'fonts'):fonts",
        '--collect-all', 'tkinterdnd2',
        '--collect-submodules', 'fontTools',
        '--hidden-import', 'PIL.PdfImagePlugin'
    )

    foreach ($layout in @('portable', 'loose')) {
        Write-Host "Building $releaseName $layout release..." -ForegroundColor Cyan
        $mode = if ($layout -eq 'portable') { '--onefile' } else { '--onedir' }
        $workPath = Join-Path $buildRoot $layout
        New-Item -ItemType Directory -Path $workPath -Force | Out-Null
        $arguments = $commonArguments + @(
            $mode, '--distpath', (Join-Path $distRoot $layout),
            '--workpath', (Join-Path $workPath 'work'), '--specpath', $workPath,
            (Join-Path $projectRoot 'main.py')
        )
        Invoke-Checked $buildPython $arguments
    }

    $portableExe = Join-Path $distRoot 'portable\BOneTool.exe'
    $looseExe = Join-Path $distRoot 'loose\BOneTool\BOneTool.exe'
    foreach ($executable in @($portableExe, $looseExe)) {
        if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
            throw "Build output is missing: $executable"
        }
    }
    Write-Host "`nRelease $releaseName builds ready:" -ForegroundColor Green
    Write-Host "Portable: $portableExe"
    Write-Host "Loose:    $(Split-Path -Parent $looseExe) (distribute the entire folder)"
} finally {
    Pop-Location
}
