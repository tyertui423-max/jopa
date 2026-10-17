@echo off
title DanyaClient Web Server
cd /d "%~dp0"

echo ===================================================
echo           DanyaClient Web Portal
echo ===================================================
echo.
echo Launching server at http://localhost:8000 ...
echo Press Ctrl + C to stop the server.
echo.

:: Open browser
start "" http://localhost:8000

:: Start FastAPI server with live reload
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server exited with error code %ERRORLEVEL%.
    pause
)
