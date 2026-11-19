@echo off
setlocal
title UPSC 2027 Tracker
cd /d "%~dp0"

rem Keep the existing Python environment and dependency setup.
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

rem Configure Tracker to prefer the user's installed local Qwen model.
if not defined TRACKER_OLLAMA_MODEL set "TRACKER_OLLAMA_MODEL=qwen3.5:9b"

echo.
echo Checking Ollama...
set "OLLAMA_EXE="
for /f "delims=" %%I in ('where ollama 2^>nul') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%I"

if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE (
    echo Ollama was not found. Install it from https://ollama.com/download/windows
    goto ollama_error
)

rem Reuse the existing Ollama server; start one only when the API is unavailable.
curl.exe --silent --fail http://127.0.0.1:11434/api/tags >nul 2>nul
if errorlevel 1 (
    echo Starting local Ollama server...
    start "Tracker Ollama Server" /min "%OLLAMA_EXE%" serve
)

set "OLLAMA_READY="
for /l %%N in (1,1,30) do (
    curl.exe --silent --fail http://127.0.0.1:11434/api/tags >nul 2>nul
    if not errorlevel 1 set "OLLAMA_READY=1"
    if defined OLLAMA_READY goto ollama_ready
    timeout /t 2 /nobreak >nul
)

echo Ollama API did not become ready within 60 seconds.
goto ollama_error

:ollama_ready
echo Ollama API is ready.

rem Do not silently download a multi-gigabyte model during normal startup.
"%OLLAMA_EXE%" list | findstr /i /c:"%TRACKER_OLLAMA_MODEL%" >nul
if errorlevel 1 (
    echo Required model %TRACKER_OLLAMA_MODEL% is not installed.
    echo Install it once with: ollama pull %TRACKER_OLLAMA_MODEL%
    goto ollama_error
)

echo Loading %TRACKER_OLLAMA_MODEL% into Ollama...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$body = @{ model = $env:TRACKER_OLLAMA_MODEL; prompt = ' '; stream = $false; keep_alive = '30m'; options = @{ num_predict = 1 } } | ConvertTo-Json -Depth 4; try { Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/generate' -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 900 | Out-Null; exit 0 } catch { Write-Error $_; exit 1 }"
if errorlevel 1 goto ollama_error
echo Qwen is loaded and ready.

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

:ollama_error
echo.
echo Ollama setup failed. Tracker was not started because its configured local AI model is unavailable.
echo Check Ollama installation, server status and model name, then run this file again.
pause
goto end

:error
echo.
echo Setup failed. Read the error above before trying again.
pause

:end
endlocal
