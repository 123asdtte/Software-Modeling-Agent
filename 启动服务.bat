@echo off
chcp 65001 >nul
title AI 教学智能体平台 - 后端服务
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM 端口自适应：8000 在本机常被 Docker(diet-gateway) 占用，依次回退。
REM 注意：PowerShell 的 exit $true 返回码为 1，故 errorlevel 1 表示"端口被占用"。
REM ---------------------------------------------------------------------------
set "PORT=8000"

powershell -NoProfile -Command "exit ([bool](Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue))"
if errorlevel 1 set "PORT=8100"

powershell -NoProfile -Command "exit ([bool](Get-NetTCPConnection -State Listen -LocalPort 8100 -ErrorAction SilentlyContinue))"
if errorlevel 1 set "PORT=8101"

echo ============================================
echo   服务端口: %PORT%
echo   建模页面: http://127.0.0.1:%PORT%/uml.html
echo   平台首页: http://127.0.0.1:%PORT%/
echo   接口文档: http://127.0.0.1:%PORT%/docs
echo   关闭本窗口即停止服务
echo ============================================
echo.

.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
pause
