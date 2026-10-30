@echo off
setlocal
rem Re-draws the summary figures and executes notebooks/02_results.ipynb so it is saved with all outputs.
rem Output: logs\30_finalize.txt, results\revocation_comparison.png, notebooks\02_results.ipynb (with outputs)
cd /d "%~dp0.."
set "LOG=logs\30_finalize.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Finalize results  %date% %time% =====
docker compose exec -T app python -m src.pavs.plot_revocation >>"%LOG%" 2>&1
docker compose exec -T app jupyter nbconvert --to notebook --execute --inplace /app/notebooks/02_results.ipynb >>"%LOG%" 2>&1
>>"%LOG%" echo notebook exit code: %errorlevel%
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
