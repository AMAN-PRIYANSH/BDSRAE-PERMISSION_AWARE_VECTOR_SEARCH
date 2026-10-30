@echo off
setlocal
rem Mutation check: runs the leakage suite with the permission filter deliberately disabled.
rem Tests on the filter method MUST fail here (that proves the suite can catch a leak).
rem Output: logs\24_mutation_check.txt, results\mutation_check_junit.xml
cd /d "%~dp0.."
set "LOG=logs\24_mutation_check.txt"
docker compose up -d >nul 2>&1
> "%LOG%" echo ===== Mutation check (filter disabled on purpose, failures EXPECTED)  %date% %time% =====
echo Running leakage tests with the filter switched off on purpose...
docker compose exec -T -e PAVS_MUTATION=no_filter -e PAVS_LEAK_QUERIES=50 app python -m pytest tests/test_leakage.py -q -p no:cacheprovider --junitxml=results/mutation_check_junit.xml >>"%LOG%" 2>&1
>>"%LOG%" echo pytest exit code: %errorlevel% (non-zero is the expected result here)
>>"%LOG%" echo ===== DONE  %date% %time% =====
echo Finished. Results in %LOG%
timeout /t 5 >nul
