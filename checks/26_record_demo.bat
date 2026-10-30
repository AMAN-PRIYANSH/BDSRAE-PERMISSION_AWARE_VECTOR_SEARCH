@echo off
setlocal
rem Records the live UI demo as a silent video (headless browser inside the app container, real Milvus index).
rem Output: logs\26_record_demo.txt, results\demo\ui_demo.webm, results\demo\ui_demo_scenes.json
cd /d "%~dp0.."
set "LOG=logs\26_record_demo.txt"
> "%LOG%" echo ===== Record UI demo  %date% %time% =====
docker compose --profile demo up -d ui api >>"%LOG%" 2>&1
echo [1/3] Installing a headless browser in the app container (first time only, about 2-3 minutes)...
docker compose exec -T app sh -c "pip install -q playwright==1.48.0 && python -m playwright install --with-deps chromium" >>"%LOG%" 2>&1
>>"%LOG%" echo playwright install exit code: %errorlevel%
echo [2/3] Waiting for the UI to start...
timeout /t 20 /nobreak >nul
echo [3/3] Recording (about 1-2 minutes)...
docker compose exec -T app python -m src.demo.record_demo --url http://ui:8501 >>"%LOG%" 2>&1
>>"%LOG%" echo record exit code: %errorlevel%
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
