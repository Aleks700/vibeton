@echo off
chcp 65001 >nul
rem Corporate TLS proxy: let Node.js trust the root CA exported from Windows (skipped if the file is absent)
if exist "%USERPROFILE%\.certs\sts_root.pem" set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.certs\sts_root.pem"
rem Состояние проекта, квота, какой ключ и модель используются. Команды из гайда:
rem   synapse info    - состояние проекта и остаток квоты
rem   synapse config  - какой API-ключ используется и откуда он взят
rem   synapse model   - какая модель/провайдер будет у сборки и откуда ключ
set SYNAPSE_TELEMETRY=0
cd /d "%~dp0..\app"
call synapse info
echo.
call synapse config
echo.
call synapse model
pause
