@echo off
setlocal
rem ------------------------------------------------------------
rem  STEP 0: check this laptop + create the local git repo
rem  Just double-click. Output goes to logs\00_check_machine.txt
rem ------------------------------------------------------------
cd /d "%~dp0.."
if not exist logs mkdir logs
set "LOG=logs\00_check_machine.txt"
echo Checking your machine, please wait...

> "%LOG%" echo ===== Machine check  %date% %time% =====

>>"%LOG%" echo.
>>"%LOG%" echo [Windows: RAM, CPU, GPU, OS]
powershell -NoProfile -Command "$cs=Get-CimInstance Win32_ComputerSystem; 'TotalRAM_GB=' + [math]::Round($cs.TotalPhysicalMemory/1GB,1); 'CPU=' + (Get-CimInstance Win32_Processor).Name; 'GPU=' + ((Get-CimInstance Win32_VideoController).Name -join ' | '); 'OS=' + (Get-CimInstance Win32_OperatingSystem).Caption" >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo [Disk free on C: in GB]
powershell -NoProfile -Command "[math]::Round((Get-PSDrive C).Free/1GB,1)" >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo [WSL]
set WSL_UTF8=1
wsl --version >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo [.wslconfig]
if exist "%USERPROFILE%\.wslconfig" (type "%USERPROFILE%\.wslconfig" >>"%LOG%") else (>>"%LOG%" echo no .wslconfig file)

>>"%LOG%" echo.
>>"%LOG%" echo [Docker]
docker version --format "client={{.Client.Version}} server={{.Server.Version}}" >>"%LOG%" 2>&1
docker info --format "DockerVM_RAM_bytes={{.MemTotal}} DockerVM_CPUs={{.NCPU}} OS={{.OperatingSystem}}" >>"%LOG%" 2>&1
docker compose version >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo [Git]
git --version >>"%LOG%" 2>&1
>>"%LOG%" echo user.name:
git config --global user.name >>"%LOG%" 2>&1
>>"%LOG%" echo user.email:
git config --global user.email >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo [Local git repo]
if exist ".git" (
  >>"%LOG%" echo repo already exists
) else (
  git init -b main >>"%LOG%" 2>&1
  git add -A >>"%LOG%" 2>&1
  git commit -m "Project scaffold: compose stack, app image, smoke tests" >>"%LOG%" 2>&1
)
git log --oneline -3 >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo ===== DONE =====
echo.
echo Finished. Results saved in %LOG%
echo You can close this window now.
pause
