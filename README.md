# OneLap到多平台数据同步工具

## 功能
从 OneLap (顽鹿) 平台下载运动数据，同步到：
- 行者 (XOSS)
- 捷安特骑行 (Giant)
- iGPSport

## 使用方法

1. 编辑 `settings.ini` 配置各平台账号密码
2. 运行程序：
   ```bash
   ./SyncOnelapToXoss
   ```

## 配置说明

编辑 `settings.ini`：
- `[onelap]` - 顽鹿账号（数据源）
- `[xoss]` - 行者账号
- `[giant]` - 捷安特账号
- `[igpsport]` - iGPSport账号

设置 `enable_sync = true/false` 控制是否同步到对应平台。

## 系统要求

- Linux x86_64
- Chrome/Chromium 浏览器

## 版本

v1.2.0 - 新增 iGPSport 平台支持
