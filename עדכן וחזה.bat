@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   חיזוי מונדיאל 2026 - מעדכן נתונים ומריץ...
echo ============================================
python src\run.py
if errorlevel 1 (
  echo.
  echo שגיאה. ודא שיש חיבור לאינטרנט ושפייתון מותקן.
  pause
  exit /b 1
)
start "" "output\index.html"
