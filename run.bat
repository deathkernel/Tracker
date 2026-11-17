@echo off
title UPSC 2027 Tracker
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py"
) else (
    set "PYTHON=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto error
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto error
pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Starting UPSC Tracker...
echo Open http://127.0.0.1:8000 in your browser.
echo Keep this window open while using the tracker.
start "" http://127.0.0.1:8000
python -m uvicorn server:app --host 127.0.0.1 --port 8000
goto end

:error
echo.
echo Setup failed. Read the error above before trying again.
pause

:end
