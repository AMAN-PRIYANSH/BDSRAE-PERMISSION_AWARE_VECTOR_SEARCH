@echo off
setlocal
rem Runs the last steps one after the other: 1M leakage tests, mutation check, finalize results.
cd /d "%~dp0.."
call checks\23_leak_tests_1m.bat
call checks\24_mutation_check.bat
call checks\30_finalize_results.bat
