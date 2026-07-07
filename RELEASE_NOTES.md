# 发布说明

## v1.2.15 (2026-07-07)

### 新增功能：Strava 同步时 FIT 坐标自动转换（GCJ-02 → WGS84）

OneLap（顽鹿）下载的 FIT 文件使用 GCJ-02 火星坐标系，而 Strava 采用 WGS84 国际标准坐标系。直接上传会导致轨迹位置偏移约 50-500 米。

#### 功能说明

- 新增 `fit_coord_transform.py` 模块，基于 `garmin-fit-sdk` 实现 FIT 文件全量坐标转换。
- 转换范围覆盖 `record`、`lap`、`session` 等所有包含坐标的消息（position_lat/position_long、start_position_lat/position_long、end_position_lat/position_long、nec_lat/nec_long、swc_lat/swc_long）。
- 境外坐标自动跳过（`out_of_china` 判断），不对海外轨迹做错误偏移。
- 坐标系转换算法采用 `coordTransform_py` 标准实现，精度约 1-2 米。

#### 配置

新增配置项 `[strava] gcj02_to_wgs84`，默认启用：

```ini
[strava]
gcj02_to_wgs84 = true   # true=启用(默认), false=上传原始文件
```

#### 实现细节

- 上传前生成 WGS84 临时副本，原始 GCJ-02 文件保留不动（供国内平台继续使用）。
- 上传完成后自动清理临时文件。
- 去重签名基于原始文件，转换后不产生重复上传。
- 依赖新增：`garmin-fit-sdk>=21.0.0`（已加入 `requirements.txt`）。

---

## v1.2.14 (2026-06-29)

### 修复顽鹿登录与新增 Docker 部署

- 适配顽鹿新版登录页 `u.onelap.cn/login`（Arco Design），登录输入框、密码框和登录按钮均采用新版选择器，并保留旧版页面选择器作为兜底。
- 登录成功判定优先读取 localStorage 中的 token，再以 URL 跳转和 userInfo 作为兜底，提升登录成功识别的可靠性。
- OneLap 接口 Referer 统一指向 `recordPage` 数据管理页，修复因 Referer 不匹配导致的请求异常。
- 新增 `[app] debug_mode` 调试开关：登录失败时浏览器保持打开并打印当前 URL、标题和 localStorage 内容，便于排查问题。
- 新增 Docker 部署支持（`Dockerfile`、`docker-compose.yml`、`entrypoint.sh`），基于 selenium 官方镜像并内置 noVNC，可在浏览器中观察运行过程、手动处理验证码。
- `settings.ini` 不再纳入版本控制（加入 `.gitignore`），避免误提交真实账号密码；请从 `settings.ini.example` 复制后填写。

感谢 @tanpengsccd 贡献顽鹿登录修复与 Docker 部署方案。

---

## v1.2.13 (2026-06-03)

### 新增功能：Garmin Connect 中国区同步

- 新增 Garmin Connect 中国区平台支持，可将 OneLap 下载的运动文件导入 `https://connect.garmin.cn/app/import-data`。
- Garmin 使用浏览器自动登录，遇到验证码、短信验证或二次验证时允许用户在浏览器中手动完成。
- Garmin 支持作为正向增量同步基准，优先级位于 Giant 之后、Strava 之前。
- Garmin 上传支持按批导入，`[garmin] max_upload_files` 可指定 Garmin 每批最多上传文件数。
- Garmin 上传顺序按 OneLap 活动时间从旧到新执行，避免中途异常后最新时间被提前推进导致漏传。
- `settings.ini.example`、README 和使用说明新增 `[garmin]` 配置和使用场景说明。

---

## v1.2.12 (2026-04-25)

### 修复与优化

- 主同步链路切换到 OneLap 新版签名 API，使用 token + 签名分页获取活动，并通过 `base64(fitUrl)` 下载 FIT 文件。
- 正向同步按下游平台最新记录做增量比对，触达同步基准后停止翻页，避免把历史数据全部拉出再处理。
- 新增 OneLap 下载状态记录与 `.part` 临时文件落盘，支持跳过已完成下载并降低中断后留下坏文件的概率。
- 修复 OneLap FIT 下载参数兼容性问题：优先使用完整 `fitUrl`，失败时自动回退尝试解码 URL、路径和文件名候选，避免部分记录在 `fit_content` 接口上连续 500。
- 反向 `iGPSport -> OneLap` 上传改为直接调用 OneLap 上传接口，修复旧页面自动化已选中文件但实际未入库的问题。
- 反向上传成功判定改为按活动时间的数量增量校验，避免把已存在同时间记录误判为新上传成功。
- 统一主脚本和增量脚本的配置路径为程序目录下的 `settings.ini`，不再依赖启动时的当前工作目录。
- 修复反向同步在 Windows 下的 FIT 文件名兼容性与控制台输出兼容性问题。

---

## v1.2.7 (2026-04-01)

### 🎉 新增功能：Strava 同步

#### 功能概述
现在支持将 OneLap 的运动记录同步到 Strava！使用标准的 OAuth 2.0 授权方式，安全可靠。

#### 首次接入步骤

1. **在 Strava Developers 创建应用**
   - 访问 https://www.strava.com/settings/api
   - 点击 "Create an App"
   - 填写应用信息（名称、描述等）
   - 网站 URL 可以填任意地址
   - **回调地址** 必须填：`http://127.0.0.1:8765/callback`

2. **获取 Client ID 和 Client Secret**
   - 创建应用后，可以看到你的 Client ID
   - 点击 "Show" 查看并复制 Client Secret

3. **配置 settings.ini**
   ```ini
   [strava]
   enable_sync = true
   client_id = 你的Client_ID
   client_secret = 你的Client_Secret
   access_token =
   refresh_token =
   expires_at = 0
   redirect_port = 8765
   athlete_id =
   athlete_name =
   ```

4. **完成首次授权**
   运行以下命令完成 OAuth 授权：
   ```bash
   python3 SyncOnelapToXoss.py --strava-auth
   ```

   程序会自动打开浏览器，你在 Strava 网页上确认授权后，程序会自动保存 token 到 settings.ini。

#### 日常使用

首次授权完成后，以后直接运行主程序即可：
```bash
python3 SyncOnelapToXoss.py
```

程序会自动：
- 检测 token 是否过期
- 自动刷新 token
- 上传新的活动记录
- 自动跳过重复记录

#### Strava 测试命令

```bash
# 测试 token 是否可用
python3 SyncOnelapToXoss.py --strava-test

# 测试上传单个文件
python3 SyncOnelapToXoss.py --strava-upload-test /path/to/file.fit
```

#### 配置说明

| 配置项 | 说明 |
|--------|------|
| `client_id` | Strava 应用的 Client ID |
| `client_secret` | Strava 应用的 Client Secret |
| `access_token` | 访问令牌（首次授权后自动生成） |
| `refresh_token` | 刷新令牌（首次授权后自动生成） |
| `expires_at` | 令牌过期时间（首次授权后自动生成） |
| `redirect_port` | 本地回调端口，默认 8765 |

---

### 🔧 重要修复：iGPSport 上传功能

#### 问题现象
之前版本上传到 iGPSport 时可能出现：
- 文件输入框定位失败（type/name/accept 显示为 None）
- 确认按钮命中到整个模态框容器，而不是真正的按钮

#### 修复内容

1. **文件输入框定位优化**
   - 废弃了 "HTML 正则解析 + 按索引取元素" 的脆弱方式
   - 改用 CSS 选择器直接定位：`input[type="file"]` 或 `input[name="file"]`
   - 找到后立即验证 type/name/accept 属性，确保找对元素
   - 更可靠地显示隐藏的输入框

2. **确认按钮选择优化**
   - 移除了模糊匹配 `any(t in text for t in ...)`
   - 只保留精确匹配 `text in candidate_texts`
   - 避免命中包含"确认"/"上传"文本的容器元素

---

### 📋 同步基准优先级说明

主程序使用固定优先级链选择增量同步基准（不是所有平台比较取最大）：

| 优先级 | 平台 |
|--------|------|
| 1 | XOSS / 行者 |
| 2 | iGPSport |
| 3 | Giant / 捷安特 |
| 4 | Strava |

**示例**：
- 如果 XOSS 和 Strava 都启用，优先使用 XOSS 作为增量基准
- 如果只启用 Strava，则使用 Strava 作为增量基准

---

### 🚀 其他改进

- GitHub Actions 自动构建和发布
  - Windows 版本（.zip）
  - Linux 版本（.tar.gz）
  - 推送 tag 时自动创建 GitHub Release
- Strava 重复上传保护
  - 本地记录已上传的文件签名
  - 自动跳过重复文件
- Strava token 自动刷新
  - 检测到即将过期时自动刷新
  - 无需手动干预
- GitHub Release Notes 使用自定义说明
  - 从 `RELEASE_NOTES.md` 读取当前版本的详细说明

---

## v1.2.6 (2026-04-01)

### 🎉 新增功能：Strava 同步

#### 功能概述
现在支持将 OneLap 的运动记录同步到 Strava！使用标准的 OAuth 2.0 授权方式，安全可靠。

#### 首次接入步骤

1. **在 Strava Developers 创建应用**
   - 访问 https://www.strava.com/settings/api
   - 点击 "Create an App"
   - 填写应用信息（名称、描述等）
   - 网站 URL 可以填任意地址
   - **回调地址** 必须填：`http://127.0.0.1:8765/callback`

2. **获取 Client ID 和 Client Secret**
   - 创建应用后，可以看到你的 Client ID
   - 点击 "Show" 查看并复制 Client Secret

3. **配置 settings.ini**
   ```ini
   [strava]
   enable_sync = true
   client_id = 你的Client_ID
   client_secret = 你的Client_Secret
   access_token =
   refresh_token =
   expires_at = 0
   redirect_port = 8765
   athlete_id =
   athlete_name =
   ```

4. **完成首次授权**
   运行以下命令完成 OAuth 授权：
   ```bash
   python3 SyncOnelapToXoss.py --strava-auth
   ```

   程序会自动打开浏览器，你在 Strava 网页上确认授权后，程序会自动保存 token 到 settings.ini。

#### 日常使用

首次授权完成后，以后直接运行主程序即可：
```bash
python3 SyncOnelapToXoss.py
```

程序会自动：
- 检测 token 是否过期
- 自动刷新 token
- 上传新的活动记录
- 自动跳过重复记录

#### Strava 测试命令

```bash
# 测试 token 是否可用
python3 SyncOnelapToXoss.py --strava-test

# 测试上传单个文件
python3 SyncOnelapToXoss.py --strava-upload-test /path/to/file.fit
```

#### 配置说明

| 配置项 | 说明 |
|--------|------|
| `client_id` | Strava 应用的 Client ID |
| `client_secret` | Strava 应用的 Client Secret |
| `access_token` | 访问令牌（首次授权后自动生成） |
| `refresh_token` | 刷新令牌（首次授权后自动生成） |
| `expires_at` | 令牌过期时间（首次授权后自动生成） |
| `redirect_port` | 本地回调端口，默认 8765 |

---

### 🔧 重要修复：iGPSport 上传功能

#### 问题现象
之前版本上传到 iGPSport 时可能出现：
- 文件输入框定位失败（type/name/accept 显示为 None）
- 确认按钮命中到整个模态框容器，而不是真正的按钮

#### 修复内容

1. **文件输入框定位优化**
   - 废弃了 "HTML 正则解析 + 按索引取元素" 的脆弱方式
   - 改用 CSS 选择器直接定位：`input[type="file"]` 或 `input[name="file"]`
   - 找到后立即验证 type/name/accept 属性，确保找对元素
   - 更可靠地显示隐藏的输入框

2. **确认按钮选择优化**
   - 移除了模糊匹配 `any(t in text for t in ...)`
   - 只保留精确匹配 `text in candidate_texts`
   - 避免命中包含"确认"/"上传"文本的容器元素

---

### 📋 同步基准优先级说明

主程序使用固定优先级链选择增量同步基准（不是所有平台比较取最大）：

| 优先级 | 平台 |
|--------|------|
| 1 | XOSS / 行者 |
| 2 | iGPSport |
| 3 | Giant / 捷安特 |
| 4 | Strava |

**示例**：
- 如果 XOSS 和 Strava 都启用，优先使用 XOSS 作为增量基准
- 如果只启用 Strava，则使用 Strava 作为增量基准

---

### 🚀 其他改进

- GitHub Actions 自动构建和发布
  - Windows 版本（.zip）
  - Linux 版本（.tar.gz）
  - 推送 tag 时自动创建 GitHub Release
- Strava 重复上传保护
  - 本地记录已上传的文件签名
  - 自动跳过重复文件
- Strava token 自动刷新
  - 检测到即将过期时自动刷新
  - 无需手动干预

---

## v1.2.5 (2026-03-28)

### ✅ 增量同步保护增强

- 防止未配置全量开关时自动执行全量同步
- 新增安全保护，未显式配置 onelap_full_sync=true 时将终止程序

### ✅ 行者(XOSS)基准提取优化

- 增强了对 XOSS 平台最新活动时间的解析能力
- 修复了基准判断失败的问题

### ✅ iGPSport 导入功能修复

- 修复了登录成功判断逻辑
- 优化了页面访问和导入按钮定位
- 使用正则表达式精准定位到第10个隐藏的文件输入框
- 成功显示隐藏的输入框并完成文件选择和上传

### ✅ 文件格式兼容性优化

- 继续支持 .fit, .gpx, .tcx 文件格式
- 保持 iGPSport → OneLap 反向增量同步功能

### 🚀 性能改进

- 同步流程优化，减少无效请求
- 增强了错误处理和重试机制

## 技术变更

- Python 代码重构，优化了逻辑流程
- 使用正则表达式精确定位输入框
- 增强了浏览器操作的稳定性
