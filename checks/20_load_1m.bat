@echo off
setlocal
rem Loads the full 1M corpus: Spark -> Iceberg -> Milvus. Needs Docker with 11 GB (03_set_docker_memory). About 30-60 min.
cd /d "%~dp0.."
set "LOG=logs\20_load_1m.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Load 1M  %date% %time% =====
docker compose exec -T app python -m src.smoke.wait_for >>"%LOG%" 2>&1
echo [1/2] Spark: 1M papers -^> Iceberg...
docker compose exec -T app python -m src.pavs.jobs.ingest --prefix corpus --replace >>"%LOG%" 2>&1
>>"%LOG%" echo ingest exit code: %errorlevel%
echo [2/2] Spark: Iceberg -^> Milvus (both collections)...
docker compose exec -T app python -m src.pavs.jobs.index >>"%LOG%" 2>&1
>>"%LOG%" echo index exit code: %errorlevel%
docker stats --no-stream --format "{{.Name}}  mem={{.MemUsage}}" >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
