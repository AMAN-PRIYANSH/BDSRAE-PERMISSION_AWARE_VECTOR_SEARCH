@echo off
setlocal
rem Latency/recall benchmark on the 100k index. Output: logs\12_benchmark.txt and results\
cd /d "%~dp0.."
set "LOG=logs\12_benchmark.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Benchmark demo100k  %date% %time% =====
echo Running benchmark (about 10-20 minutes)...
docker compose exec -T app python -m src.pavs.bench --prefix demo100k --queries 500 >>"%LOG%" 2>&1
>>"%LOG%" echo bench exit code: %errorlevel%
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
pause
