@echo off
setlocal
rem ------------------------------------------------------------
rem  STEP 1: download images, build the app image, start the stack
rem  First run downloads about 5-6 GB and can take 15-30 minutes.
rem  Output goes to logs\01_build_and_start.txt
rem ------------------------------------------------------------
cd /d "%~dp0.."
if not exist logs mkdir logs
set "LOG=logs\01_build_and_start.txt"
set BUILDKIT_PROGRESS=plain

docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running.
  echo Open Docker Desktop, wait until it says "Engine running", then double-click this file again.
  pause
  exit /b 1
)

> "%LOG%" echo ===== Build and start  %date% %time% =====

echo [1/4] Downloading Milvus, etcd, MinIO, Kafka, Postgres images...
>>"%LOG%" echo.
>>"%LOG%" echo [1/4] pull
docker compose pull etcd minio standalone kafka postgres >>"%LOG%" 2>&1
>>"%LOG%" echo pull exit code: %errorlevel%

echo [2/4] Building the app image (Python, Java, Spark, PyTorch CPU)...
>>"%LOG%" echo.
>>"%LOG%" echo [2/4] build
docker compose build app >>"%LOG%" 2>&1
>>"%LOG%" echo build exit code: %errorlevel%

echo [3/4] Starting all services...
>>"%LOG%" echo.
>>"%LOG%" echo [3/4] up
docker compose up -d >>"%LOG%" 2>&1
>>"%LOG%" echo up exit code: %errorlevel%

echo [4/4] Recording status...
>>"%LOG%" echo.
>>"%LOG%" echo [4/4] status
docker compose ps -a >>"%LOG%" 2>&1
docker image ls >>"%LOG%" 2>&1
docker compose exec -T app pip freeze > "logs\pip-freeze.txt" 2>&1
docker compose exec -T app java -version >>"%LOG%" 2>&1
docker compose exec -T app python --version >>"%LOG%" 2>&1

>>"%LOG%" echo.
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo.
echo Finished. Results saved in %LOG%
echo You can close this window now.
pause
