@echo off
setlocal
rem Pushes your commits to GitHub. Run this YOURSELF. The first time, a browser window may open
rem asking you to sign in to GitHub: sign in as AMAN-PRIYANSH and approve.
cd /d "%~dp0.."
echo Pushing to https://github.com/AMAN-PRIYANSH/BDSRAE-PERMISSION_AWARE_VECTOR_SEARCH ...
git push -u origin main
echo.
echo If it says "main -> main", it worked. Refresh the GitHub page to see your files.
pause
