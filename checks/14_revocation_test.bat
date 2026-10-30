@echo off
setlocal
rem Revocation leak-window test: starts the Kafka->Spark ACL stream, relabels documents, times how long they stay visible.
rem Output: logs\14_revocation.txt and results\revocation_*
cd /d "%~dp0.."
set "LOG=logs\14_revocation.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Revocation test  %date% %time% =====
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic acl-relabel --partitions 3 --replication-factor 1 >>"%LOG%" 2>&1
echo [1/3] Starting the ACL stream job...
docker compose exec -d app sh -c "python -m src.pavs.jobs.acl_stream --trigger 1 > /app/logs/acl_stream.txt 2>&1"
timeout /t 75 /nobreak >nul
echo [2/3] Running revocation trials (about 10 minutes)...
docker compose exec -T app python -m src.pavs.revocation_bench --trials 20 >>"%LOG%" 2>&1
>>"%LOG%" echo revocation exit code: %errorlevel%
timeout /t 20 /nobreak >nul
echo [3/3] Stopping the stream job...
docker compose exec -T app pkill -f acl_stream >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
