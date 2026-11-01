@echo off
setlocal
rem Connects this local repo to GitHub (does NOT push anything). Output: logs\91_connect_github.txt
cd /d "%~dp0.."
set "LOG=logs\91_connect_github.txt"
> "%LOG%" echo ===== Connect GitHub remote  %date% %time% =====
git remote remove origin >nul 2>&1
git remote add origin https://github.com/AMAN-PRIYANSH/BDSRAE-PERMISSION_AWARE_VECTOR_SEARCH.git >>"%LOG%" 2>&1
git branch -M main >>"%LOG%" 2>&1
git remote -v >>"%LOG%" 2>&1
git log --format="%%h %%an <%%ae> %%s" -3 >>"%LOG%" 2>&1
>>"%LOG%" echo ===== DONE =====
echo Connected to GitHub (nothing was pushed). See %LOG%
timeout /t 5 >nul
