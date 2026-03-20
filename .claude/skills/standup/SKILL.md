---
name: standup
description: Set up the WinPython environment — extract installer, install pip packages, verify. The counterpart to /teardown. Use when starting fresh on a new machine or after a clean clone.
---

# standup

Sets up the project's bundled WinPython environment at `./wpy64/`. Extracts the self-extracting installer from `wpy64_src/`, installs pip dependencies, and verifies everything works. Idempotent — skips steps that are already done.

## What Gets Set Up

| # | Target | Check | Action |
|---|--------|-------|--------|
| 1 | WinPython (`./wpy64/`) | `./wpy64/python/python.exe` exists? | Run `wpy64_src/setup_wpy.ps1` (GUI installer) |
| 2 | Pip packages | All imports succeed? | `python -m pip install -r wpy64_src/requirements.txt` |
| 3 | Temp directory (`./tmp/`) | Directory exists? | `mkdir -p ./tmp` |

## Step-by-Step Workflow

### Step 1 — Check if WinPython is already installed

```bash
ls ./wpy64/python/python.exe 2>/dev/null && echo "INSTALLED" || echo "MISSING"
```

If `INSTALLED`, skip to Step 3.

### Step 2 — Run WinPython setup

```bash
powershell -ExecutionPolicy Bypass -File ./wpy64_src/setup_wpy.ps1
```

**Important:** This opens a **GUI installer window**. Tell the user:
> "The WinPython installer window has opened. Please complete the installer dialog (accept defaults and click through). The script will continue automatically after the installer finishes."

The script handles:
1. Parsing `wpy64_src/version.txt` for the installer filename
2. Launching the self-extracting `.exe`
3. Finding and renaming the extracted `WPy64-*` folder to `wpy64`
4. Installing packages from `wpy64_src/requirements.txt`

### Step 3 — Verify installation

```bash
PYTHON=./wpy64/python/python.exe
"$PYTHON" --version
"$PYTHON" -c "import serial, pytest, psutil, requests, cv2, tftpy; print('ALL PACKAGES OK')"
```

If any import fails, re-run pip install:
```bash
"$PYTHON" -m pip install -r ./wpy64_src/requirements.txt --no-warn-script-location
```

### Step 4 — Ensure tmp directory exists

```bash
mkdir -p ./tmp
```

### Step 5 — Report status

Print a summary:
```
Component              Status
--------------------------------------------
WinPython (wpy64)      installed (Python 3.13.5)
Pip packages           all OK
Temp directory         ready
```

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `wpy64` not created after setup | Installer GUI was dismissed without completing | Re-run `setup_wpy.ps1` and complete the installer |
| `ModuleNotFoundError` for a package | pip install failed or was interrupted | Run `"$PYTHON" -m pip install -r ./wpy64_src/requirements.txt` |
| `python.exe` not found at expected path | Installer extracted to wrong location | Check `wpy64_src/` for a `WPy64-*` folder and rename it to `wpy64` |
| Installer opens but nothing happens | Antivirus blocking the `.exe` | Whitelist `wpy64_src/Winpython64-*.exe` in Windows Defender |
