@echo off
setlocal EnableExtensions

echo [webui] XHS Cyber UI 一键启动

:: 确保工作目录为脚本所在目录
pushd "%~dp0"

set HOST=127.0.0.1
set PORT=8000
if not "%~1"=="" set PORT=%~1

echo [webui] HOST=%HOST% PORT=%PORT%

:: 检查端口是否被占用并尝试释放
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr LISTENING') do (
    echo [webui] 端口 %PORT% 被 PID %%p 占用，尝试结束...
    taskkill /PID %%p /F >nul 2>&1
)

:: 激活虚拟环境
if exist .venv\Scripts\activate.bat (
    echo [webui] 激活虚拟环境 .venv ...
    call .venv\Scripts\activate.bat
) else (
    echo [webui] 未找到 .venv，使用系统 python
)

:: 检查依赖是否安装
python -c "import sys; sys.path.insert(0, '.'); import web_ui" 2>webui_import_error.log
if %errorlevel% neq 0 (
    echo [webui] ❌ 无法导入 web_ui:app，请检查依赖或文件是否存在。
    echo [webui]    建议先运行: pip install -r requirements.txt
    echo [webui]    详细错误见 webui_import_error.log
    type webui_import_error.log
    pause
    popd
    exit /b 1
)

echo [webui] 启动后端服务 (uvicorn) ...

:: 打开浏览器
set "URL=http://%HOST%:%PORT%/"
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1; Start-Process '%URL%'"

python -m uvicorn web_ui:app --host %HOST% --port %PORT%

if %errorlevel% neq 0 (
    echo [webui] ❌ 启动失败，请查看上方错误信息。
    pause
)

popd
endlocal
