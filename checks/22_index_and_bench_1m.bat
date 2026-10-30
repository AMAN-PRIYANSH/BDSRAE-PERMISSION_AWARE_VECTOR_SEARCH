@echo off
setlocal
rem Retry of the 1M Milvus load (reuses the parquet files Spark already staged) and then the 1M benchmark.
rem Kafka is paused during the benchmark to leave more memory for Milvus + FAISS.
rem Output: logs\22_index_bench_1m.txt and results\bench_corpus1m.csv + plots
cd /d "%~dp0.."
set "LOG=logs\22_index_bench_1m.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Index + benchmark 1M  %date% %time% =====
echo [1/3] Loading 1M documents into Milvus (about 10 minutes)...
docker compose exec -T app python -m src.pavs.jobs.index --skip-stage >>"%LOG%" 2>&1
>>"%LOG%" echo index exit code: %errorlevel%
docker stats --no-stream --format "{{.Name}}  mem={{.MemUsage}}" >>"%LOG%" 2>&1
echo [2/3] Benchmark on 1M documents (about 20-30 minutes)...
docker compose stop kafka >>"%LOG%" 2>&1
docker compose exec -T app python -m src.pavs.bench --prefix corpus --queries 500 --tag corpus1m >>"%LOG%" 2>&1
>>"%LOG%" echo bench exit code: %errorlevel%
docker stats --no-stream --format "{{.Name}}  mem={{.MemUsage}}" >>"%LOG%" 2>&1
echo [3/3] Restarting Kafka...
docker compose start kafka >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
