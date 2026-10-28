@echo off
setlocal
rem ------------------------------------------------------------
rem  STEP 2: run all smoke tests inside the app container
rem  Takes about 5-10 minutes. Output goes to logs\02_smoke_tests.txt
rem ------------------------------------------------------------
cd /d "%~dp0.."
if not exist logs mkdir logs
set "LOG=logs\02_smoke_tests.txt"

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running. Open it, wait for "Engine running", then try again.
  pause
  exit /b 1
)

> "%LOG%" echo ===== Smoke tests  %date% %time% =====
docker compose up -d >>"%LOG%" 2>&1

call :run "waiting for services" src.smoke.wait_for
call :run "Milvus"               src.smoke.test_milvus
call :run "FAISS"                src.smoke.test_faiss
call :run "Spark + Iceberg"      src.smoke.test_lakehouse
call :run "Kafka + Streaming"    src.smoke.test_stream
call :run "Embedding speed"      src.smoke.test_embed

echo Recording memory use...
>>"%LOG%" echo.
>>"%LOG%" echo ===== Memory use per container =====
docker stats --no-stream --format "{{.Name}}  mem={{.MemUsage}}  cpu={{.CPUPerc}}" >>"%LOG%" 2>&1
docker info --format "DockerVM_RAM_bytes={{.MemTotal}}" >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo.
echo Finished. Results saved in %LOG%
echo You can close this window now.
pause
exit /b 0

:run
echo Running: %~1 ...
>>"%LOG%" echo.
>>"%LOG%" echo ===== %~1  (%time%) =====
docker compose exec -T app python -m %2 >>"%LOG%" 2>&1
>>"%LOG%" echo exit code: %errorlevel%
exit /b 0
