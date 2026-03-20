# Wrapper script for pane 1: setup environment then run miniterm
. wpy64\scripts\WinPython_PS_Prompt.ps1


# Get the current working directory
$cwd = Get-Location

# Check if VSPE (Virtual Serial Port Emulator) is running; start it if not
$vspe = Get-Process -Name "VSPEmulator" -ErrorAction SilentlyContinue
if (-not $vspe) {
    Write-Host "VSPE is not running. Starting vspe_setup.vspe..." -ForegroundColor Yellow
    Start-Process "$cwd\vspe_setup.vspe"
    Start-Sleep -Seconds 3
    $vspe = Get-Process -Name "VSPEmulator" -ErrorAction SilentlyContinue
    if (-not $vspe) {
        Write-Host "ERROR: Failed to start VSPE. Please open 'vspe_setup.vspe' manually." -ForegroundColor Red
        exit 1
    }
    Write-Host "VSPE started successfully." -ForegroundColor Green
}

# Check if wpy64 exists
if (-not (Test-Path "$cwd\wpy64")) {
    Write-Host "ERROR: WinPython environment not found at '$cwd\wpy64'." -ForegroundColor Red
    Write-Host "Run the setup script first to install WinPython." -ForegroundColor Yellow
    exit 1
}



pyserial-miniterm COM200
