@echo off
setlocal
rem Re-runs only the Milvus part of the 1M benchmark with a warm-up (the first run measured cold caches
rem at the 100% point), then merges it with the FAISS part again.
rem Output: logs\27_bench_1m_milvus_rerun.txt, results\bench_corpus1m.csv + plots
cd /d "%~dp0.."
set "LOG=logs\27_bench_1m_milvus_rerun.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Benchmark 1M, Milvus part again with warm-up  %date% %time% =====
docker compose exec -T app python -m src.pavs.bench --prefix corpus --queries 500 --tag corpus1m_milvus --skip-faiss --methods milvus_filter,milvus_partition >>"%LOG%" 2>&1
>>"%LOG%" echo bench exit code: %errorlevel%
docker compose exec -T app python -m src.pavs.merge_bench corpus1m /app/results/bench_corpus1m_milvus.csv /app/results/bench_corpus1m_faiss.csv >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
