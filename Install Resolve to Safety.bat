@echo off
cd /d "%~dp0"

echo.
echo ======================================
echo   Installing Resolve to Safety
echo ======================================
echo.

py -m venv .venv

call .venv\Scripts\activate.bat

python -m pip install --upgrade pip

pip install -r requirements.txt

playwright install chromium

echo.
echo ======================================
echo   Installation complete!
echo ======================================
echo.
echo You can now use:
echo "Resolve to Safety.bat"
echo.

pause