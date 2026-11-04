@echo off
setlocal
rem Starts the stack plus Airflow (the "orchestration" profile).
rem Airflow UI: http://localhost:8080   login: admin / admin   (local use only)
rem First time only: downloads the Airflow image (about 1 GB).
cd /d "%~dp0.."
if not exist logs\airflow mkdir logs\airflow
echo Starting the services and Airflow...
docker compose --profile orchestration up -d
echo Waiting for Airflow to be ready (1-3 minutes)...
set /a tries=0
:wait
set /a tries+=1
for /f %%S in ('docker inspect -f "{{.State.Health.Status}}" pavs-airflow 2^>nul') do set "STATUS=%%S"
if /i "%STATUS%"=="healthy" goto ready
if %tries% geq 60 goto fail
ping -n 6 127.0.0.1 >nul
goto wait
:ready
echo.
echo Airflow is ready: http://localhost:8080   (login admin / admin)
echo Next: run 51_run_pipeline.bat, or press "Trigger" on pavs_pipeline in the UI.
if not defined PAVS_NO_PAUSE start "" http://localhost:8080
if not defined PAVS_NO_PAUSE pause
exit /b 0
:fail
echo Airflow did not become ready. Last log lines:
docker logs --tail 40 pavs-airflow
if not defined PAVS_NO_PAUSE pause
exit /b 1
