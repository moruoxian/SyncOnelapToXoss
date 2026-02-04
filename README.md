# OneLap多平台数据同步工具

这是一个用于从OneLap平台下载运动数据并同步到多个骑行平台的自动化工具。

## 支持的平台

- **OneLap (顽鹿)** - 数据源平台
- **行者 (XOSS)** - 目标同步平台
- **捷安特骑行** - 目标同步平台（可选）
- **iGPSport** - 目标同步平台（可选）

## 功能特性

- 自动登录OneLap和多个目标平台
- 智能同步：只同步比行者最新活动更新的OneLap活动
- 支持批量下载和上传FIT文件
- 支持同时同步到多个平台（行者、捷安特、iGPSport）
- 详细的日志记录
- 可配置的批处理大小和文件大小限制

## 安装要求

### Python依赖
```bash
pip install DrissionPage requests bs4
```

### 系统要求
- Python 3.7+
- Chrome浏览器（用于自动化操作）

## 配置说明

修改 `settings.ini` 配置文件中的平台账号和密码：

```ini
[onelap]
# OneLap平台账号信息
username = 139xxxxxx
password = xxxxxx

[xoss]
# 行者平台账号信息
username = 139xxxxxx
password = xxxxxx

[giant]
# 捷安特骑行平台账号信息
username = 139xxxxxx
password = xxxxxx
# 是否启用捷安特平台同步 (true=启用, false=禁用)
enable_sync = false

[igpsport]
# iGPSport平台账号信息
username = 139xxxxxx
password = xxxxxx
# 是否启用iGPSport平台同步 (true=启用, false=禁用)
enable_sync = false
```

### 其他可选配置

在 `[sync]` 节中可配置：
- `storage_dir`: 文件存储目录（默认: './downloads'）
- `max_files_per_batch`: 每批上传文件数（默认: 5）
- `max_file_size_mb`: 最大文件大小限制（默认: 50MB）

在 `[app]` 节中可配置：
- `headless_mode`: 无头模式（默认: false）
- `log_level`: 日志级别（默认: INFO）

## 使用方法

1. 确保已正确配置 `settings.ini` 文件
2. 运行同步工具：
```bash
python SyncOnelapToXoss.py
```

## 工作流程

1. **步骤1 - 登录顽鹿**: 自动登录OneLap平台获取cookies
2. **步骤2 - 登录行者**: 自动登录行者平台，获取最新活动记录
3. **步骤3 - 下载文件**: 智能筛选并下载比行者最新活动更新的FIT文件
4. **步骤4 - 上传行者**: 分批上传文件到行者平台
5. **步骤5 - 上传捷安特**: 上传文件到捷安特骑行平台（可选）
6. **步骤6 - 上传iGPSport**: 上传文件到iGPSport平台（可选）
7. **步骤7 - 验证结果**: 显示同步结果

## 日志说明

工具会生成详细的日志信息，包括：
- 各平台登录状态
- 活动筛选结果
- 文件下载进度
- 各平台上传状态
- 错误信息

## 注意事项

1. 请确保网络连接稳定
2. 首次运行可能需要手动处理验证码
3. 建议在非高峰期运行以避免平台限制
4. 定期检查日志文件以监控同步状态
5. 捷安特和iGPSport平台需要在配置中设置 `enable_sync = true` 才会启用

## 故障排除

### 常见问题

1. **登录失败**: 检查账号密码是否正确
2. **下载失败**: 检查网络连接和OneLap平台状态
3. **上传失败**: 检查目标平台状态和文件格式

### 调试模式

在 `settings.ini` 中设置 `log_level = DEBUG` 可以获取更详细的日志信息。

## 许可证

本项目仅供个人学习和使用，请遵守相关平台的使用条款。
