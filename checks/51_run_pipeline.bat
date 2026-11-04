@echo off
setlocal
rem Runs the whole batch pipeline through Airflow and follows it until it ends:
rem   check_services - ingest - index - quality_gate - leak_tests - mutation_check - benchmark - report
rem
rem   51_run_pipeline.bat                       load the 100k demo slice and run everything (about 20 min)
rem   51_run_pipeline.bat --skip-load           keep the current index: checks, tests and benchmark only
rem   51_run_pipeline.bat --prefix corpus1m     the full 1M load (about 45 min, needs the 1M files)
rem
rem Output: results\airflow\pipeline_report_<prefix>.md, results\quality_<prefix>.json,
rem         results\bench_airflow_<prefix>.csv; every task log is in the Airflow UI.
rem NOTE: a load REPLACES the current index (for example the 1M one used in the live demo).
cd /d "%~dp0.."
docker inspect pavs-airflow >nul 2>&1 || (echo Airflow is not running: run 50_start_airflow.bat first & exit /b 1)
echo Triggering pavs_pipeline. Watch it live at http://localhost:8080
docker exec pavs-airflow python /opt/pavs-orchestration/trigger_and_wait.py %*
set "RC=%errorlevel%"
echo.
if "%RC%"=="0" (echo PIPELINE SUCCEEDED. Report: results\airflow\) else (echo PIPELINE FAILED: open the red task in the Airflow UI to see why.)
if not defined PAVS_NO_PAUSE pause
exit /b %RC%
