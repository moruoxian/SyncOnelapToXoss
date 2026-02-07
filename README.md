# OneLap到多平台数据同步工具

## 🎯 功能概述

从 OneLap (顽鹿) 平台下载运动数据，同步到多个平台：
- ✅ 行者 (XOSS)
- ✅ 捷安特骑行 (Giant)
- ✅ iGPSport

## 🎉 新增功能：iGPSport → OneLap 反向增量同步

### 功能说明

将 iGPSport 中比 OneLap 新的骑行记录自动同步到 OneLap。

**适用场景**：当您的 iGPSport 记录比 OneLap 多时，使用此功能补录数据。

### 与传统方式对比

| 方式 | 处理180条记录 | 速度 |
|------|---------------|------|
| 传统全量同步 | 每次处理180条 | 约5分钟 |
| **新增增量同步** | 只处理3条新记录 | **约15秒** |

### 配置方法

在 `settings.ini` 中添加配置：

```ini
[igpsport_to_onelap]
# 是否启用反向同步
eable = false    # true=启用, false=禁用(默认)

# 同步模式
mode = auto      # auto=增量(推荐), full=全量

# 比对策略
strategy = time_based  # 基于时间戳比对
```

### 配置项详解

| 配置项 | 可选值 | 默认值 | 说明 |
|--------|--------|--------|------|
| `enable` | `true`/`false` | `false` | 功能开关 |
| `mode` | `auto`/`full` | `auto` | 同步模式 |
| `strategy` | `time_based` | `time_based` | 比对策略 |

#### 同步模式

- **auto（智能增量模式）**：自动检测 iGPSport 中 OneLap 没有的新记录，只同步这些
- **full（全量模式）**：同步 iGPSport 中所有记录

**建议**：日常使用 `auto` 模式，即使 OneLap 为空也会自动全量同步。

### 使用方法

```bash
# 1. 开启反向同步（编辑 settings.ini）
# [igpsport_to_onelap]
# enable = true
# mode = auto

# 2. 运行程序
python3 SyncOnelapToXoss.py
```

程序会自动：
1. 执行原有逻辑（OneLap → 行者/捷安特/iGPSport）
2. 执行新增逻辑（iGPSport → OneLap 增量同步）

### 工作流程

```
程序启动
    │
    ├── 步骤1-7: 原有逻辑（OneLap → 行者/捷安特/iGPSport）
    │
    └── 步骤8: 新增逻辑（iGPSport → OneLap 增量同步）
            │
            ├── 登录 iGPSport（API方式）
            ├── 获取所有记录（180条）
            ├── 登录 OneLap（浏览器方式）
            ├── 获取最新记录时间
            ├── 筛选增量记录（时间 > OneLap最新时间）
            ├── 下载增量文件
            └── 批量上传到 OneLap
```

### 输出示例

```
🚴 iGPSport → OneLap 增量同步
==========================================
📊 发现增量: 3 条新记录
   ├─ 2026-02-05 - 2.3km
   ├─ 2026-02-02 - 20.5km
   └─ 2026-02-02 - 13.0km

⬇️  下载完成: 231 KB
⬆️  上传完成: 3/3

✅ 同步成功！耗时 15 秒
==========================================
```

## 📖 使用指南

### 1. 快速开始 (Windows 用户)

如果您下载的是 Windows 打包版本 (`.zip`)：

1.  **解压文件**：将压缩包解压到一个文件夹中。
2.  **配置账号**：
    *   找到 `settings.ini` 文件。
    *   用记事本打开，填入您的 OneLap、行者、捷安特或 iGPSport 账号密码。
    *   **注意**：`enable_sync = true` 表示启用该平台的同步。
3.  **运行程序**：
    *   双击 `SyncOnelapToXoss.exe`。
    *   程序会自动打开浏览器进行操作，**请勿关闭该浏览器窗口**，等待程序运行结束。

### 2. 开发者指南 (源码运行)

如果您是开发者或希望通过源码运行：

1.  **环境准备**：
    *   Python 3.7+
    *   Chrome 浏览器
2.  **安装依赖**：
    ```bash
    pip install -r requirements.txt
    ```
3.  **配置文件**：
    *   复制模板：`cp settings.ini.example settings.ini` (Windows 下手动复制重命名即可)
    *   编辑 `settings.ini` 填入账号信息。
4.  **运行脚本**：
    ```bash
    python SyncOnelapToXoss.py
    ```

## ⚙️ 业务场景与配置

本工具支持多种同步场景，请根据需求修改 `settings.ini`：

### 场景 A：OneLap 数据同步到其他平台 (默认)
*   **用途**：将顽鹿(OneLap)的骑行记录同步到行者、捷安特或 iGPSport。
*   **配置**：
    *   `[onelap]`: 填入账号密码（必须）。
    *   `[xoss]`: 填入账号密码（如不同步到行者，可不填）。
    *   `[giant]`: 填入账号密码并将 `enable_sync = true` (如不同步到捷安特，可不填)。
    *   `[igpsport]`: 填入账号密码并将 `enable_sync = true` (如不同步到 iGPSport，可不填)。

### 场景 B：iGPSport 数据反向同步到 OneLap (新功能)
*   **用途**：当 iGPSport 记录比 OneLap 全时，将缺失的记录补录回 OneLap。
*   **配置**：
    *   `[igpsport_to_onelap]`: 设置 `enable = true`。
    *   建议保持 `mode = auto` (智能增量模式)，只同步新数据。

## ⚙️ 详细配置说明

编辑 `settings.ini`：

```ini
[onelap]
username = 13800138000    # OneLap账号（数据源）
password = your_password

[xoss]
username = 13800138000    # 行者账号
password = your_password

[giant]
username = 13800138000    # 捷安特账号
password = your_password
enable_sync = false       # 是否启用捷安特同步

[igpsport]
username = 13800138000    # iGPSport账号
password = your_password
enable_sync = false       # 是否启用iGPSport同步（主程序方向）

[sync]
storage_dir = ./downloads
supported_formats = .fit,.gpx,.tcx
max_file_size_mb = 50
max_files_per_batch = 5

[igpsport_to_onelap]
enable = false            # 反向同步开关
mode = auto               # 同步模式
```

## 🔒 安全说明

- `settings.ini` 包含敏感信息，**请勿提交到 Git**
- 已添加到 `.gitignore`，不会被包含在版本控制中
- 提供 `settings.ini.example` 作为配置模板

## 💻 系统要求

- Python 3.7+
- Chrome/Chromium 浏览器
- Linux/macOS/Windows

## 📦 安装依赖

```bash
pip install -r requirements.txt
```

## 📝 版本历史

### v1.2.3 (2026-02-08)
- ✅ 新增 iGPSport → OneLap 反向增量同步功能
- ✅ 智能增量检测，只同步新数据
- ✅ settings.ini 使用示例账号优化
- ✅ 文档合并优化：说明文档整合到 README.md

### v1.2.1
- ✅ 修复 iGPSport 批量上传问题（支持一次上传多个 .fit 文件）
- ✅ 增强容错性：OneLap/行者登录失败时不再直接退出，而是尝试继续后续流程
- ✅ 优化发布包命名

### v1.2.0
- ✅ 新增 iGPSport 平台支持

### v1.0.0
- ✅ 初始版本，支持 OneLap → 行者/捷安特

## 🙏 注意事项

1. **首次使用建议测试**：先开启预览模式确认增量数量
2. **定期同步**：建议每周运行一次，保持数据同步
3. **账号安全**：settings.ini 包含敏感信息，请勿分享

---

**Enjoy your ride! 🚴‍♂️**
