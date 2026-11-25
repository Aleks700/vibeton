@echo off
chcp 65001 >nul
rem Corporate TLS proxy: let Node.js trust the root CA exported from Windows (skipped if the file is absent)
if exist "%USERPROFILE%\.certs\sts_root.pem" set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.certs\sts_root.pem"
rem Шаг 2. Инициализация проекта (только для hosted-сборки; для --local не нужно).
rem Ключ API берётся в Synapse console. Команда из гайда:  cd my-project  ->  synapse init
rem Synapse попросит вставить ключ - вставьте его в это окно (в файлы его не пишите).
set SYNAPSE_TELEMETRY=0
cd /d "%~dp0..\app"
call synapse init
pause
