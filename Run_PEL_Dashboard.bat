@echo off
setlocal
cd /d "%~dp0"

if not exist "assets" mkdir "assets"
if not exist "uploads" mkdir "uploads"
if not exist "processed" mkdir "processed"
if not exist ".streamlit" mkdir ".streamlit"

if exist ".venv\Scripts\python.exe" (
    set "PYEXE=.venv\Scripts\python.exe"
    goto run_app
)

py -3.12 --version >nul 2>nul
if not errorlevel 1 (
    py -3.12 -m venv .venv
    if errorlevel 1 goto setup_failed
    set "PYEXE=.venv\Scripts\python.exe"
    goto install_deps
)

py -3.11 --version >nul 2>nul
if not errorlevel 1 (
    py -3.11 -m venv .venv
    if errorlevel 1 goto setup_failed
    set "PYEXE=.venv\Scripts\python.exe"
    goto install_deps
)

echo Python 3.11 or 3.12 is recommended. Install one, then run this file again.
pause
exit /b 1

:install_deps
"%PYEXE%" -m pip install --upgrade pip
if errorlevel 1 goto setup_failed
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 goto setup_failed

:run_app
"%PYEXE%" -m streamlit run pel_assets_dashboard.py
if errorlevel 1 goto setup_failed
pause
exit /b 0

:setup_failed
echo.
echo Setup or dashboard launch failed. Review the error above.
pause
exit /b 1
