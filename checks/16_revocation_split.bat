@echo off
setlocal
rem Third revocation run: the stream job is split into a fast path (Kafka -> Milvus, every 0.2 s)
rem and a separate slow path (Kafka -> Iceberg MERGE + audit table, every 1 s).
rem Output: logs\16_revocation_split.txt and results\revocation_*demo100k_split*
cd /d "%~dp0.."
set "LOG=logs\16_revocation_split.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Split-path revocation test  %date% %time% =====
docker compose exec -T app sh -c "python -c 'import time; print(int(time.time()*1000))' > /app/data/stage/t_split.txt"
echo [1/3] Starting the split ACL stream job...
docker compose exec -d app sh -c "python -m src.pavs.jobs.acl_stream --split --fast-trigger 0.2 --trigger 1 --shuffle-partitions 4 --checkpoint /app/data/stage/ckpt_acl_split > /app/logs/acl_stream_split.txt 2>&1"
timeout /t 75 /nobreak >nul
echo [2/3] Running revocation trials (about 6 minutes)...
docker compose exec -T app python -m src.pavs.revocation_bench --trials 20 --tag demo100k_split >>"%LOG%" 2>&1
>>"%LOG%" echo revocation exit code: %errorlevel%
timeout /t 20 /nobreak >nul
docker compose exec -T app pkill -f acl_stream >>"%LOG%" 2>&1
echo [3/3] Breakdown of the split run...
docker compose exec -T app python -m src.pavs.revocation_breakdown --since-file /app/data/stage/t_split.txt --milvus-log /app/logs/acl_milvus_applied.jsonl --tag demo100k_split >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
