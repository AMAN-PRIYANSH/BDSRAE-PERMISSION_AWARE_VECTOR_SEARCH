@echo off
setlocal
rem Commits all project changes as YOU (your git name/email). Message comes from checks\commit_message.txt
cd /d "%~dp0.."
set "LOG=logs\90_git_commit.txt"
> "%LOG%" echo ===== git commit  %date% %time% =====
git rm -r --cached -q --ignore-unmatch logs >>"%LOG%" 2>&1
git add -A >>"%LOG%" 2>&1
git commit -F checks\commit_message.txt >>"%LOG%" 2>&1
>>"%LOG%" echo commit exit code: %errorlevel%
git log --oneline -5 >>"%LOG%" 2>&1
git status --short >>"%LOG%" 2>&1
echo Done. See %LOG%
timeout /t 3 >nul
