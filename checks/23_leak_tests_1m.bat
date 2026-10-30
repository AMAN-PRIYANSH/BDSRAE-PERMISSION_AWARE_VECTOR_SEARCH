@echo off
setlocal
rem Runs the leakage test suite against the 1M index. Output: logs\23_leak_tests_1m.txt, results\leak_tests_junit_1m.xml
cd /d "%~dp0.."
set "LOG=logs\23_leak_tests_1m.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Leakage tests on 1M index  %date% %time% =====
echo Running leakage tests on the 1M index (a few minutes)...
docker compose exec -T app python -m pytest tests/test_leakage.py -q -p no:cacheprovider --junitxml=results/leak_tests_junit_1m.xml >>"%LOG%" 2>&1
>>"%LOG%" echo pytest exit code: %errorlevel%
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
