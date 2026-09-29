@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Python 3 not found. Install Python and enable the py launcher.
  exit /b 1
)
py -3 -X utf8 "%~dp0generate.py" %*
exit /b %ERRORLEVEL%
