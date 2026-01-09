@echo off
setlocal EnableExtensions

echo [webui] XHS Cyber UI 一键启动

:: Ensure working directory is the script directory
pushd "%~dp0"

set HOST=127.0.0.1
set PORT=8000
if not "%~1"=="" set PORT=%~1

echo [webui] HOST=%HOST% PORT=%PORT%

:: Try to free the port if occupied
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr LISTENING') do (
    echo [webui] 端口 %PORT% 被 PID %%p 占用，尝试结束...
    taskkill /PID %%p /F >nul 2>&1
)

:: Activate venv if exists
if exist .venv\Scripts\activate.bat (
    echo [webui] 激活虚拟环境 .venv ...
    call .venv\Scripts\activate.bat
) else (
    echo [webui] 未找到 .venv，使用系统 python
)

:: Quick sanity check: can we import the app?
python -c "import sys; sys.path.insert(0, '.'); import web_ui" >nul 2>&1
if %errorlevel% neq 0 (
    echo [webui] ❌ 无法导入 web_ui:app，请检查依赖或文件是否存在。
    echo [webui]    建议先运行: pip install -r requirements.txt
    pause
    popd
    exit /b 1
)

echo [webui] 启动后端服务 (uvicorn) ...

:: Open browser (robust): use PowerShell Start-Process to avoid CMD quoting issues
set "URL=http://%HOST%:%PORT%/"
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1; Start-Process '%URL%'"

python -m uvicorn web_ui:app --host %HOST% --port %PORT%

if %errorlevel% neq 0 (
    echo [webui] ❌ 启动失败，请查看上方错误信息。
    pause
)

popd
endlocal
