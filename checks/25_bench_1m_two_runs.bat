@echo off
setlocal
rem 1M benchmark in two runs so nothing swaps to disk (swapping makes latency numbers meaningless):
rem   run 1: Milvus methods (FAISS HNSW not built)   run 2: FAISS methods (Milvus collections released)
rem Output: logs\25_bench_1m.txt, results\bench_corpus1m.csv + plots
cd /d "%~dp0.."
set "LOG=logs\25_bench_1m.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Benchmark 1M in two runs  %date% %time% =====
docker compose exec -T app pkill -f src.pavs.bench >nul 2>&1
docker compose stop kafka >>"%LOG%" 2>&1
echo [1/3] Milvus methods on 1M documents...
docker compose exec -T app python -m src.pavs.bench --prefix corpus --queries 500 --tag corpus1m_milvus --skip-faiss --methods milvus_filter,milvus_partition >>"%LOG%" 2>&1
>>"%LOG%" echo run 1 exit code: %errorlevel%
docker stats --no-stream --format "{{.Name}}  mem={{.MemUsage}}" >>"%LOG%" 2>&1
echo [2/3] FAISS methods on 1M documents (builds FAISS HNSW, about 12 minutes)...
docker compose exec -T app python -m src.pavs.bench --prefix corpus --queries 500 --tag corpus1m_faiss --methods faiss_prefilter,faiss_postfilter,faiss_post_10x >>"%LOG%" 2>&1
>>"%LOG%" echo run 2 exit code: %errorlevel%
docker stats --no-stream --format "{{.Name}}  mem={{.MemUsage}}" >>"%LOG%" 2>&1
echo [3/3] Merging...
docker compose exec -T app python -m src.pavs.merge_bench corpus1m /app/results/bench_corpus1m_milvus.csv /app/results/bench_corpus1m_faiss.csv >>"%LOG%" 2>&1
docker compose start kafka >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
