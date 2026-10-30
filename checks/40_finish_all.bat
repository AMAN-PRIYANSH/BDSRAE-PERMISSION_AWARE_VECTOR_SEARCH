@echo off
setlocal
rem Last steps in one go: Milvus 1M re-run with warm-up, 1M leakage tests, mutation check,
rem results notebook, demo recording.
cd /d "%~dp0.."
call checks\27_bench_1m_milvus_rerun.bat
call checks\23_leak_tests_1m.bat
call checks\24_mutation_check.bat
call checks\30_finalize_results.bat
call checks\26_record_demo.bat
