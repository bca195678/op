#Requires -Version 5.1
<#
.SYNOPSIS
    Sets up the bundled WinPython environment for axnstream.
.DESCRIPTION
    Reads version.txt to find the installer filename, runs it,
    renames the extracted folder to 'wpy64', installs pip packages
    from requirements.txt, and optionally moves the folder to the
    parent (repo-root) directory.

    Can be called from any directory - always resolves paths relative
    to the script's own location.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Helpers
function Write-Step { param([string]$Msg) Write-Host "`n==> $Msg" -ForegroundColor Cyan }
function Write-Ok   { param([string]$Msg) Write-Host "    OK: $Msg" -ForegroundColor Green }
function Write-Fail {
    param([string]$Msg)
    Write-Host "`n    ERROR: $Msg" -ForegroundColor Red
    Read-Host  "`nPress Enter to exit"
    exit 1
}

# Anchor to the script's own folder
$ScriptDir        = $PSScriptRoot
$WpyFolder        = 'wpy64'
$VersionFile      = Join-Path $ScriptDir 'version.txt'
$RequirementsFile = Join-Path $ScriptDir 'requirements.txt'

Write-Host "Working directory: $ScriptDir" -ForegroundColor DarkGray

# Step 1: Parse version.txt
Write-Step "Parsing version.txt"

if (-not (Test-Path $VersionFile)) {
    Write-Fail "version.txt not found at: $VersionFile"
}

$versionContent = Get-Content $VersionFile -Raw
$match = [regex]::Match($versionContent, "winpy_filename\s*=\s*'([^']+)'")

if (-not $match.Success) {
    Write-Fail "Could not find 'winpy_filename = ...' in version.txt"
}

$Filename      = $match.Groups[1].Value
$InstallerPath = Join-Path $ScriptDir $Filename
Write-Ok "Installer: $Filename"

# Step 2: Verify installer exists
if (-not (Test-Path $InstallerPath)) {
    Write-Fail "Installer not found: $InstallerPath"
}

# Step 3: Run installer and wait
Write-Step "Running WinPython installer"
Write-Host "    (A GUI dialog will open - complete it, then return here)" -ForegroundColor Yellow

$proc = Start-Process -FilePath $InstallerPath -WorkingDirectory $ScriptDir -PassThru -Wait

if ($proc.ExitCode -ne 0) {
    Write-Fail "Installer exited with code $($proc.ExitCode)"
}

Start-Sleep -Seconds 2   # give the FS a moment to flush

# Step 4: Find and rename WPy64-* folder
Write-Step "Locating extracted WPy64 folder"

$extracted = Get-ChildItem -Path $ScriptDir -Directory -Filter 'WPy64-*' |
             Where-Object  { $_.Name -ne $WpyFolder } |
             Sort-Object   LastWriteTime -Descending  |
             Select-Object -First 1

if (-not $extracted) {
    Write-Fail "No WPy64-* folder found after installation. Did the installer complete successfully?"
}

$destPath = Join-Path $ScriptDir $WpyFolder

if (Test-Path $destPath) {
    Write-Host "    '$WpyFolder' already exists - removing it." -ForegroundColor Yellow
    Remove-Item $destPath -Recurse -Force
}

Write-Ok "Renaming '$($extracted.Name)'  ->  '$WpyFolder'"
Rename-Item -Path $extracted.FullName -NewName $WpyFolder

# Step 5: Install pip packages (direct python.exe, no activate needed)
Write-Step "Installing Python packages from requirements.txt"

$PythonExe = Join-Path $destPath 'python\python.exe'
if (-not (Test-Path $PythonExe)) {
    Write-Fail "python.exe not found at expected path: $PythonExe"
}

if (-not (Test-Path $RequirementsFile)) {
    Write-Fail "requirements.txt not found at: $RequirementsFile"
}

& $PythonExe -m pip install -r $RequirementsFile --no-warn-script-location

if ($LASTEXITCODE -ne 0) {
    Write-Fail "pip install failed (exit code $LASTEXITCODE)"
}

Write-Ok "Packages installed successfully"

# Step 6: Optionally move wpy64 to parent directory (repo root)
Write-Host ""
$choice = Read-Host "Move '$WpyFolder' to the parent (repo root) directory? [Y/N]"

if ($choice -match '^[Yy]') {
    $parentDir  = Split-Path $ScriptDir -Parent
    $parentDest = Join-Path  $parentDir $WpyFolder

    if (Test-Path $parentDest) {
        Write-Host "    '$WpyFolder' already exists in parent - removing it." -ForegroundColor Yellow
        Remove-Item $parentDest -Recurse -Force
    }

    Move-Item -Path $destPath -Destination $parentDest
    Write-Ok "Moved to: $parentDest"
} else {
    Write-Ok "Kept in: $ScriptDir"
}

Write-Host "`nSetup complete.`n" -ForegroundColor Green
Read-Host "Press Enter to exit"
