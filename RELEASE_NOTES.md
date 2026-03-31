# 发布说明

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
