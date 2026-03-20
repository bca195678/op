@echo off
setlocal enabledelayedexpansion

REM Define the wpy_folder variable at the beginning
set "wpy_folder=wpy64"

REM Step 1: Extract the WinPython filename from version.txt
set "filename="
for /f "tokens=2 delims=='" %%i in ('findstr "winpy_filename" version.txt') do (
    set "filename=%%i"
)

REM Confirm that the filename has been extracted
echo Filename extracted: %filename%

REM Check if the extracted filename is correct
if not defined filename (
    echo Error: Filename not found in version.txt. Exiting.
	pause
    exit /b 1
)

REM Check if the file exists
if not exist "%filename%" (
    echo Error: The file "%filename%" does not exist. Exiting.
	pause
    exit /b 1
)

REM Step 1: Run the WinPython installer
echo Running WinPython installer: %filename%
start /wait "" "%filename%"

REM Step 2: Rename the extracted folder to %wpy_folder%
if exist "%wpy_folder%" (
    echo Folder %wpy_folder% already exists. Removing it.
    rd /s /q "%wpy_folder%"
)

for /d %%D in (WPy64-*) do (
    echo Renaming %%D to %wpy_folder%
    move "%%D" "%wpy_folder%"
)
timeout /t 3 /nobreak >nul



REM Step 3: Activate WinPython environment
echo Activating WinPython environment
if not exist ".\%wpy_folder%\scripts\activate.bat" (
    echo Error: WinPython activation script not found. Exiting.
    pause
    exit /b 1
)

call ".\%wpy_folder%\scripts\activate.bat"
timeout /t 3 /nobreak >nul

if errorlevel 1 (
    echo Error: Failed to activate WinPython environment.
    pause
    exit /b 1
)

echo WinPython environment activated successfully


REM Step 4: [DEPRECATED]
REM Step 5: Install required Python packages
echo Installing Python packages
python -m pip install -r .\requirements.txt --no-warn-script-location

REM Step 6: Ask user if they want to move %wpy_folder% folder to the parent directory
echo.
set /p move_choice="Do you want to move %wpy_folder% folder to the parent directory? (Y/N): "
if /i "%move_choice%"=="Y" (
	if exist ..\%wpy_folder% (
		echo Folder %wpy_folder% already exists at parent directory. Removing it.
		rd /s /q ..\%wpy_folder%
	)
    move .\%wpy_folder% ..\
) else (
    echo Keeping %wpy_folder% in current directory
)


echo Script completed.
pause