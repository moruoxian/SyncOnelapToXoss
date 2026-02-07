# iGPSport → OneLap 反向增量同步功能说明

## 🎯 功能介绍

新增 **iGPSport → OneLap 反向增量同步** 功能。

### 什么是"反向同步"？

- **主程序默认方向**：OneLap → 行者/捷安特/iGPSport（从 OneLap 下载，上传到其他平台）
- **新增反向同步**：iGPSport → OneLap（从 iGPSport 下载，上传到 OneLap）

### 适用场景

当您的 **iGPSport 记录比 OneLap 多** 时，使用此功能将缺失的记录自动补录到 OneLap。

## 📊 对比说明

| 同步方向 | 数据源 | 目标平台 | 使用场景 |
|---------|--------|---------|---------|
| 主程序默认 | OneLap | 行者/捷安特/iGPSport | OneLap 数据最全 |
| **反向同步（新增）** | **iGPSport** | **OneLap** | **iGPSport 数据最全** |

## ⚙️ 配置方法

### 1. 配置结构说明

```ini
[sync]
# 这是主程序原有配置（OneLap → 其他平台）
storage_dir = ./downloads
supported_formats = .fit,.gpx,.tcx
max_file_size_mb = 50
max_files_per_batch = 5

# ========== 独立配置节：iGPSport → OneLap 反向同步 ==========
[igpsport_to_onelap]
# 与 [sync] 完全独立，专门控制反向同步功能
enable = false          # 是否启用
mode = auto             # 同步模式
strategy = time_based   # 比对策略
```

### 2. 开启反向增量同步

编辑 `settings.ini` 文件，在文件末尾添加独立的配置节：

```ini
# ========== iGPSport → OneLap 反向增量同步配置 ==========
# 
# 功能说明：将 iGPSport 中比 OneLap 新的骑行记录自动同步到 OneLap
# 适用场景：iGPSport 记录比 OneLap 多，需要补录数据到 OneLap
# 
# 注意：这是【反向同步】，与主程序默认的 OneLap → 其他平台 方向相反
# 
[igpsport_to_onelap]

# 是否启用反向同步 (true=启用, false=禁用)
# 默认禁用，需要时手动开启
enable = true

# 同步模式选择
#   auto  = 智能增量模式（推荐）：自动检测 iGPSport 中 OneLap 没有的新记录，只同步这些
#   full  = 全量模式：同步 iGPSport 中所有记录
# 说明：即使 OneLap 为空，auto 模式也会自动全量同步
mode = auto

# 同步策略（当前仅支持 time_based）
#   time_based = 基于时间戳比对：比较记录时间，iGPSport 时间 > OneLap 最新时间的记录被视为增量
strategy = time_based
```

### 3. 确保账号配置正确

```ini
[onelap]
username = 你的OneLap账号
password = 你的OneLap密码

[igpsport]
username = 你的iGPSport账号
password = 你的iGPSport密码
```

## 🚀 使用方法

### 正常使用（增量同步）

```bash
python3 SyncOnelapToXoss.py
```

程序会自动：
1. 执行主程序逻辑（OneLap → 行者/捷安特/iGPSport）
2. 如果 `[igpsport_to_onelap] enable = true`，则执行反向同步（iGPSport → OneLap）

### 输出示例

```
===== 步骤8：iGPSport → OneLap 反向增量同步 =====
开始执行 iGPSport → OneLap 反向同步...
当前为同步模式: auto

======================================================================
iGPSport → OneLap 增量同步（基于最新时间戳）
======================================================================

【步骤1】登录两个平台...
[iGPSport] 登录中...
[iGPSport] ✅ 登录成功
[OneLap] 启动浏览器...
[OneLap] ✅ 登录成功

【步骤2】获取 iGPSport 所有记录...
[iGPSport] 共获取 180 条记录

【步骤3】获取 OneLap 最新记录时间...
[OneLap] 最新记录时间: 2026-01-30

【步骤4】筛选增量记录（时间 > OneLap 最新时间）...

📈 找到 3 条增量记录

增量记录列表:
  1. 2026-02-05 - 2.3km
  2. 2026-02-02 - 20.5km
  3. 2026-02-02 - 13.0km

【步骤5】下载 3 个增量文件...
  [1/3] 下载: 2026-02-05 (2.3km)
      ✅ 完成 (16.7 KB)
  [2/3] 下载: 2026-02-02 (20.5km)
      ✅ 完成 (127.3 KB)
  [3/3] 下载: 2026-02-02 (13.0km)
      ✅ 完成 (87.0 KB)

【步骤6】上传到 OneLap...
  [1/3] 上传: 2026-02-05-44520615.fit
      ✅ 上传成功
  [2/3] 上传: 2026-02-02-44511454.fit
      ✅ 上传成功
  [3/3] 上传: 2026-02-02-44511453.fit
      ✅ 上传成功

======================================================================
📋 同步报告
======================================================================
iGPSport 总记录: 180
OneLap 最新时间: 2026-01-30
增量记录: 3
成功下载: 3
成功上传: 3
======================================================================
✅ 增量同步完成！
```

## 🔧 配置项详解

### `[igpsport_to_onelap]` 配置节

| 配置项 | 可选值 | 默认值 | 说明 |
|--------|--------|--------|------|
| `enable` | `true` / `false` | `false` | 是否启用反向同步功能 |
| `mode` | `auto` / `full` | `auto` | 同步模式：`auto`=智能增量，`full`=全量 |
| `strategy` | `time_based` | `time_based` | 比对策略：`time_based`=基于时间戳比对 |

### 同步模式详解

#### `mode = auto`（智能增量模式 - 推荐）

**工作原理：**
1. 获取 iGPSport 所有记录的时间列表
2. 获取 OneLap 最新一条记录的时间
3. 筛选出 iGPSport 中 **时间 > OneLap 最新时间** 的记录
4. 只同步这些"增量"记录

**适用场景：**
- 日常使用，只同步新增的记录
- 即使 OneLap 为空，也会自动全量同步

**示例：**
- iGPSport 有 180 条记录（2025-07 至 2026-02）
- OneLap 有 177 条记录（最新是 2026-01-30）
- 结果：只同步 3 条记录（2026-02-02 和 2026-02-05 的）

#### `mode = full`（全量模式）

**工作原理：**
尝试同步 iGPSport 中所有记录，不管 OneLap 是否已有。

**适用场景：**
- 特殊情况下需要强制重新同步
- 注意：OneLap 会检测重复，已存在的文件会提示"已上传"

## 🔧 常见问题

### Q: 配置节 `[igpsport_to_onelap]` 和 `[sync]` 有什么区别？

**A:** 
- `[sync]`：控制主程序 **OneLap → 其他平台** 的同步行为
- `[igpsport_to_onelap]`：独立控制 **iGPSport → OneLap** 反向同步行为
- 两者完全独立，互不影响

### Q: 为什么我设置了 `enable = true` 但没有执行反向同步？

**A:** 检查以下几点：
1. 确认配置写在 `[igpsport_to_onelap]` 节下，不是 `[sync]` 节
2. 确认 iGPSport 和 OneLap 账号密码已正确配置
3. 查看程序输出日志中是否有 "步骤8：iGPSport → OneLap 反向增量同步"

### Q: 首次使用应该怎么配置？

**A:** 
```ini
[igpsport_to_onelap]
enable = true
mode = auto
strategy = time_based
```
即使 OneLap 是空的，`auto` 模式也会自动全量同步所有记录。

### Q: 如何完全禁用反向同步功能？

**A:** 两种方式：
1. 设置 `enable = false`
2. 或者直接删除 `[igpsport_to_onelap]` 整个配置节

### Q: `auto` 模式如何确定哪些是"增量"？

**A:** 
1. 获取 OneLap 最新一条记录的时间（页面第一条，因为是倒序排列）
2. 获取 iGPSport 所有记录的时间
3. 筛选出 **iGPSport 记录时间 > OneLap 最新时间** 的记录
4. 这些就是"增量"记录

### Q: 同一天有多个记录怎么办？

**A:** 会全部同步。时间比对精确到日期，同一天内的多个记录都会被视为增量。

### Q: 同步后 OneLap 显示"文件已存在"是什么意思？

**A:** 这是正常的。OneLap 会自动检测重复文件，如果文件已经存在，会提示：
```
You have already uploaded this file.
```
这不会导致数据重复，只是说明这条记录之前已经上传过了。

## 📁 生成的文件

反向同步下载的文件保存在独立的目录：
```
./incremental_sync/           # 增量同步专用目录
├── 2026-02-05-44520615.fit  # 文件名格式：日期-ride_id.fit
├── 2026-02-02-44511454.fit
└── 2026-02-02-44511453.fit
```

与主程序的 `./downloads/` 目录分开，避免混淆。

## 🔄 完整的数据流向图

```
                    ┌─────────────────┐
                    │   OneLap 平台   │
                    └────────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │  行者平台     │ │ 捷安特平台    │ │ iGPSport平台 │
    └──────────────┘ └──────────────┘ └──────┬───────┘
                                             │
            ┌────────────────────────────────┘
            │  【反向同步：iGPSport → OneLap】
            │  （当 [igpsport_to_onelap] enable=true 时启用）
            ▼
    ┌──────────────┐
    │  OneLap 平台  │ ◄── 只同步 iGPSport 中比 OneLap 新的记录
    └──────────────┘
```

## ⚠️ 注意事项

1. **独立的配置节**：反向同步配置在 `[igpsport_to_onelap]` 节下，与 `[sync]` 完全独立
2. **需要两个平台的账号**：必须同时配置 `[onelap]` 和 `[igpsport]` 的账号密码
3. **默认禁用**：新功能默认 `enable = false`，需要手动开启
4. **使用浏览器自动化**：会占用 Chrome 浏览器，不要手动关闭
5. **首次同步可能较慢**：之后每次只同步新增记录，速度极快

## 🎉 开始使用

1. 编辑 `settings.ini`，添加 `[igpsport_to_onelap]` 配置节
2. 设置 `enable = true`
3. 运行 `python3 SyncOnelapToXoss.py`
4. 享受快速、智能的增量同步！
