@echo off
rem Stops all containers to free RAM. Data is kept (Docker volumes are not deleted).
cd /d "%~dp0.."
docker compose stop
echo.
echo All services stopped. Your data is kept.
pause
