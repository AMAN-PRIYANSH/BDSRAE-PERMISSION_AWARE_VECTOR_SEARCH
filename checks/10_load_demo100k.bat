@echo off
setlocal
rem Loads the 100k demo slice: files in data\kaggle -> Iceberg (Spark) -> Milvus.
rem Output: logs\10_load_demo100k.txt
cd /d "%~dp0.."
set "LOG=logs\10_load_demo100k.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Load demo100k  %date% %time% =====
echo [1/3] Waiting for services...
docker compose exec -T app python -m src.smoke.wait_for >>"%LOG%" 2>&1
echo [2/3] Spark: files -^> Iceberg lakehouse...
docker compose exec -T app python -m src.pavs.jobs.ingest --prefix demo100k --replace >>"%LOG%" 2>&1
>>"%LOG%" echo ingest exit code: %errorlevel%
echo [3/3] Spark: Iceberg -^> Milvus index...
docker compose exec -T app python -m src.pavs.jobs.index >>"%LOG%" 2>&1
>>"%LOG%" echo index exit code: %errorlevel%
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
pause
