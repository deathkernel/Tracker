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
python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto error

if not defined TRACKER_HOST set "TRACKER_HOST=127.0.0.1"
echo.
echo Starting UPSC Tracker on %TRACKER_HOST%...
echo Open http://127.0.0.1:8000 on this PC.
if "%TRACKER_HOST%"=="127.0.0.1" echo Network access is disabled by default for safety.
if not "%TRACKER_HOST%"=="127.0.0.1" echo Network access is enabled. Use only on a trusted private network.
echo Keep this window open while using the tracker.
start "" http://127.0.0.1:8000
python -m uvicorn server:app --host "%TRACKER_HOST%" --port 8000
goto end

:error
echo.
echo Setup failed. Read the error above before trying again.
pause

:end
