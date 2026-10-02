<#
.SYNOPSIS
Installs Windows dependencies and prepares a Codex MCP configuration fragment.
.EXAMPLE
.\install-windows.bat -SkipTemplates
.EXAMPLE
.\install-windows.bat -SamplesRoot 'D:\NI\Circuit Design Suite 14.3\samples'
#>
[CmdletBinding()]
param(
    [string]$Python32,
    [string]$SamplesRoot,
    [switch]$SkipTemplates,
    [switch]$SelfCheck
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

function Invoke-Native {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Program failed (exit $LASTEXITCODE)."
    }
}

# A runnable check for the failure gate, without installing or launching Multisim.
if ($SelfCheck) {
    foreach ($Script in @($PSCommandPath, (Join-Path $RepoRoot 'mcp_server\setup.ps1'))) {
        $ParseErrors = $null
        $Tokens = $null
        $null = [System.Management.Automation.Language.Parser]::ParseFile($Script, [ref]$Tokens, [ref]$ParseErrors)
        if ($ParseErrors.Count) { throw ($ParseErrors | Out-String) }
    }
    $ShellName = if ($env:OS -eq 'Windows_NT') { 'powershell.exe' } else { 'pwsh' }
    $Shell = Join-Path $PSHOME $ShellName
    Invoke-Native $Shell @('-NoProfile', '-Command', 'exit 0')
    $Rejected = $false
    try { Invoke-Native $Shell @('-NoProfile', '-Command', 'exit 7') }
    catch { $Rejected = $_.Exception.Message -match 'exit 7' }
    if (-not $Rejected) { throw 'Failed commands must stop the installer.' }
    $MockRoot = Join-Path ([IO.Path]::GetTempPath()) ('multisim-install-check-' + [guid]::NewGuid())
    $null = New-Item -ItemType Directory -Path $MockRoot
    $MockPython = Join-Path $MockRoot 'python.ps1'
    $OriginalLocation = Get-Location
    try {
        Set-Content -LiteralPath $MockPython -Encoding ASCII -Value @'
if ($args[0] -eq '-c') { $global:LASTEXITCODE = 0; '32' }
else { $global:LASTEXITCODE = 9 }
'@
        $Rejected = $false
        try { & (Join-Path $RepoRoot 'mcp_server\setup.ps1') -Python $MockPython }
        catch { $Rejected = $_.Exception.Message -match 'pip upgrade failed' }
        if (-not $Rejected) { throw 'setup.ps1 must reject failed pip installation.' }
    } finally {
        Set-Location -LiteralPath $OriginalLocation.Path
        Remove-Item -LiteralPath $MockRoot -Recurse -Force
    }
    Write-Host 'PASS: PowerShell syntax, native-command failure gate, and pip failure propagation.'
    exit 0
}

if ($env:OS -ne 'Windows_NT') { throw 'Run install-windows.bat on Windows 10/11.' }
$InstallRoot = Join-Path $env:LOCALAPPDATA 'MultisimMcp'
$LogRoot = Join-Path $InstallRoot 'logs'
$PackRoot = Join-Path $InstallRoot 'component-pack'
$NpmRoot = Join-Path $InstallRoot 'npm'
$VenvRoot = Join-Path $InstallRoot 'venv32'
$ConfigPath = Join-Path $InstallRoot 'codex-multisim.toml'
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
$LogPath = Join-Path $LogRoot (Get-Date -Format 'install-yyyyMMdd-HHmmss.log')
Start-Transcript -Path $LogPath | Out-Null

try {
    Write-Host "Repository: $RepoRoot"
    Write-Host "Installation: $InstallRoot"
    Write-Host "Log: $LogPath"
    Write-Host 'NI Multisim and its license must be installed separately.'
    Set-Location -LiteralPath $RepoRoot

    # Reuse Python 3.13 x86 if present; WinGet verifies downloaded installers.
    if (-not $Python32) {
        $Python32 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python313-32\python.exe'
        if (-not (Test-Path -LiteralPath $Python32)) {
            if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
                throw 'WinGet is missing. Install/update Microsoft App Installer, or provide -Python32 and install Node.js LTS first.'
            }
            Write-Host '[1/6] Installing Python 3.13 (32-bit)...'
            # --force also permits x86 installation when this package ID exists as x64.
            Invoke-Native 'winget.exe' @('install', '--id', 'Python.Python.3.13', '--exact', '--source', 'winget', '--architecture', 'x86', '--scope', 'user', '--force', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
            if (-not (Test-Path -LiteralPath $Python32)) {
                throw 'Python is installed in a custom location. Run again with -Python32 C:\path\to\python.exe.'
            }
        }
    }
    $Python32 = (Resolve-Path -LiteralPath $Python32).Path
    Invoke-Native $Python32 @('-c', 'import struct,sys; assert struct.calcsize(''P'')==4 and sys.version_info>=(3,11), ''Python 3.11+ (32-bit) required by this installer''')

    # Refresh PATH in this process after WinGet; keep pre-existing process entries.
    $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:PATH
    $Node = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $Node -or [int]((& $Node.Source --version).TrimStart('v').Split('.')[0]) -lt 18) {
        if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
            throw 'Install Node.js LTS from nodejs.org, then run again.'
        }
        Write-Host '[2/6] Installing Node.js LTS (Windows may request administrator permission)...'
        Invoke-Native 'winget.exe' @('install', '--id', 'OpenJS.NodeJS.LTS', '--exact', '--source', 'winget', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
        $env:PATH = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:PATH
        $Node = Get-Command node.exe -ErrorAction Stop
    }
    Invoke-Native $Node.Source @('-e', 'if (Number(process.versions.node.split(''.'')[0]) < 18) process.exit(1)')
    $NodeDir = Split-Path -Parent $Node.Source
    $Npm = Join-Path $NodeDir 'npm.cmd'
    if (-not (Test-Path -LiteralPath $Npm)) { throw "npm.cmd is missing from $NodeDir. Repair Node.js LTS." }

    Write-Host '[3/6] Installing MCP in an isolated 32-bit environment...'
    $VenvPython = Join-Path $VenvRoot 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Invoke-Native $Python32 @('-m', 'venv', $VenvRoot)
    }
    Invoke-Native $VenvPython @('-c', 'import struct; assert struct.calcsize(''P'')==4, ''Existing venv must be 32-bit''')
    & (Join-Path $RepoRoot 'mcp_server\setup.ps1') -Python $VenvPython
    Set-Location -LiteralPath $RepoRoot
    Invoke-Native $VenvPython @('-m', 'pip', 'check')
    Invoke-Native $VenvPython @('-c', 'import mcp,win32com.client,multisim_mcp')
    $Cli = Join-Path $VenvRoot 'Scripts\multisim-mcp.exe'

    Write-Host '[4/6] Installing the pinned .ms14 codec...'
    Invoke-Native $Npm @('install', '--global', '--prefix', $NpmRoot, 'electronics-workbench-decoder@0.2.0')
    $env:MULTISIM_MCP_EWD = Join-Path $NpmRoot 'node_modules\electronics-workbench-decoder\dist\ewd.js'
    $env:MULTISIM_MCP_EWE = Join-Path $NpmRoot 'node_modules\electronics-workbench-decoder\dist\ewe.js'
    foreach ($Codec in @($env:MULTISIM_MCP_EWD, $env:MULTISIM_MCP_EWE)) {
        if (-not (Test-Path -LiteralPath $Codec)) { throw "Codec file is missing: $Codec" }
    }
    $env:MULTISIM_MCP_TEMPLATE_DIR = $PackRoot
    $env:MULTISIM_MCP_WORKER_PYTHON = $VenvPython

    Write-Host '[5/6] Preparing Codex configuration...'
    Invoke-Native $Cli @('config', '--client', 'codex', '--python', $VenvPython, '--worker-python', $VenvPython, '--template-dir', $PackRoot, '--tool-profile', 'experiment', '--output', $ConfigPath, '--force')
    # The generator has already opened the [mcp_servers.multisim.env] table.
    $ExtraEnv = @{
        MULTISIM_MCP_EWD = $env:MULTISIM_MCP_EWD
        MULTISIM_MCP_EWE = $env:MULTISIM_MCP_EWE
        PATH = "$NodeDir;$NpmRoot;$env:PATH"
    }
    foreach ($Key in ($ExtraEnv.Keys | Sort-Object)) {
        $Value = ConvertTo-Json -InputObject $ExtraEnv[$Key] -Compress
        [IO.File]::AppendAllText($ConfigPath, "$Key = $Value`n", [Text.UTF8Encoding]::new($false))
    }
    Invoke-Native $VenvPython @('-c', 'import sys,tomllib; tomllib.load(open(sys.argv[1],''rb''))', $ConfigPath)
    Write-Host "Copy the contents of $ConfigPath into your Codex config.toml and restart Codex."

    Write-Host '[6/6] Creating local Multisim templates and checking readiness...'
    if ($SkipTemplates) {
        Write-Host 'Template creation skipped. Run again without -SkipTemplates after installing Multisim.'
    } elseif (Test-Path -LiteralPath (Join-Path $PackRoot 'local-pack-manifest.json')) {
        Write-Host "Keeping the existing template pack: $PackRoot"
    } else {
        if (-not $SamplesRoot) {
            $Candidates = @(Get-ChildItem -LiteralPath (Join-Path $env:PUBLIC 'Documents\National Instruments') -Directory -Filter 'Circuit Design Suite *' -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName 'samples' } |
                Where-Object { Test-Path -LiteralPath (Join-Path $_ 'LowPassFilter.ms14') })
            if (-not $Candidates.Count) {
                throw 'Multisim samples not found. Install licensed Multisim with samples, then rerun; or use -SamplesRoot / -SkipTemplates.'
            }
            $SamplesRoot = $Candidates[0]
        }
        $SamplesRoot = (Resolve-Path -LiteralPath $SamplesRoot).Path
        Write-Host 'Save all open Multisim projects first: template generation creates a temporary blank circuit.'
        $null = Read-Host 'Press Enter after saving your work'
        Invoke-Native $VenvPython @((Join-Path $RepoRoot 'tools\bootstrap_local_component_pack.py'), '--samples-root', $SamplesRoot, '--output', $PackRoot)
    }
    if ($SkipTemplates) { Invoke-Native $Cli @('doctor', '--lang', 'en') }
    else { Invoke-Native $Cli @('doctor', '--lang', 'en', '--connect', '--strict') }
    Write-Host "Dependencies installed. Codex configuration: $ConfigPath"
    Write-Host "Keep the repository at $RepoRoot (the package is installed in editable mode)."
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Log: $LogPath"
    exit 1
} finally {
    Stop-Transcript | Out-Null
}
