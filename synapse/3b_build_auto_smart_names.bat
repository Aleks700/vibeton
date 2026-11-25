@echo off
chcp 65001 >nul
rem Corporate TLS proxy: let Node.js trust the root CA exported from Windows (skipped if the file is absent)
if exist "%USERPROFILE%\.certs\sts_root.pem" set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.certs\sts_root.pem"
rem Шаг 3 (вариант A+, hosted). То же, что 3_build_auto_hosted, плюс --smart-names:
rem Synapse читает обработчики и README и даёт инструментам понятные имена и описания.
rem Внимание: при --smart-names в Synapse уходит и код функций (эта копия - без секретов).
rem Команда из гайда:  synapse build --smart-names
set SYNAPSE_TELEMETRY=0
cd /d "%~dp0..\app"
call synapse build --auto --smart-names --endpoints "GET /catalog,POST /catalog/area,GET /db/scenes,GET /db/scenes/{code},GET /db/status"
pause
