@echo off
chcp 65001 >nul
rem Corporate TLS proxy: let Node.js trust the root CA exported from Windows (skipped if the file is absent)
if exist "%USERPROFILE%\.certs\sts_root.pem" set "NODE_EXTRA_CA_CERTS=%USERPROFILE%\.certs\sts_root.pem"
rem Шаг 3 (вариант A, hosted). Auto-режим: Synapse находит HTTP-маршруты FastAPI и делает из них MCP-инструменты.
rem Открываем агенту только 5 маршрутов на чтение (почему - README.md, "Endpoint selection").
rem В hosted-режиме в Synapse уходят имена маршрутов и docstring (код этой копии без секретов).
rem Команда из гайда:  synapse build --auto --endpoints "GET /patients,POST /patients"
set SYNAPSE_TELEMETRY=0
cd /d "%~dp0..\app"
call synapse build --auto --endpoints "GET /catalog,POST /catalog/area,GET /db/scenes,GET /db/scenes/{code},GET /db/status"
echo.
echo Скопируйте JSON-фрагмент, который напечатал Synapse, в конфиг MCP-клиента (см. ИНСТРУКЦИЯ.md, шаг 6).
pause
