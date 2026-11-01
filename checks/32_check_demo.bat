@echo off
setlocal
rem Checks that the demo is up: containers running, UI and API answering, and runs 3 example searches
rem through the API. Output: logs\32_check_demo.txt
cd /d "%~dp0.."
set "LOG=logs\32_check_demo.txt"
> "%LOG%" echo ===== Demo check  %date% %time% =====
docker compose --profile demo ps --format "{{.Name}}  {{.Status}}" >>"%LOG%" 2>&1
>>"%LOG%" echo [UI health]
curl -s http://localhost:8501/_stcore/health >>"%LOG%" 2>&1
>>"%LOG%" echo.
>>"%LOG%" echo [API health]
curl -s http://localhost:8000/health >>"%LOG%" 2>&1
>>"%LOG%" echo.
>>"%LOG%" echo [Example 1: intern, general query]
docker compose exec -T app python -m src.demo.examples >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Done. See %LOG%
timeout /t 5 >nul
