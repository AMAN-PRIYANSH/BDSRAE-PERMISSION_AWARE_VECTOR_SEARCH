@echo off
setlocal
rem Latency/recall benchmark on the 1M index. Output: logs\21_benchmark_1m.txt and results\
cd /d "%~dp0.."
set "LOG=logs\21_benchmark_1m.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Benchmark 1M  %date% %time% =====
docker compose exec -T app python -m src.pavs.bench --prefix corpus --queries 500 --tag corpus1m >>"%LOG%" 2>&1
>>"%LOG%" echo bench exit code: %errorlevel%
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
