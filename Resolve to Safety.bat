@echo off
cd /d "%~dp0"

call .venv\Scripts\activate.bat

start "" http://localhost:8501

python -m streamlit run shift_report_web_app.py --server.headless=false

pause