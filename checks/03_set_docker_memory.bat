@echo off
setlocal
rem ------------------------------------------------------------
rem  Gives Docker (WSL2) 11 GB RAM, 12 CPU cores and 8 GB swap.
rem  Run ONLY after 01 and 02 have finished: it restarts WSL,
rem  which stops Docker for a moment.
rem ------------------------------------------------------------
set "CFG=%USERPROFILE%\.wslconfig"
if exist "%CFG%" copy /y "%CFG%" "%CFG%.backup" >nul

> "%CFG%" echo [wsl2]
>>"%CFG%" echo memory=11GB
>>"%CFG%" echo processors=12
>>"%CFG%" echo swap=8GB

echo Written %CFG%:
type "%CFG%"
echo.
echo Stopping Docker Desktop and WSL so the new limit applies...
taskkill /im "Docker Desktop.exe" /f >nul 2>&1
wsl --shutdown
echo.
echo Done. Now open Docker Desktop again and wait for "Engine running".
pause
