@echo off
chcp 65001 >nul
rem Corporate TLS proxy: let Node.js trust the root CA exported from Windows (skipped if the file is absent)
if exist "%USERPROFILE%\.certs\sts_root.pem" set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.certs\sts_root.pem"
rem Шаг 3 (вариант B, рекомендуется для кода КГС). Локальная сборка своей моделью:
rem код никуда не уходит в Synapse, квоты нет, synapse init не нужен.
rem Результат - файл app\synapse_auto_server.py (Python MCP-сервер), его и подключаем к агенту.
rem Команды из гайда:  export ANTHROPIC_API_KEY=sk-ant-...  ->  cd my-project  ->  synapse build --local
rem                    synapse model set <provider>   (anthropic по умолчанию)
rem Ключ задайте ЗАРАНЕЕ в переменной окружения (не в этом файле):
rem    setx ANTHROPIC_API_KEY "sk-ant-..."   и откройте новое окно
set SYNAPSE_TELEMETRY=0
if "%ANTHROPIC_API_KEY%"=="" (
  echo Не задан ANTHROPIC_API_KEY. Выполните: setx ANTHROPIC_API_KEY "ваш-ключ" и запустите этот файл в новом окне.
  pause
  exit /b 1
)
cd /d "%~dp0..\app"
call synapse model set anthropic
call synapse build --local --auto --endpoints "GET /catalog,POST /catalog/area,GET /db/scenes,GET /db/scenes/{code},GET /db/status"
if errorlevel 1 (
  echo.
  echo Если комбинация флагов не принята - запустите просто "synapse build --local" и выберите эти 5 маршрутов в меню.
)
pause
