@echo off
setlocal
rem Stops every container (including the demo UI and API) and shuts down Docker's Linux VM,
rem so the laptop cools down and gets its RAM back. All data stays saved in Docker volumes and data\.
rem Next time: open Docker Desktop, wait for "Engine running", then run 13_start_demo.bat.
cd /d "%~dp0.."
echo Stopping all project containers...
docker compose --profile demo stop
echo Shutting down Docker's Linux VM (frees about 11 GB of RAM)...
wsl --shutdown
echo.
echo Done. You can also quit Docker Desktop from the system tray (right-click the whale, Quit).
timeout /t 10 >nul
