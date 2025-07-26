# OneLap到行者(XOSS)数据同步工具配置文件
# 请根据您的实际情况修改以下配置

# 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL = 'INFO'

# 浏览器无头模式 (True=无头模式, False=显示浏览器窗口)
HEADLESS_MODE = False

# OneLap平台账号信息
ONELAP_ACCOUNT = '139xxxxxx'  # 您的OneLap账号（手机号或邮箱）
ONELAP_PASSWORD = 'xxxxxx'  # 您的OneLap密码

# 行者平台账号信息
XOSS_ACCOUNT = '139xxxxxx'  # 您的行者账号（手机号或邮箱）
XOSS_PASSWORD = 'xxxxxx'  # 您的行者密码

# 文件存储目录
STORAGE_DIR = './downloads'

# 支持的文件格式
SUPPORTED_FORMATS = ['.fit', '.gpx', '.tcx']

# 最大文件大小限制 (字节)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# 每批上传的最大文件数量
MAX_FILES_PER_BATCH = 5 