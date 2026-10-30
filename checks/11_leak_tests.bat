@echo off
setlocal
rem Runs the leakage test suite against the live index. Output: logs\11_leak_tests.txt
cd /d "%~dp0.."
set "LOG=logs\11_leak_tests.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Leakage tests  %date% %time% =====
echo Running leakage tests (a few minutes)...
docker compose exec -T app python -m pytest tests/test_leakage.py -q -p no:cacheprovider --junitxml=results/leak_tests_junit.xml >>"%LOG%" 2>&1
>>"%LOG%" echo pytest exit code: %errorlevel%
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
pause
