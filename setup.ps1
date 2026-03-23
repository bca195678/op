# Split Windows Terminal into 2x2 grid
# This script launches Windows Terminal with 4 panes in a 2x2 layout

# Get the current working directory
$cwd = Get-Location

# Check if wpy64 exists
if (-not (Test-Path "$cwd\wpy64")) {
    Write-Host "ERROR: WinPython environment not found at '$cwd\wpy64'." -ForegroundColor Red
    Write-Host "Run the setup script first to install WinPython." -ForegroundColor Yellow
    exit 1
}

# Launch Windows Terminal with 2x2 split layout
# Layout:
# +-------+-------+
# |   1   |   2   |
# +-------+-------+
# |   3   |   4   |
# +-------+-------+

# Pane 1 runs: . .\winstart.ps1 then pyserial-miniterm COM200

# Pane 1 (top-left)
wt -w 0 -d "$cwd" --colorScheme "One Half Dark"  powershell -NoExit -File "$cwd\pane1-start.ps1"
Start-Sleep -Milliseconds 1000

# Pane 2 (top-right): split Pane 1 vertically
wt -w 0 split-pane -V --title "Pane 2" --colorScheme "Vintage" -d "$cwd"
Start-Sleep -Milliseconds 200

# Pane 3 (bottom-left, SSH): move to Pane 1, split horizontally
wt -w 0 move-focus left `; split-pane -H --title "Pane 3 (SSH)" --colorScheme "Campbell Powershell" -d "$cwd" powershell -NoExit -Command "ssh chester@172.31.230.36"
Start-Sleep -Milliseconds 200

# Pane 4 (bottom-right): move to Pane 2, split horizontally
wt -w 0 move-focus right `; split-pane -H --title "Pane 4" --colorScheme "Vintage" -d "$cwd"
