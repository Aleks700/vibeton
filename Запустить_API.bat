@echo off
chcp 65001 >nul
rem GeoVision Catalog API (безопасная версия для хакатона): http://127.0.0.1:9100/docs
rem База - тот же контейнер geovision_db, но через роль только на чтение (app\.env).
cd /d "%~dp0"
if exist "%~dp0..\GeoVision\backend\Запустить_базу.bat" call "%~dp0..\GeoVision\backend\Запустить_базу.bat"
set PY=%~dp0app\.venv\Scripts\python.exe
if not exist "%PY%" set PY=%~dp0..\catalogFastapi\.venv\Scripts\python.exe
if not exist "%PY%" set PY=python
if not exist "%~dp0app\.env" (
  echo Нет app\.env - скопируйте app\.env.example в app\.env и впишите DATABASE_URL.
  pause
  exit /b 1
)
cd /d "%~dp0app"
echo API: http://127.0.0.1:9100/docs   (остановить - закрыть окно)
"%PY%" -m uvicorn main:app --host 127.0.0.1 --port 9100
pause
