@echo off
setlocal EnableDelayedExpansion

echo ===============================================
echo GitHub 私密仓库上传脚本
echo 目标: 上传文件夹内所有文件
echo 仓库: https://github.com/XAIOxiao-guaisou/play.git
echo ===============================================
echo.

:: 1. 检查 Git 环境 [cite: 1]
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ 未检测到 Git，请先安装: https://git-scm.com/downloads
    pause
    exit /b 1
)

:: 2. 初始化仓库 [cite: 3]
if not exist .git (
    echo 📁 正在初始化本地 Git 仓库...
    git init
    echo ✅ 初始化成功
)

:: 3. 配置远程仓库地址 [cite: 4, 5]
:: 注意：私密仓库在 push 时会弹出窗口要求登录 GitHub
git remote remove origin >nul 2>&1
git remote add origin https://github.com/XAIOxiao-guaisou/play.git
echo ✅ 远程仓库已指向: https://github.com/XAIOxiao-guaisou/play.git

:: 4. 强制添加文件夹内所有文件 
echo 📦 正在扫描并添加所有文件...
:: 使用 git add -A 确保包含所有新增、修改和删除的文件
git add -A 
if %errorlevel% neq 0 (
    echo ❌ 添加文件失败
    pause
    exit /b 1
)
echo ✅ 所有文件已进入暂存区

:: 5. 提交变更 [cite: 7]
set /p COMMIT_MESSAGE="请输入提交备注 (直接回车则使用 'Update all files'): "
if "!COMMIT_MESSAGE!"=="" set COMMIT_MESSAGE=Update all files
git commit -m "!COMMIT_MESSAGE!"

:: 6. 推送到 GitHub [cite: 8, 9]
echo 🚀 正在上传到私密仓库...
echo ℹ️  提示：如果弹出登录框，请完成 GitHub 身份验证。
git branch -M main
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo 🎉 上传完成！ [cite: 10]
) else (
    echo ❌ 上传失败，请检查网络或 GitHub 访问权限。 [cite: 9]
)

pause