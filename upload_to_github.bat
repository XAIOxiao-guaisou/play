@echo off
setlocal EnableDelayedExpansion

echo ===============================================
echo GitHub 上传脚本
echo 目标仓库: https://github.com/XAIOxiao-guaisou/play.git
echo ===============================================
echo.

:: 检查是否已安装 Git
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到 Git，请先安装 Git
    echo 下载地址: https://git-scm.com/downloads
    pause
    exit /b 1
)

echo ✅ Git 已安装
echo.

:: 检查当前目录是否为 Git 仓库
if exist .git (
    echo 📁 当前目录已经是 Git 仓库
    git status --porcelain >nul 2>&1
    if %errorlevel% equ 0 (
        echo 📊 检查文件变更...
        git status --porcelain | findstr /r /c:"^[^?]" >nul
        if %errorlevel% equ 0 (
            echo 📝 检测到未提交的变更
        ) else (
            echo ℹ️  没有检测到变更
        )
    )
) else (
    echo 📁 初始化 Git 仓库...
    git init
    if %errorlevel% neq 0 (
        echo ❌ Git 初始化失败
        pause
        exit /b 1
    )
    echo ✅ Git 仓库初始化成功
)

echo.

:: 检查远程仓库配置
git remote get-url origin >nul 2>&1
if %errorlevel% equ 0 (
    echo 🔗 当前远程仓库配置:
    git remote get-url origin
    echo.
    set /p CHANGE_REMOTE="是否要更改远程仓库? (y/N): "
    if /i "!CHANGE_REMOTE!"=="y" (
        git remote remove origin
        echo 🔄 已移除原有远程仓库
    ) else (
        echo ℹ️  使用现有远程仓库配置
        goto :PUSH_CODE
    )
)

:: 添加远程仓库
echo 🔗 添加远程仓库: https://github.com/XAIOxiao-guaisou/play.git
git remote add origin https://github.com/XAIOxiao-guaisou/play.git
if %errorlevel% neq 0 (
    echo ❌ 添加远程仓库失败
    pause
    exit /b 1
)
echo ✅ 远程仓库添加成功

:PUSH_CODE
echo.

:: 添加所有文件到暂存区
echo 📦 添加文件到暂存区...
git add .
if %errorlevel% neq 0 (
    echo ❌ 添加文件失败
    pause
    exit /b 1
)
echo ✅ 文件添加成功

:: 检查是否有文件需要提交
git diff --cached --quiet
if %errorlevel% equ 0 (
    echo ℹ️  没有需要提交的变更
    goto :PUSH_TO_REMOTE
)

:: 提交变更
echo 💾 提交变更...
set /p COMMIT_MESSAGE="请输入提交信息 (默认: Initial commit): "
if "!COMMIT_MESSAGE!"=="" set COMMIT_MESSAGE=Initial commit

git commit -m "!COMMIT_MESSAGE!"
if %errorlevel% neq 0 (
    echo ❌ 提交失败
    pause
    exit /b 1
)
echo ✅ 提交成功

:PUSH_TO_REMOTE
echo.

:: 推送到远程仓库
echo 🚀 推送到 GitHub...
echo 📤 正在上传代码到 https://github.com/XAIOxiao-guaisou/play
git push -u origin main
if %errorlevel% equ 0 (
    echo ✅ 推送成功
    goto :SUCCESS
)

:: 如果 main 分支不存在，尝试 master 分支
echo 🔄 尝试推送到 master 分支...
git push -u origin master
if %errorlevel% equ 0 (
    echo ✅ 推送成功
    goto :SUCCESS
)

:: 如果两个分支都不存在，创建并推送
echo 🔄 创建并推送 main 分支...
git branch -M main
git push -u origin main
if %errorlevel% neq 0 (
    echo ❌ 推送失败，请检查网络连接和仓库权限
    echo 📋 常见问题:
    echo   - 确保 GitHub 仓库已创建
    echo   - 检查网络连接
    echo   - 确认有仓库的写入权限
    pause
    exit /b 1
)

:SUCCESS
echo.
echo ===============================================
echo 🎉 上传完成!
echo 📊 仓库信息:
git remote get-url origin
echo 📈 分支信息:
git branch --show-current
echo ===============================================
echo.
echo 📋 后续操作建议:
echo   - 在 GitHub 上检查代码是否成功上传
echo   - 如有需要，可以设置 .gitignore 文件排除不需要的文件
echo   - 定期使用 git add . && git commit -m "message" && git push 更新代码
echo.

pause