@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo ======================================
echo    Todoist Assistant Installer
echo ======================================
echo.

REM Determine the directory of this script (handles elevation changing CWD)
set "SCRIPT_DIR=%~dp0"
REM Normalize: remove trailing backslash if present then add single backslash
if "%SCRIPT_DIR:~-1%"=="\" (
  set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
)
set "SCRIPT_DIR=%SCRIPT_DIR%\"

REM Sanity check: ensure we're not running from inside the ZIP preview
if not exist "%SCRIPT_DIR%TodoistAssistant.exe" (
    echo Error: Could not find TodoistAssistant.exe next to install.bat
    echo If you opened the ZIP directly, please extract the entire archive first,
    echo then run install.bat from the extracted folder.
    echo.
    pause
    exit /b 1
)

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    set "IS_ADMIN=1"
    echo Running with administrator privileges...
) else (
    set "IS_ADMIN=0"
    echo Not running as administrator.
)

echo.
echo Installing Todoist Assistant...

REM Choose install location: Program Files when elevated, else per-user
if "%IS_ADMIN%"=="1" (
    set "INSTALL_DIR=%ProgramFiles%\TodoistAssistant"
) else (
    set "INSTALL_DIR=%LocalAppData%\Programs\TodoistAssistant"
    echo Installing to per-user location:
    echo   %INSTALL_DIR%
)

REM Create program directory (and parents if needed)
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%" 2>nul
if not exist "%INSTALL_DIR%" (
    echo Access is denied. Unable to create install directory:
    echo   %INSTALL_DIR%
    echo Try running install.bat as Administrator or choose a writable folder.
    pause
    exit /b 1
)

REM Copy executable and supporting files
echo Copying files...
set "EXE_NAME=TodoistAssistant.exe"
copy /Y "%SCRIPT_DIR%!EXE_NAME!" "%INSTALL_DIR%" >nul || (
    echo Error: !EXE_NAME! not found
    pause & exit /b 1
)

REM Prefer robocopy for directories; fall back to xcopy if not available
if exist "%SCRIPT_DIR%configs" (
    where robocopy >nul 2>&1 && (
        robocopy "%SCRIPT_DIR%configs" "%INSTALL_DIR%\configs" /E /NFL /NDL /NJH /NJS /NC /NS >nul
        REM robocopy returns codes^>0 on success; treat anything <8 as success
        if errorlevel 8 (
            echo Warning: Failed copying configs directory.
        )
    ) || (
        xcopy "%SCRIPT_DIR%configs" "%INSTALL_DIR%\configs\" /E /I /Q /Y >nul
    )
)
if exist "%SCRIPT_DIR%.env.example" copy /Y "%SCRIPT_DIR%.env.example" "%INSTALL_DIR%" >nul
if exist "%SCRIPT_DIR%README.md" copy /Y "%SCRIPT_DIR%README.md" "%INSTALL_DIR%" >nul
if exist "%SCRIPT_DIR%LICENSE" copy /Y "%SCRIPT_DIR%LICENSE" "%INSTALL_DIR%" >nul
if exist "%SCRIPT_DIR%img" (
    where robocopy >nul 2>&1 && (
        robocopy "%SCRIPT_DIR%img" "%INSTALL_DIR%\img" /E /NFL /NDL /NJH /NJS /NC /NS >nul
        if errorlevel 8 (
            echo Warning: Failed copying img directory.
        )
    ) || (
        xcopy "%SCRIPT_DIR%img" "%INSTALL_DIR%\img\" /E /I /Q /Y >nul
    )
)

REM Create shortcuts (.lnk) using PowerShell for proper Start Menu/Desktop entries
echo Creating shortcuts...
set "DESKTOP=%USERPROFILE%\Desktop"
set "STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Todoist Assistant"
if not exist "%STARTMENU%" mkdir "%STARTMENU%" >nul 2>&1

REM Desktop shortcut
powershell -NoProfile -ExecutionPolicy Bypass -Command "$W=New-Object -ComObject WScript.Shell; $S=$W.CreateShortcut('%DESKTOP%\Todoist Assistant.lnk'); $S.TargetPath='%INSTALL_DIR%\%EXE_NAME%'; $S.WorkingDirectory='%INSTALL_DIR%'; $S.IconLocation='%INSTALL_DIR%\%EXE_NAME%,0'; $S.Save()" >nul 2>&1

REM Start menu shortcut
powershell -NoProfile -ExecutionPolicy Bypass -Command "$W=New-Object -ComObject WScript.Shell; $S=$W.CreateShortcut('%STARTMENU%\Todoist Assistant.lnk'); $S.TargetPath='%INSTALL_DIR%\%EXE_NAME%'; $S.WorkingDirectory='%INSTALL_DIR%'; $S.IconLocation='%INSTALL_DIR%\%EXE_NAME%,0'; $S.Save()" >nul 2>&1

REM Create Uninstall script in Start Menu folder
(
  echo @echo off
  echo echo Uninstalling Todoist Assistant...
  echo rmdir /s /q "%INSTALL_DIR%"
  echo del "%DESKTOP%\Todoist Assistant.lnk" ^>nul 2^>^&1
  echo del "%STARTMENU%\Todoist Assistant.lnk" ^>nul 2^>^&1
  echo echo Uninstallation complete.
  echo pause
) > "%STARTMENU%\Uninstall Todoist Assistant.bat"

echo.
echo ======================================
echo Installation completed successfully!
echo ======================================
echo.
echo You can now run Todoist Assistant by:
echo   1. Double-clicking "Todoist Assistant" on your desktop
echo   2. Finding it in your Start Menu
if "%IS_ADMIN%"=="1" (
  echo   3. Running: "%ProgramFiles%\TodoistAssistant\%EXE_NAME%"
) else (
  echo   3. Running: "%LocalAppData%\Programs\TodoistAssistant\%EXE_NAME%"
)
echo.
echo On first run, you'll need to configure your Todoist API key.
echo Get your API key from: https://todoist.com/prefs/integrations
echo.
echo Press any key to launch Todoist Assistant now...
pause >nul

start "" "%INSTALL_DIR%\%EXE_NAME%"
endlocal
exit /b 0