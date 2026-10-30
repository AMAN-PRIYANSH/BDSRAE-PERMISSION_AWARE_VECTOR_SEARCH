@echo off
rem Starts the search API (port 8000) and demo UI (port 8501), then opens the UI.
cd /d "%~dp0.."
docker compose --profile demo up -d
echo Waiting 20 seconds for the UI to start...
timeout /t 20 /nobreak >nul
start "" http://localhost:8501
echo Demo UI: http://localhost:8501    API docs: http://localhost:8000/docs
pause
