@echo off
chcp 65001 >nul
rem Corporate TLS proxy: let Node.js trust the root CA exported from Windows (skipped if the file is absent)
if exist "%USERPROFILE%\.certs\sts_root.pem" set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.certs\sts_root.pem"
rem Пересборка после изменений кода: Synapse пересканирует только изменённые файлы, MCP-сервер остаётся тем же
rem (конфиг клиента менять не нужно). Команда из гайда:  synapse build --discover
rem Прервали сборку - продолжить:  synapse build --resume
rem Второй сервер вместо обновления:  synapse build --new   (выбрать сервер: --server-name <name>)
set SYNAPSE_TELEMETRY=0
cd /d "%~dp0..\app"
call synapse build --discover
pause
