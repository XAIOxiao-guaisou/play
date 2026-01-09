# GitHub 上传指南

## 第一步：准备 GitHub 仓库

1. 在 GitHub 上创建新仓库：https://github.com/new
2. 仓库名：`play`
3. 描述：可选
4. 选择公开或私有
5. **不要**初始化 README、.gitignore 或许可证（因为本地已有）

## 第二步：上传代码

1. 双击运行 `upload_to_github.bat`
2. 按照提示操作：
   - 确认 Git 已安装
   - 输入提交信息（默认为 "Initial commit"）
   - 等待上传完成

## 第三步：验证上传

1. 访问 https://github.com/XAIOxiao-guaisou/play
2. 确认所有文件已成功上传
3. 检查代码结构和内容

## 常见问题

### 1. Git 未安装
- 下载并安装 Git：https://git-scm.com/downloads
- 安装时选择默认选项即可

### 2. 网络连接问题
- 检查网络连接
- 确保可以访问 GitHub
- 如有防火墙，可能需要配置代理

### 3. 权限问题
- 确保有仓库的写入权限
- 如果是私有仓库，需要登录 GitHub 账户

### 4. 大文件上传
- 如果文件较大，上传可能需要较长时间
- 确保稳定的网络连接

## 后续更新

要更新代码到 GitHub，可以使用以下命令：

```bash
# 添加所有变更
git add .

# 提交变更
git commit -m "描述变更内容"

# 推送到 GitHub
git push
```

或直接运行批处理文件：
```bash
upload_to_github.bat
```