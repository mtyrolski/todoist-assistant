@echo off
echo ======================================
echo    Todoist Assistant Installer
echo ======================================
echo.

REM Check if running as administrator
net session >nul 2>&1
if %errorLevel% == 0 (
    echo Running with administrator privileges...
) else (
    echo Note: Not running as administrator. Desktop shortcut creation may require manual action.
)

echo.
echo Installing Todoist Assistant...

REM Create program directory
set INSTALL_DIR=%ProgramFiles%\TodoistAssistant
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

REM Copy executable and files
echo Copying files...
copy "TodoistAssistant.exe" "%INSTALL_DIR%\" >nul
if exist "configs" xcopy "configs" "%INSTALL_DIR%\configs\" /E /I /Q >nul
if exist ".env.example" copy ".env.example" "%INSTALL_DIR%\" >nul
if exist "README.md" copy "README.md" "%INSTALL_DIR%\" >nul
if exist "LICENSE" copy "LICENSE" "%INSTALL_DIR%\" >nul
if exist "img" xcopy "img" "%INSTALL_DIR%\img\" /E /I /Q >nul

REM Create desktop shortcut
echo Creating desktop shortcut...
set DESKTOP=%USERPROFILE%\Desktop
echo @echo off > "%DESKTOP%\Todoist Assistant.bat"
echo cd /d "%INSTALL_DIR%" >> "%DESKTOP%\Todoist Assistant.bat"
echo start "" "TodoistAssistant.exe" >> "%DESKTOP%\Todoist Assistant.bat"

REM Create start menu shortcut
set STARTMENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs
if not exist "%STARTMENU%\Todoist Assistant" mkdir "%STARTMENU%\Todoist Assistant"
echo @echo off > "%STARTMENU%\Todoist Assistant\Todoist Assistant.bat"
echo cd /d "%INSTALL_DIR%" >> "%STARTMENU%\Todoist Assistant\Todoist Assistant.bat"
echo start "" "TodoistAssistant.exe" >> "%STARTMENU%\Todoist Assistant\Todoist Assistant.bat"

echo @echo off > "%STARTMENU%\Todoist Assistant\Uninstall.bat"
echo echo Uninstalling Todoist Assistant... >> "%STARTMENU%\Todoist Assistant\Uninstall.bat"
echo rmdir /s /q "%INSTALL_DIR%" >> "%STARTMENU%\Todoist Assistant\Uninstall.bat"
echo del "%DESKTOP%\Todoist Assistant.bat" >> "%STARTMENU%\Todoist Assistant\Uninstall.bat"
echo rmdir /s /q "%STARTMENU%\Todoist Assistant" >> "%STARTMENU%\Todoist Assistant\Uninstall.bat"
echo echo Uninstallation complete. >> "%STARTMENU%\Todoist Assistant\Uninstall.bat"
echo pause >> "%STARTMENU%\Todoist Assistant\Uninstall.bat"

echo.
echo ======================================
echo Installation completed successfully!
echo ======================================
echo.
echo You can now run Todoist Assistant by:
echo   1. Double-clicking "Todoist Assistant" on your desktop
echo   2. Finding it in your Start Menu
echo   3. Running: "%INSTALL_DIR%\TodoistAssistant.exe"
echo.
echo On first run, you'll need to configure your Todoist API key.
echo Get your API key from: https://todoist.com/prefs/integrations
echo.
echo Press any key to launch Todoist Assistant now...
pause >nul

cd /d "%INSTALL_DIR%"
start "" "TodoistAssistant.exe"