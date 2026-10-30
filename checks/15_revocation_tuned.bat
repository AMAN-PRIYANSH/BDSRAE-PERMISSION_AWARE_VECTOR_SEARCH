@echo off
setlocal
rem Second revocation run with a tuned stream job (4 shuffle partitions instead of Spark's default 200).
rem Also: breaks down the first (default) run, and re-draws the 100k benchmark plots.
rem Output: logs\15_revocation_tuned.txt and results\revocation_*demo100k_tuned*, results\revocation_breakdown_*
cd /d "%~dp0.."
set "LOG=logs\15_revocation_tuned.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Tuned revocation test  %date% %time% =====
echo [1/5] Re-drawing the 100k benchmark plots...
docker compose exec -T app python -m src.pavs.plots /app/results/bench_demo100k.csv demo100k >>"%LOG%" 2>&1
echo [2/5] Breakdown of the first (default, 200 partitions) run...
docker compose exec -T app python -m src.pavs.revocation_breakdown --tag demo100k >>"%LOG%" 2>&1
docker compose exec -T app sh -c "python -c 'import time; print(int(time.time()*1000))' > /app/data/stage/t_tuned.txt"
echo [3/5] Starting the tuned ACL stream job...
docker compose exec -d app sh -c "python -m src.pavs.jobs.acl_stream --trigger 1 --shuffle-partitions 4 --checkpoint /app/data/stage/ckpt_acl_p4 > /app/logs/acl_stream_tuned.txt 2>&1"
timeout /t 75 /nobreak >nul
echo [4/5] Running revocation trials (about 8 minutes)...
docker compose exec -T app python -m src.pavs.revocation_bench --trials 20 --tag demo100k_tuned >>"%LOG%" 2>&1
>>"%LOG%" echo revocation exit code: %errorlevel%
timeout /t 20 /nobreak >nul
docker compose exec -T app pkill -f acl_stream >>"%LOG%" 2>&1
echo [5/5] Breakdown of the tuned run...
docker compose exec -T app python -m src.pavs.revocation_breakdown --since-file /app/data/stage/t_tuned.txt --tag demo100k_tuned >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
