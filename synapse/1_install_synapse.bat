@echo off
chcp 65001 >nul
rem Corporate TLS proxy: let Node.js trust the root CA exported from Windows (skipped if the file is absent)
if exist "%USERPROFILE%\.certs\sts_root.pem" set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.certs\sts_root.pem"
rem Шаг 1. Установка Synapse CLI (нужен Node.js 20+; у вас 22).
rem Команда из гайда:  npm install -g @2ndbrainlabs-ai/synapse-cli  ->  synapse --version
node --version
call npm install -g @2ndbrainlabs-ai/synapse-cli
call synapse --version
pause
