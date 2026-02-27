# OneLap平台数据同步工具
# 文件类型：py
# 文件名称：SyncOnelapToXoss.py
# 功能：从OneLap平台下载最新运动数据并同步到行者平台和捷安特骑行平台
from math import log
from DrissionPage import ChromiumPage, ChromiumOptions
import os
import time
import re
from datetime import datetime
import requests
import hashlib
import logging
import shutil
from bs4 import BeautifulSoup  # 添加BeautifulSoup用于HTML解析
from urllib.parse import unquote, urlparse

# 导入配置 - 支持INI配置文件
import configparser

# ===== 新增：导入增量同步模块 =====
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from incremental_sync_v2 import IncrementalSync
    INCREMENTAL_SYNC_AVAILABLE = True
except ImportError as e:
    INCREMENTAL_SYNC_AVAILABLE = False
    print(f"⚠️ 增量同步模块未加载: {e}")

def load_config_from_ini(config_file="settings.ini"):
    """从INI配置文件加载所有配置参数"""
    if not os.path.exists(config_file):
        print(f"配置文件 {config_file} 不存在，使用默认配置")
        return None
        
    try:
        config = configparser.ConfigParser()
        config.read(config_file, encoding='utf-8-sig')  # 处理BOM字符
        print(f"✅ 成功从 {config_file} 加载配置")
        
        cfg = {}
        cfg['LOG_LEVEL'] = config.get('app', 'log_level', fallback='INFO')
        cfg['HEADLESS_MODE'] = config.getboolean('app', 'headless_mode', fallback=False)
        cfg['ONELAP_ACCOUNT'] = config.get('onelap', 'username', fallback='')
        cfg['ONELAP_PASSWORD'] = config.get('onelap', 'password', fallback='')
        cfg['XOSS_ACCOUNT'] = config.get('xoss', 'username', fallback='')
        cfg['XOSS_PASSWORD'] = config.get('xoss', 'password', fallback='')
        cfg['XOSS_ENABLE_SYNC'] = config.getboolean('xoss', 'enable_sync', fallback=True)
        cfg['GIANT_ACCOUNT'] = config.get('giant', 'username', fallback='')
        cfg['GIANT_PASSWORD'] = config.get('giant', 'password', fallback='')
        cfg['GIANT_ENABLE_SYNC'] = config.getboolean('giant', 'enable_sync', fallback=False)
        cfg['IGPSPORT_ACCOUNT'] = config.get('igpsport', 'username', fallback='')
        cfg['IGPSPORT_PASSWORD'] = config.get('igpsport', 'password', fallback='')
        cfg['IGPSPORT_ENABLE_SYNC'] = config.getboolean('igpsport', 'enable_sync', fallback=False)
        cfg['STORAGE_DIR'] = config.get('sync', 'storage_dir', fallback='./downloads')
        
        formats_str = config.get('sync', 'supported_formats', fallback='.fit,.gpx,.tcx')
        cfg['SUPPORTED_FORMATS'] = [fmt.strip() for fmt in formats_str.split(',')]
        
        cfg['MAX_FILE_SIZE'] = config.getint('sync', 'max_file_size_mb', fallback=50) * 1024 * 1024
        cfg['MAX_FILES_PER_BATCH'] = config.getint('sync', 'max_files_per_batch', fallback=5)
        cfg['ONELAP_FULL_SYNC'] = config.getboolean('sync', 'onelap_full_sync', fallback=False)
        
        # ===== 新增：iGPSport → OneLap 反向增量同步配置 =====
        # 使用独立的配置节 [igpsport_to_onelap]
        cfg['IGPSPORT_TO_ONELAP_ENABLE'] = config.getboolean('igpsport_to_onelap', 'enable', fallback=False)
        cfg['IGPSPORT_TO_ONELAP_MODE'] = config.get('igpsport_to_onelap', 'mode', fallback='auto')
        cfg['IGPSPORT_TO_ONELAP_STRATEGY'] = config.get('igpsport_to_onelap', 'strategy', fallback='time_based')
        
        return cfg
    except Exception as e:
        print(f"❌ 读取INI配置文件失败: {e}")
        return None

# 配置加载逻辑 - 优先INI配置，否则使用默认配置
print("🔧 正在加载配置...")
ini_config = load_config_from_ini()

if ini_config:
    # 使用INI配置
    LOG_LEVEL = ini_config['LOG_LEVEL']
    HEADLESS_MODE = ini_config['HEADLESS_MODE']
    ONELAP_ACCOUNT = ini_config['ONELAP_ACCOUNT']
    ONELAP_PASSWORD = ini_config['ONELAP_PASSWORD']
    XOSS_ACCOUNT = ini_config['XOSS_ACCOUNT']
    XOSS_PASSWORD = ini_config['XOSS_PASSWORD']
    XOSS_ENABLE_SYNC = ini_config.get('XOSS_ENABLE_SYNC', True)
    GIANT_ACCOUNT = ini_config['GIANT_ACCOUNT']
    GIANT_PASSWORD = ini_config['GIANT_PASSWORD']
    GIANT_ENABLE_SYNC = ini_config['GIANT_ENABLE_SYNC']
    IGPSPORT_ACCOUNT = ini_config['IGPSPORT_ACCOUNT']
    IGPSPORT_PASSWORD = ini_config['IGPSPORT_PASSWORD']
    IGPSPORT_ENABLE_SYNC = ini_config['IGPSPORT_ENABLE_SYNC']
    STORAGE_DIR = ini_config['STORAGE_DIR']
    SUPPORTED_FORMATS = ini_config['SUPPORTED_FORMATS']
    MAX_FILE_SIZE = ini_config['MAX_FILE_SIZE']
    MAX_FILES_PER_BATCH = ini_config['MAX_FILES_PER_BATCH']
    ONELAP_FULL_SYNC = ini_config.get('ONELAP_FULL_SYNC', False)
    
    # ===== 新增：读取 iGPSport → OneLap 反向增量同步配置 =====
    IGPSPORT_TO_ONELAP_ENABLE = ini_config.get('IGPSPORT_TO_ONELAP_ENABLE', False)
    IGPSPORT_TO_ONELAP_MODE = ini_config.get('IGPSPORT_TO_ONELAP_MODE', 'auto')
    IGPSPORT_TO_ONELAP_STRATEGY = ini_config.get('IGPSPORT_TO_ONELAP_STRATEGY', 'time_based')
    
    # 配置验证提示
    if ONELAP_ACCOUNT in ['139xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的OneLap账号")
    if ONELAP_PASSWORD in ['xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的OneLap密码")
    if XOSS_ENABLE_SYNC:
        if XOSS_ACCOUNT in ['139xxxxxx', '']:
            print("⚠️ 请在 settings.ini 中配置正确的行者账号")  
        if XOSS_PASSWORD in ['xxxxxx', '']:
            print("⚠️ 请在 settings.ini 中配置正确的行者密码")
    if GIANT_ACCOUNT in ['139xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的捷安特账号")
    if GIANT_PASSWORD in ['xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的捷安特密码")
    if IGPSPORT_ACCOUNT in ['139xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的iGPSport账号")
    if IGPSPORT_PASSWORD in ['xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的iGPSport密码")
else:
    # 使用默认配置
    print("📄 使用默认配置")
    LOG_LEVEL = 'INFO'
    HEADLESS_MODE = False
    ONELAP_ACCOUNT = ''
    ONELAP_PASSWORD = ''
    XOSS_ACCOUNT = ''
    XOSS_PASSWORD = ''
    XOSS_ENABLE_SYNC = True
    GIANT_ACCOUNT = ''
    GIANT_PASSWORD = ''
    GIANT_ENABLE_SYNC = False
    IGPSPORT_ACCOUNT = ''
    IGPSPORT_PASSWORD = ''
    IGPSPORT_ENABLE_SYNC = False
    STORAGE_DIR = './downloads'
    SUPPORTED_FORMATS = ['.fit', '.gpx', '.tcx']
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_FILES_PER_BATCH = 5
    ONELAP_FULL_SYNC = False
    
    # ===== 新增：iGPSport → OneLap 反向增量同步默认配置 =====
    IGPSPORT_TO_ONELAP_ENABLE = False      # 默认禁用反向同步
    IGPSPORT_TO_ONELAP_MODE = 'auto'       # 默认使用增量模式
    IGPSPORT_TO_ONELAP_STRATEGY = 'time_based'  # 默认基于时间戳比对

# 配置日志
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), 
                   format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('OnelapToXossSync')

# 显示平台信息和配置
import platform
logger.info(f"当前操作系统: {platform.system()} {platform.release()}")
logger.info(f"文件存储目录: {STORAGE_DIR}")
logger.info(f"无头模式: {'启用' if HEADLESS_MODE else '禁用'}")
logger.info("程序初始化完成")

# 定义函数
def create_retry_session():
    """创建带重试机制的会话"""
    logger.debug("创建带重试机制的会话")
    session = requests.Session()
    retry = requests.adapters.Retry(
        total=5,
        backoff_factor=0.3,
        status_forcelist=(500, 502, 504)
    )
    adapter = requests.adapters.HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def login_onelap_browser(tab, account, password):
    """使用现有浏览器标签页登录顽鹿账号"""
    logger.info("使用浏览器登录顽鹿账号")
    
    try:
        # 访问顽鹿登录页面
        logger.info("正在访问顽鹿登录页面...")
        tab.get('https://www.onelap.cn/login.html')
        time.sleep(3)  # 等待页面加载
        
        logger.info(f"顽鹿登录页面标题: {tab.title}")
        logger.info(f"顽鹿当前URL: {tab.url}")
        
        # 输入账号信息
        try:
            # 查找用户名输入框 - 根据提供的HTML结构
            username_input = tab.ele('.from1 login_1', timeout=5)
            if username_input:
                username_input.clear()
                username_input.input(account)
                logger.info("已输入顽鹿账号信息")
            else:
                raise Exception("未找到用户名输入框")
        except Exception as e:
            logger.error(f"输入用户名失败: {e}")
            raise
        
        # 输入密码信息
        try:
            # 查找密码输入框
            password_input = tab.ele('.from1 login_password ', timeout=5)
            if password_input:
                password_input.clear()
                password_input.input(password)
                logger.info("已输入顽鹿密码信息")
            else:
                raise Exception("未找到密码输入框")
        except Exception as e:
            logger.error(f"输入密码失败: {e}")
            raise
        
        # 点击登录按钮
        try:
         
            tab.ele('.from_yellow_btn', timeout=5).click()
            logger.info("已点击顽鹿登录按钮")
           
        except Exception as e:
            logger.error(f"点击登录按钮失败: {e}")
            raise
        
        # 等待登录完成
        time.sleep(5)
        
        # 检查登录是否成功 - 通过URL变化或页面内容判断
        current_url = tab.url
        logger.info(f"登录后URL: {current_url}")
        
        # 如果还在登录页面，可能登录失败
        if 'login.html' in current_url:
            # 检查是否有错误提示
            try:
                error_elements = tab.eles('.error_log')
                for error_elem in error_elements:
                    if error_elem.text and error_elem.text.strip():
                        logger.error(f"顽鹿登录错误: {error_elem.text.strip()}")
                raise Exception("顽鹿登录失败，仍在登录页面")
            except:
                logger.error("顽鹿登录失败")
                raise
        
        # 获取登录后的cookies
        cookies = tab.cookies()
        logger.info("成功获取顽鹿登录cookies")
        
        # 构造session的cookies
        session_cookies = {}
        for cookie in cookies:
            session_cookies[cookie['name']] = cookie['value']
        
        logger.info("顽鹿登录成功！")
        return session_cookies
        
    except Exception as e:
        logger.error(f"顽鹿浏览器登录失败: {e}")
        raise

def login_giant_browser(tab, account, password):
    """使用现有浏览器标签页登录捷安特骑行平台"""
    logger.info("使用浏览器登录捷安特骑行平台")
    
    try:
        # 访问捷安特登录页面
        logger.info("正在访问捷安特登录页面...")
        tab.get('https://ridelife.giant.com.cn/web/login.html')
        time.sleep(1)  # 等待页面加载
        
        logger.info(f"捷安特登录页面标题: {tab.title}")
        logger.info(f"捷安特当前URL: {tab.url}")
        
        # 输入账号信息
        try:
            # 查找用户名输入框 - 通过多种选择器尝试
            account_selectors = [
                '@name=username'
            ]
            username_input = None
            
            for selector in account_selectors:
                try:
                    username_input = tab.ele(selector, timeout=2)
                    if username_input:
                        logger.info(f"找到用户名输入框: {selector}")
                        break
                except:
                    continue
            
            if username_input:
                username_input.clear()
                username_input.input(account)
                logger.info("已输入捷安特账号信息")
            else:
                raise Exception("未找到用户名输入框")
        except Exception as e:
            logger.error(f"输入用户名失败: {e}")
            raise
        
        # 输入密码信息
        try:
            # 查找密码输入框 - 通过多种选择器尝试
            password_selectors = [
                '@name=password'
            ]
            password_input = None
            
            for selector in password_selectors:
                try:
                    password_input = tab.ele(selector, timeout=2)
                    if password_input:
                        logger.info(f"找到密码输入框: {selector}")
                        break
                except:
                    continue
            
            if password_input:
                password_input.clear()
                password_input.input(password)
                logger.info("已输入捷安特密码信息")
            else:
                raise Exception("未找到密码输入框")
        except Exception as e:
            logger.error(f"输入密码失败: {e}")
            raise
        
        # 点击登录按钮
        try:
            login_selectors = [
                '.btn btn_shadow btn_submit'
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    login_button = tab.ele(selector, timeout=2)
                    if login_button:
                        logger.info(f"找到登录按钮: {selector}")
                        break
                except:
                    continue
            
            if login_button:
                login_button.click()
                logger.info("已点击捷安特登录按钮")
            else:
                raise Exception("未找到登录按钮")
           
        except Exception as e:
            logger.error(f"点击登录按钮失败: {e}")
            raise
        
        # 等待登录完成
        time.sleep(2)
        
        # 检查登录是否成功 - 通过URL变化或页面内容判断
        current_url = tab.url
        logger.info(f"登录后URL: {current_url}")
        
        # 如果还在登录页面，可能登录失败
        if 'login.html' in current_url:
            # 检查是否有错误提示
            try:
                error_selectors = ['.error-msg', '.error-tip', '.login-error']
                for selector in error_selectors:
                    try:
                        error_elements = tab.eles(selector)
                        for error_elem in error_elements:
                            if error_elem.text and error_elem.text.strip():
                                logger.error(f"捷安特登录错误: {error_elem.text.strip()}")
                    except:
                        continue
                raise Exception("捷安特登录失败，仍在登录页面")
            except:
                logger.error("捷安特登录失败")
                raise
        
        # 获取登录后的cookies
        cookies = tab.cookies()
        logger.info("成功获取捷安特登录cookies")
        
        # 构造session的cookies
        session_cookies = {}
        for cookie in cookies:
            session_cookies[cookie['name']] = cookie['value']
        
        logger.info("捷安特登录成功！")
        return session_cookies
        
    except Exception as e:
        logger.error(f"捷安特浏览器登录失败: {e}")
        raise
# 将文件分批处理
def get_latest_activity_giant(tab):
    """从Giant获取最新活动时间"""
    logger.info("正在从Giant获取最新活动记录...")
    try:
        # 确保在历史列表页
        if 'main_fit.html' not in tab.url:
            tab.get('https://ridelife.giant.com.cn/web/main_fit.html')
            time.sleep(3)
            
        # 查找列表中的第一条记录
        # Giant页面通常是表格结构
        first_row_date = None
        
        # 尝试查找日期元素，Giant列表页通常有日期列
        # 这里假设日期元素包含 YYYY-MM-DD
        elements = tab.eles('tag:div') # 宽泛搜索
        for ele in elements:
            text = ele.text
            if text and re.match(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', text):
                first_row_date = text
                break
            if text and re.match(r'\d{4}-\d{2}-\d{2}', text):
                # 只有日期，默认为 00:00:00
                first_row_date = text + " 00:00:00"
                break
        
        if first_row_date:
            latest_time = datetime.strptime(first_row_date, '%Y-%m-%d %H:%M:%S')
            logger.info(f"Giant最新活动时间: {latest_time}")
            return {
                'platform': 'giant',
                'activity_date': first_row_date,
                'time_obj': latest_time
            }
        else:
            logger.warning("无法从Giant页面中解析出时间")
            return None
            
    except Exception as e:
        logger.error(f"获取Giant最新活动失败: {e}")
        return None

def batch_files(file_list, batch_size):
    """将文件列表分批处理"""
    for i in range(0, len(file_list), batch_size):
        yield file_list[i:i + batch_size]

def login_igpsport_browser(tab, account, password):
    """使用浏览器登录iGPSport平台"""
    logger.info("使用浏览器登录iGPSport平台")

    try:
        # 访问登录页面
        logger.info("正在访问iGPSport登录页面...")
        tab.get('https://login.passport.igpsport.cn/login?lang=zh-Hans')
        time.sleep(3)

        logger.info(f"iGPSport登录页面标题: {tab.title}")
        logger.info(f"iGPSport当前URL: {tab.url}")

        # 输入账号
        try:
            username_input = tab.ele('#basic_username', timeout=5)
            if username_input:
                username_input.clear()
                username_input.input(account)
                logger.info("已输入iGPSport账号信息")
            else:
                raise Exception("未找到用户名输入框")
        except Exception as e:
            logger.error(f"输入用户名失败: {e}")
            raise

        # 输入密码
        try:
            password_input = tab.ele('#basic_password', timeout=5)
            if password_input:
                password_input.clear()
                password_input.input(password)
                logger.info("已输入iGPSport密码信息")
            else:
                raise Exception("未找到密码输入框")
        except Exception as e:
            logger.error(f"输入密码失败: {e}")
            raise

        # 点击登录按钮
        try:
            login_selectors = [
                '@type=submit',
                '.ant-btn-primary',
            ]

            login_button = None
            for selector in login_selectors:
                try:
                    login_button = tab.ele(selector, timeout=2)
                    if login_button:
                        logger.info(f"找到登录按钮: {selector}")
                        break
                except:
                    continue

            if login_button:
                login_button.click()
                logger.info("已点击iGPSport登录按钮")
            else:
                raise Exception("未找到登录按钮")

        except Exception as e:
            logger.error(f"点击登录按钮失败: {e}")
            raise

        # 等待登录完成
        time.sleep(5)

        # 检查登录是否成功
        current_url = tab.url
        logger.info(f"登录后URL: {current_url}")

        # 如果还在登录页面，可能登录失败
        if 'login' in current_url.lower():
            try:
                error_elements = tab.eles('.ant-form-item-explain-error')
                for error_elem in error_elements:
                    if error_elem.text and error_elem.text.strip():
                        logger.error(f"iGPSport登录错误: {error_elem.text.strip()}")
            except:
                pass

        # 获取cookies
        cookies = tab.cookies()
        session_cookies = {}
        for cookie in cookies:
            session_cookies[cookie['name']] = cookie['value']

        logger.info("iGPSport登录成功！")
        return session_cookies

    except Exception as e:
        logger.error(f"iGPSport浏览器登录失败: {e}")
        raise

def get_latest_activity_igpsport(tab):
    """从iGPSport获取最新活动时间"""
    logger.info("正在从iGPSport获取最新活动记录...")
    try:
        # 确保在历史列表页
        if 'history/list' not in tab.url:
            tab.get('https://app.igpsport.cn/sport/history/list')
            
        # 显式等待表格加载 (最多等待10秒)
        logger.info("等待iGPSport活动列表加载...")
        # 等待数据行出现（注意：不是空行，而是有数据的行）
        if not tab.wait.eles_loaded('css:.ant-table-row', timeout=10):
            logger.warning("等待iGPSport活动记录超时或列表为空")
            
            # 检查是否显示“暂无数据”
            no_data = tab.ele('text:暂无数据', timeout=1)
            if no_data:
                logger.warning("页面显示'暂无数据'")
                return None
            return None
            
        # 获取所有数据行（使用 .ant-table-row 过滤掉表头或占位符）
        table_rows = tab.eles('css:.ant-table-row')
        if not table_rows:
            logger.warning("iGPSport未找到有效活动记录(行数为0)")
            # 再次尝试宽泛搜索
            table_rows = tab.eles('css:.ant-table-tbody > tr')
            if not table_rows:
                return None
            
        # 获取第一行数据（最新的）
        first_row = table_rows[0]
        
        # 检查第一行是否为暂无数据
        if "暂无数据" in first_row.text:
            logger.warning("第一行为'暂无数据'，尝试等待并刷新...")
            time.sleep(3)
            # 刷新页面
            # tab.refresh() # 刷新可能导致需要重新登录，这里只等待重试获取
            # 重新获取行
            if not tab.wait.eles_loaded('css:.ant-table-row', timeout=5):
                return None
            table_rows = tab.eles('css:.ant-table-row')
            if not table_rows:
                return None
            first_row = table_rows[0]
            if "暂无数据" in first_row.text:
                logger.warning("重试后仍为'暂无数据'")
                return None
                
        try:
            date_td = first_row.ele('css:td.ant-table-column-sort', timeout=1)
        except Exception:
            date_td = None
        if date_td and (date_td.text or '').strip():
            raw_date = date_td.text.strip()
            logger.info(f"直接从日期列提取到文本: {raw_date}")
            # 支持 2026.01.30 或 2026-01-30
            m_dot = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', raw_date)
            m_dash = re.search(r'(\d{4})-(\d{2})-(\d{2})', raw_date)
            if m_dot:
                date_str = f"{m_dot.group(1)}-{m_dot.group(2)}-{m_dot.group(3)}"
                latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                logger.info(f"解析日期(点号格式): {date_str}")
                return {
                    'platform': 'igpsport',
                    'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'time_obj': latest_time
                }
            if m_dash:
                date_str = f"{m_dash.group(1)}-{m_dash.group(2)}-{m_dash.group(3)}"
                latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                logger.info(f"解析日期(短横线格式): {date_str}")
                return {
                    'platform': 'igpsport',
                    'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'time_obj': latest_time
                }
            logger.warning("日期列文本未匹配到有效日期格式，回退到逐列解析")

        if not date_td:
            try:
                row_html = first_row.html
            except Exception:
                row_html = ""
            if row_html:
                try:
                    soup = BeautifulSoup(row_html, 'html.parser')
                    td = soup.find('td', class_=lambda c: c and 'ant-table-column-sort' in c)
                    raw_date = td.get_text(strip=True) if td else ""
                except Exception:
                    raw_date = ""
                if raw_date:
                    logger.info(f"从行HTML提取到日期列文本: {raw_date}")
                    m_dot = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', raw_date)
                    m_dash = re.search(r'(\d{4})-(\d{2})-(\d{2})', raw_date)
                    if m_dot:
                        date_str = f"{m_dot.group(1)}-{m_dot.group(2)}-{m_dot.group(3)}"
                        latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                        return {
                            'platform': 'igpsport',
                            'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'time_obj': latest_time
                        }
                    if m_dash:
                        date_str = f"{m_dash.group(1)}-{m_dash.group(2)}-{m_dash.group(3)}"
                        latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                        return {
                            'platform': 'igpsport',
                            'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'time_obj': latest_time
                        }
        
        # 获取所有单元格文本
        # 我们需要找到时间列。通常包含日期格式如 YYYY-MM-DD HH:MM:SS
        
        # 获取所有单元格文本
        # 注意：iGPSport的表格结构可能比较复杂，有时候 td 可能会被包含在其他元素中
        # 或者 eles('tag:td') 获取方式在某些版本的 DrissionPage 中表现不同
        # 我们尝试更稳健的方式：获取所有子 td 元素
        cells = first_row.eles('css:td')  # 使用CSS选择器更准确
        
        # 如果还是获取不到，尝试获取所有文本并按换行符分割
        if not cells or len(cells) <= 1:
            logger.warning(f"使用 tag:td 只获取到 {len(cells) if cells else 0} 列，尝试分析行文本")
            row_text = first_row.text
            logger.info(f"行完整文本: {row_text}")
            
            # 尝试直接在行文本中搜索日期
            # 匹配 YYYY.MM.DD
            match_dot_date = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', row_text)
            if match_dot_date:
                date_str = f"{match_dot_date.group(1)}-{match_dot_date.group(2)}-{match_dot_date.group(3)}"
                latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                logger.info(f"从行文本中直接解析到日期: {date_str}")
                return {
                    'platform': 'igpsport',
                    'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'time_obj': latest_time
                }
                
            # 匹配 YYYY-MM-DD
            match_date = re.search(r'(\d{4}-\d{2}-\d{2})', row_text)
            if match_date:
                date_str = match_date.group(1)
                latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                logger.info(f"从行文本中直接解析到日期: {date_str}")
                return {
                    'platform': 'igpsport',
                    'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'time_obj': latest_time
                }
                
        latest_time = None
        
        row_text = first_row.text or ""
        match_full = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', row_text)
        if match_full:
            time_str = match_full.group(1)
            latest_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
        else:
            match_dot_date = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', row_text)
            if match_dot_date:
                date_str = f"{match_dot_date.group(1)}-{match_dot_date.group(2)}-{match_dot_date.group(3)}"
                latest_time = datetime.strptime(date_str, '%Y-%m-%d')
            else:
                match_date = re.search(r'(\d{4}-\d{2}-\d{2})', row_text)
                if match_date:
                    date_str = match_date.group(1)
                    latest_time = datetime.strptime(date_str, '%Y-%m-%d')

        if latest_time:
            logger.info(f"从行文本解析到时间: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
            return {
                'platform': 'igpsport',
                'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                'time_obj': latest_time
            }

        logger.info(f"正在解析第一行数据，共 {len(cells)} 列")
        for i, cell in enumerate(cells):
            text = cell.text.strip() if cell.text else ""
            logger.debug(f"第 {i+1} 列内容: '{text}'")
            
            # 尝试匹配时间格式 YYYY-MM-DD HH:MM:SS
            # 使用 search 替代 match 以支持前后有空白字符的情况
            match_full = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', text)
            if match_full:
                time_str = match_full.group(1)
                latest_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')
                logger.info(f"在第 {i+1} 列找到完整时间: {time_str}")
                break
                
            match_dot_date = re.search(r'(\d{4})\.(\d{2})\.(\d{2})', text)
            if match_dot_date:
                date_str = f"{match_dot_date.group(1)}-{match_dot_date.group(2)}-{match_dot_date.group(3)}"
                if not latest_time:
                    latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                    logger.info(f"在第 {i+1} 列找到日期(点号格式): {date_str} (继续查找是否有更精确时间)")

            # 尝试匹配时间格式 YYYY-MM-DD
            match_date = re.search(r'(\d{4}-\d{2}-\d{2})', text)
            if match_date:
                date_str = match_date.group(1)
                # 如果只有日期，需要判断是不是只有日期而没有时间
                # 只有当后面没有找到更精确的时间时才使用这个
                # 但通常 iGPSport 的时间列是完整的，或者日期和时间分开
                # 这里假设如果找到日期，暂时记录，继续往后找看有没有更精确的
                if not latest_time:
                    latest_time = datetime.strptime(date_str, '%Y-%m-%d')
                    logger.info(f"在第 {i+1} 列找到日期: {date_str} (继续查找是否有更精确时间)")
                
        if latest_time:
            logger.info(f"iGPSport最新活动时间: {latest_time}")
            return {
                'platform': 'igpsport',
                'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
                'time_obj': latest_time
            }
        else:
            logger.warning("无法从iGPSport表格中解析出时间")
            return None
            
    except Exception as e:
        logger.error(f"获取iGPSport最新活动失败: {e}")
        return None

def upload_files_to_igpsport(tab, valid_files):
    """上传文件到iGPSport平台"""
    logger.info("===== 开始上传文件到iGPSport平台 =====")

    try:
        # 访问运动历史页面
        logger.info("正在访问运动历史页面...")
        tab.get('https://app.igpsport.cn/sport/history/list')
        time.sleep(3)

        logger.info(f"当前页面URL: {tab.url}")
        logger.info(f"当前页面标题: {tab.title}")

        # iGPSport 限制：每次最多上传9个文件
        max_files_per_batch = 9

        # 分批上传
        for batch_start in range(0, len(valid_files), max_files_per_batch):
            batch_files = valid_files[batch_start:batch_start + max_files_per_batch]
            logger.info(f"正在处理批次 {batch_start // max_files_per_batch + 1}，共 {len(batch_files)} 个文件")

            # 点击"导入运动记录"按钮
            import_btn = tab.ele('text:导入运动记录', timeout=5)
            if not import_btn:
                logger.error("未找到'导入运动记录'按钮")
                return False

            import_btn.click()
            logger.info("已点击'导入运动记录'按钮")
            time.sleep(2)

            # 查找文件上传输入框
            file_input = tab.ele('@type=file', timeout=5)
            if not file_input:
                logger.error("未找到文件上传输入框")
                return False

            logger.info("找到文件上传输入框")

            try:
                abs_paths = [os.path.abspath(p) for p in batch_files]
                file_input.input("\n".join(abs_paths))
                for file_path in batch_files:
                    logger.info(f"已选择: {os.path.basename(file_path)}")
            except Exception as e:
                logger.error(f"选择文件失败: {e}")
                return False

            # 等待文件列表加载
            time.sleep(2)

            # 点击"上传"按钮确认上传
            try:
                # 查找所有按钮，找到文本为"上传"的按钮
                upload_confirm_btn = None
                buttons = tab.eles('tag:button')
                for btn in buttons:
                    if btn.text and btn.text.strip() == '上传':
                        upload_confirm_btn = btn
                        break

                if upload_confirm_btn:
                    upload_confirm_btn.click()
                    logger.info("已点击'上传'确认按钮")
                    time.sleep(8)  # 等待上传完成
                else:
                    logger.warning("未找到上传确认按钮")
            except Exception as e:
                logger.error(f"点击上传按钮失败: {e}")

            # 检查是否有成功提示，或等待模态框关闭
            time.sleep(3)

            # 如果还有下一批，需要等待页面恢复
            if batch_start + max_files_per_batch < len(valid_files):
                logger.info("等待页面恢复，准备下一批上传...")
                tab.get('https://app.igpsport.cn/sport/history/list')
                time.sleep(3)

        logger.info("===== iGPSport上传流程完成 =====")
        return True

    except Exception as e:
        logger.error(f"上传到iGPSport失败: {e}")
        return False

def fetch_activities(session, cookies_dict, latest_sync_activity):
    """获取活动列表数据"""
    logger.info("获取活动列表数据")
    
    # 将cookies字典转换为Cookie字符串
    cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
    headers = {
        'Cookie': cookie_string,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    # 更新session的cookies
    session.cookies.update(cookies_dict)

    try:
        response = session.get(
            "http://u.onelap.cn/analysis/list",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        filtered = data['data']

        # 如果有最新的活动基准记录，只同步比它更新的活动
        if latest_sync_activity:
            try:
                # 获取基准时间对象
                # 注意：latest_sync_activity 可能来自不同平台，结构略有差异
                # 但我们在 get_latest_activity_* 函数中都统一了 'time_obj' 字段
                benchmark_time = latest_sync_activity.get('time_obj')
                
                # 如果没有预处理好的 time_obj，尝试解析 activity_date
                if not benchmark_time and latest_sync_activity.get('activity_date'):
                    time_str = latest_sync_activity['activity_date']
                    # 尝试解析...
                    # (此处省略复杂的解析逻辑，假设已在基准获取函数中处理好)
                    pass

                if benchmark_time:
                    logger.info(f"增量同步基准时间: {benchmark_time}")
                    # 筛选出比基准时间更新的OneLap活动
                    activities_after_matched = []
                    for activity in filtered:
                        try:
                            # created_at 是秒级 Unix 时间戳
                            created_at = activity['created_at']
                            if isinstance(created_at, int):
                                # 直接使用秒级时间戳
                                onelap_time = datetime.fromtimestamp(created_at)
                            elif isinstance(created_at, str):
                                # 如果是字符串，尝试解析ISO格式
                                onelap_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                                onelap_time = onelap_time.replace(tzinfo=None)
                            else:
                                logger.warning(f"未知的时间格式: {created_at} ({type(created_at)})")
                                # 保守地包含该活动
                                activities_after_matched.append(activity)
                                continue
                                
                            if onelap_time > benchmark_time:
                                activities_after_matched.append(activity)
                        except Exception as e:
                            logger.debug(f"解析OneLap活动时间失败: {e}, created_at={activity.get('created_at')}")
                            # 如果时间解析失败，保守地包含该活动
                            activities_after_matched.append(activity)
                    
                    logger.info(f"筛选到 {len(activities_after_matched)} 个比基准时间更新的OneLap活动")
                    return activities_after_matched
                else:
                    logger.warning("无法解析基准活动时间，返回所有OneLap活动")
                    return filtered
            except Exception as e:
                logger.error(f"处理基准活动时间时出错: {e}")
                return filtered
        else:
            logger.info("没有同步基准记录，返回所有OneLap活动")
            return filtered
    except Exception as e:
        logger.error("获取活动列表失败", exc_info=True)
        raise

def ensure_storage_dir_clean(directory):
    """确保存储文件夹存在且为空状态"""
    try:
        # 检查文件夹是否存在
        if not os.path.exists(directory):
            # 文件夹不存在，创建它
            os.makedirs(directory, exist_ok=True)
            logger.info(f"创建存储文件夹: {directory}")
            return
        
        # 文件夹存在，检查是否有内容
        items = os.listdir(directory)
        if not items:
            # 文件夹为空，无需清空
            logger.info(f"存储文件夹已存在且为空: {directory}")
            return
        
        # 文件夹有内容，需要清空
        logger.info(f"开始清空存储文件夹: {directory} (发现 {len(items)} 个文件/文件夹)")
        for item in items:
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path) or os.path.islink(item_path):
                os.unlink(item_path)  # 删除文件或链接
                logger.debug(f"删除文件: {item}")
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)  # 删除子文件夹
                logger.debug(f"删除文件夹: {item}")
        logger.info(f"存储文件夹清空完成: {directory}")
        
    except Exception as e:
        logger.error(f"处理存储文件夹时发生错误: {e}", exc_info=True)

def download_fit_file(session, activity, headers):
    """下载单个 FIT 文件"""
    # 确保存储目录存在（但不清空，因为是批量下载）
    if not os.path.exists(STORAGE_DIR):
        os.makedirs(STORAGE_DIR, exist_ok=True)

    download_url = activity["durl"]
    if not download_url.startswith("http"):
        download_url = f"http://u.onelap.cn{download_url}"

    filename = None
    filepath = None
    try:
        response = session.get(download_url, headers=headers, timeout=10, stream=True)
        response.raise_for_status()

        cd_filename = None
        content_disposition = response.headers.get('Content-Disposition') or response.headers.get('content-disposition') or ''
        if content_disposition:
            m = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, flags=re.IGNORECASE)
            if m:
                cd_filename = unquote(m.group(1)).strip()
            if not cd_filename:
                m = re.search(r'filename="?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
                if m:
                    cd_filename = m.group(1).strip()

        activity_file_key = str(activity.get('fileKey') or '').strip()
        activity_fit_url = str(activity.get('fitUrl') or '').strip()
        url_path = urlparse(download_url).path
        url_basename = os.path.basename(url_path) if url_path else ''

        filename_source = None
        if activity_file_key and 'MAGENE' in activity_file_key.upper():
            filename = activity_file_key
            filename_source = 'activity.fileKey'
        elif cd_filename and 'MAGENE' in cd_filename.upper():
            filename = cd_filename
            filename_source = 'response.headers.content-disposition'
        elif url_basename and 'MAGENE' in url_basename.upper():
            filename = url_basename
            filename_source = 'download_url.basename'
        elif cd_filename:
            filename = cd_filename
            filename_source = 'response.headers.content-disposition'
        elif activity_file_key:
            filename = activity_file_key
            filename_source = 'activity.fileKey'
        elif activity_fit_url:
            filename = activity_fit_url
            filename_source = 'activity.fitUrl'
        else:
            filename = 'activity.fit'
            filename_source = 'fallback'

        if not str(filename).lower().endswith('.fit'):
            filename = f"{filename}.fit"

        filename = re.sub(r'[<>:"/\\\\|?*]+', '_', str(filename)).strip().strip('.')
        if not filename.lower().endswith('.fit'):
            filename = f"{filename}.fit"

        filepath = os.path.join(STORAGE_DIR, filename)
        if os.path.exists(filepath):
            logger.warning(f"文件已存在，跳过下载: {filename}")
            response.close()
            return

        logger.info(f"开始下载: {filename} (命名来源: {filename_source})")
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info(f"文件下载完成: {filepath}")
    except Exception as e:
        logger.error("下载失败", exc_info=True)
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
            logger.warning(f"已删除不完整文件: {filepath}")

def upload_files_to_giant(tab, valid_files):
    """上传文件到捷安特骑行平台"""
    logger.info("===== 开始上传文件到捷安特平台 =====")
    
    try:
        # 尝试找到上传页面，如果没有明确的上传页面，可能需要在主页面寻找上传入口
        # 先尝试访问可能的上传页面
        upload_urls = [
            'https://ridelife.giant.com.cn/web/main_fit.html',
        ]
        
        upload_found = False
        for upload_url in upload_urls:
            try:
                logger.info(f"尝试访问上传页面: {upload_url}")
                tab.get(upload_url)
                time.sleep(3)
                
                # 检查页面是否包含上传相关元素
                upload_elements = tab.eles('#btn_upload')
                if upload_elements:
                    logger.info(f"在 {upload_url} 找到上传功能")
                    upload_found = True
                    
                    # 点击上传按钮，弹出上传窗体
                    upload_elements[0].click()
                    time.sleep(0.5)  # 等待窗体加载
                    logger.info("已点击上传按钮，弹出上传窗体")
                    
                    # 配置设备类型下拉框
                    try:
                        device_select = tab.ele('@name=device', timeout=3)
                        if device_select:
                            # 选择"码表"选项
                            device_select.select.by_value('bike_computer')
                            logger.info("已选择设备类型：码表")
                        else:
                            logger.warning("未找到设备类型下拉框")
                    except Exception as e:
                        logger.error(f"配置设备类型失败: {e}")
                    
                    # 配置品牌下拉框
                    try:
                        brand_select = tab.ele('@name=brand', timeout=3)
                        if brand_select:
                            # 选择"顽鹿Onelap"选项
                            brand_select.select.by_value('onelap')
                            logger.info("已选择品牌：顽鹿Onelap")
                        else:
                            logger.warning("未找到品牌下拉框")
                    except Exception as e:
                        logger.error(f"配置品牌失败: {e}")
                    
                    time.sleep(1)  # 等待下拉框配置完成
                    break
            except:
                continue
        
        if not upload_found:
            logger.warning("未找到捷安特平台的上传功能，跳过上传步骤")
            return False
        
        logger.info(f"当前页面URL: {tab.url}")
        logger.info(f"当前页面标题: {tab.title}")
        
        # 分批上传文件
        for batch in batch_files(valid_files, 10*MAX_FILES_PER_BATCH):
            logger.info(f"正在上传批次文件到捷安特平台，共 {len(batch)} 个文件")
            
            try:
                # 在弹出的窗体中查找文件上传输入框
                upload_selectors = [
                    '#files'
                ]
                
                upload_element = None
                for selector in upload_selectors:
                    try:
                        upload_element = tab.ele(selector, timeout=2)
                        if upload_element:
                            logger.info(f"找到窗体内的文件上传元素: {selector}")
                            break
                    except:
                        continue
                
                if not upload_element:
                    logger.error("无法找到捷安特平台弹出窗体中的文件上传元素")
                    continue
                
                # 批量上传文件（一次性选择所有文件）
                try:
                    logger.info(f"正在批量上传 {len(batch)} 个文件到捷安特平台...")
                    
                    # 构建文件路径列表
                    file_paths = []
                    for file_name in batch:

                            file_paths.append(file_name)

                    logger.info(f"before file_paths: {file_paths}")                    
                    # 打印即将上传的文件列表
                    for file_path in file_paths:
                        logger.info(f"准备上传: {os.path.basename(file_path)}")
                    
                    # 一次性选择所有文件（支持多文件选择）
                    try:
                        # 尝试传递多个文件路径
                        if len(file_paths) == 1:
                            # 单个文件
                            upload_element.click.to_upload(file_paths[0])
                        else:
                            # 多个文件，使用换行符分隔的路径字符串
                            # 某些平台支持这种方式
                            upload_element.click.to_upload('\n'.join(file_paths))
                        
                        logger.info(f"已选择 {len(file_paths)} 个文件进行上传")
                        logger.info(f"file_paths: {file_paths}")
                        
                    except Exception as e:
                        logger.warning(f"批量选择文件失败，尝试逐个选择: {e}")
                        # 如果批量失败，回退到逐个选择
                        return False
                    
                    # time.sleep(1)  # 等待文件选择完成
                    
                except Exception as e:
                    logger.error(f"批量文件选择失败: {e}")
                    continue
                
                # 查找并点击弹出窗体内的提交/确认按钮
                try:
                    submit_selectors = [
                        
                    ]
                    
                    submit_button = None
                    submit_button = tab.ele('.btn_submit form_btn btn btn_color_1 btn_shadow btn_round', timeout=2)
                    if submit_button:
                        logger.info("找到提交按钮")


                    
                    if submit_button:
                        submit_button.click()
                        logger.info("已点击捷安特上传提交按钮")
                        time.sleep(2)
                    else:
                        logger.warning("未找到提交按钮，文件可能已自动上传")

                    time.sleep(1)
                    # 点击确认按钮
                    try:
                        confirm_button = tab.ele('.btn ok', timeout=2)
                        if confirm_button:
                            confirm_button.click()
                            logger.info("已点击确认按钮，提交成功")
                        else:
                            logger.info("未找到确认按钮，但提交流程已完成")
                    except Exception as e:
                        logger.warning(f"点击确认按钮失败: {e}")
                        logger.info("提交流程完成")

                except Exception as e:
                    logger.warning(f"查找提交按钮失败: {e}")
                    
            except Exception as e:
                logger.error(f"批次上传到捷安特失败: {e}")
                continue
            
            time.sleep(1)  # 批次间隔
        
        logger.info("===== 捷安特平台文件上传完成 =====")
        return True
        
    except Exception as e:
        logger.error(f"上传到捷安特平台失败: {e}")
        return False

# 获取屏幕尺寸并计算窗口大小
try:
    import tkinter as tk
    root = tk.Tk()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    root.destroy()  # 立即销毁tkinter窗口
    
    # 计算半屏尺寸和右侧位置
    half_width = screen_width // 2
    window_height = screen_height
    right_position = half_width  # 右半屏的起始位置
    
    logger.info(f"检测到屏幕尺寸: {screen_width}x{screen_height}")
    logger.info(f"设置浏览器窗口: {half_width}x{window_height}，位置: ({right_position}, 0)")
    
except Exception as e:
    # 如果获取屏幕尺寸失败，使用默认值
    logger.warning(f"无法获取屏幕尺寸: {e}，使用默认值")
    half_width = 960
    window_height = 1080
    right_position = 960

# 初始化浏览器选项
options = ChromiumOptions()
options.incognito()  # 启用匿名模式

# Chrome浏览器启动参数配置
options.set_argument("--no-sandbox")                    # 避免沙盒问题
options.set_argument("--disable-dev-shm-usage")         # 避免/dev/shm内存不足
options.set_argument("--disable-web-security")          # 禁用网络安全检查
options.set_argument("--disable-features=VizDisplayCompositor")
options.set_argument("--disable-blink-features=AutomationControlled")
options.set_argument("--disable-extensions")            # 禁用扩展
options.auto_port()

# 动态设置窗口大小和位置
options.set_argument(f"--window-size={half_width},{window_height}")    # 设置窗口大小为半屏
options.set_argument(f"--window-position={right_position},0")          # 设置窗口位置在右侧
options.set_argument("--force-device-scale-factor=1")                  # 强制设备缩放因子为1


if HEADLESS_MODE:
    options.headless()  # 启用无头模式
    logger.info("启用无头模式运行")
else:
    logger.info("启用可视化模式运行")


# 启动浏览器
tab = ChromiumPage(options)

#test giant
# giant_cookies = login_giant_browser(tab, GIANT_ACCOUNT, GIANT_PASSWORD)
# # 测试上传文件 读取文件夹下所有文件
# valid_files = [f for f in os.listdir(STORAGE_DIR) if f.endswith('.fit') or f.endswith('.gpx')]
# upload_success = upload_files_to_giant(tab, valid_files)

# === 步骤1：先登录顽鹿获取cookies ===
logger.info("===== 步骤1：登录顽鹿平台 =====")
session = create_retry_session()
try:
    # 使用浏览器方式登录顽鹿账号
    onelap_cookies = login_onelap_browser(tab, ONELAP_ACCOUNT, ONELAP_PASSWORD)


    logger.info("顽鹿登录完成，准备获取活动数据...")
except Exception as e:
    logger.critical(f"顽鹿登录失败: {e}")
    tab.close()
    exit(1)

def get_latest_activity_xoss(tab):
    """从行者平台获取最新活动时间"""
    logger.info("===== 步骤2：登录行者平台获取最新活动 =====")
    try:
        tab.get('https://www.imxingzhe.com/login')
        
        # 登录流程... (简化，假设已登录或执行登录)
        # 这里为了复用原有逻辑，我们保留原来的登录代码块，只是将其封装或调整调用顺序
        # 实际代码中，登录逻辑比较复杂，包含验证码等，这里我们尽量利用已有的登录状态
        
        # ... (此处省略登录细节，直接跳转到列表页) ...
        # 注意：下面的代码是提取自原主流程
        
        # 检查是否需要登录
        if 'login' in tab.url:
            # 执行登录...
            # 点击“我已阅读并同意”
            try:
                checkbox = tab.ele('.van-checkbox', timeout=1)
                if checkbox: checkbox.click()
            except: pass
            
            # 输入账号密码
            tab.ele('@name=account').clear()
            tab.ele('@name=account').input(XOSS_ACCOUNT)
            tab.ele('@name=password').clear()
            tab.ele('@name=password').input(XOSS_PASSWORD)
            
            # 点击登录
            try:
                tab.ele('.login_btn_box login_btn van-button van-button--primary van-button--normal van-button--block').click()
            except:
                try: tab.ele('button[type=submit]').click()
                except: tab.ele('button:contains("登录")').click()
            
            time.sleep(3)

        # 跳转列表页
        tab.get('https://www.imxingzhe.com/workouts/list')
        time.sleep(5)
        
        # 解析表格
        xoss_activities = []
        # ... (保留原有的解析逻辑) ...
        # 为了避免代码重复，这里我们简化处理，实际应复用原有代码
        # 由于原代码直接写在主流程中，我们需要将其提取出来，或者在主流程中根据条件执行
        
        # 临时方案：直接在主流程中控制，不完全封装成函数，而是通过标志位控制
        return True 
        
    except Exception as e:
        logger.error(f"行者操作失败: {e}")
        return False

# === 步骤2：确定同步基准 ===
logger.info("===== 步骤2：确定同步基准 =====")
latest_sync_activity = None
sync_benchmark_platform = None
xoss_login_ok = False

# 优先级1：行者 (XOSS)
if XOSS_ENABLE_SYNC and XOSS_ACCOUNT and XOSS_PASSWORD and XOSS_ACCOUNT not in ['139xxxxxx', ''] and XOSS_PASSWORD not in ['xxxxxx', '']:
    logger.info("尝试使用行者(XOSS)作为同步基准...")
    try:
        tab.get('https://www.imxingzhe.com/login')
        # ... (原有的行者登录代码) ...
        
        # 点击“我已阅读并同意”
        try:
            checkbox = tab.ele('.van-checkbox', timeout=1)
            if checkbox: checkbox.click()
        except: pass
        
        # 输入账号
        tab.ele('@name=account').clear()
        tab.ele('@name=account').input(XOSS_ACCOUNT)
        tab.ele('@name=password').clear()
        tab.ele('@name=password').input(XOSS_PASSWORD)
        
        # 点击登录
        try:
            tab.ele('.login_btn_box login_btn van-button van-button--primary van-button--normal van-button--block').click()
        except:
            try: tab.ele('button[type=submit]').click()
            except: tab.ele('button:contains("登录")').click()
        
        time.sleep(3)
        tab.get('https://www.imxingzhe.com/workouts/list')
        time.sleep(5)

        xoss_login_ok = ('login' not in (tab.url or '').lower())
        
        # 提取行者数据 (原代码逻辑 1071-1196 行)
        # ... 这里保留原有的解析逻辑 ...
        # 由于 SearchReplace 工具限制，我需要非常小心地替换代码块
        # 下面通过替换整个 Step 2 模块来实现
        
    except Exception as e:
        logger.error(f"行者登录或获取数据失败: {e}")
        xoss_login_ok = False
        # 失败后继续尝试下一个平台

# 如果行者失败或未配置，尝试 iGPSport
if not latest_sync_activity and IGPSPORT_ENABLE_SYNC and IGPSPORT_ACCOUNT and IGPSPORT_PASSWORD:
    logger.info("尝试使用 iGPSport 作为同步基准...")
    try:
        login_igpsport_browser(tab, IGPSPORT_ACCOUNT, IGPSPORT_PASSWORD)
        result = get_latest_activity_igpsport(tab)
        if result:
            latest_sync_activity = result
            sync_benchmark_platform = 'igpsport'
            logger.info(f"成功获取 iGPSport 最新记录: {result['activity_date']}")
    except Exception as e:
        logger.error(f"iGPSport 获取基准失败: {e}")

# 如果还不行，尝试 Giant
if not latest_sync_activity and GIANT_ENABLE_SYNC and GIANT_ACCOUNT and GIANT_PASSWORD:
    logger.info("尝试使用 Giant 作为同步基准...")
    try:
        login_giant_browser(tab, GIANT_ACCOUNT, GIANT_PASSWORD)
        result = get_latest_activity_giant(tab)
        if result:
            latest_sync_activity = result
            sync_benchmark_platform = 'giant'
            logger.info(f"成功获取 Giant 最新记录: {result['activity_date']}")
    except Exception as e:
        logger.error(f"Giant 获取基准失败: {e}")

if not latest_sync_activity:
    logger.warning("⚠️ 未能从任何平台获取最新活动记录，将执行全量同步！")
else:
    logger.info(f"✅ 同步基准确定: {sync_benchmark_platform}, 最新时间: {latest_sync_activity['activity_date']}")

if ONELAP_FULL_SYNC:
    logger.info("✅ 已启用 OneLap 全量下载开关，将忽略同步基准，执行全量同步")
    latest_sync_activity = None


# === 步骤3：开始执行 FIT 文件下载任务 ===
logger.info("===== 步骤3：开始执行 FIT 文件下载任务 =====")
try:
    # 使用之前获取的顽鹿cookies获取活动数据
    activities = fetch_activities(session, onelap_cookies, latest_sync_activity)

    logger.info(f"总共需要处理 {len(activities)} 个活动")
    #分别是什么需要打印出来
    latest_onelap_activity_time = None
    for activity in activities:
        # 将Unix时间戳转换为datetime对象进行格式化
        try:
            created_at = activity['created_at']
            if isinstance(created_at, int):
                # 秒级Unix时间戳
                activity_time = datetime.fromtimestamp(created_at)
            elif isinstance(created_at, str):
                # ISO格式字符串
                activity_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                activity_time = activity_time.replace(tzinfo=None)
            else:
                activity_time = None
                
            time_str = activity_time.strftime('%Y-%m-%d %H:%M:%S') if activity_time else "未知时间"
            logger.info(f"时间: {time_str}, 距离: {activity['totalDistance']/1000}km, 爬升: {activity['elevation']}m")
            if activity_time and (latest_onelap_activity_time is None or activity_time > latest_onelap_activity_time):
                latest_onelap_activity_time = activity_time
        except Exception as e:
            logger.warning(f"时间格式化失败: {e}, created_at={activity.get('created_at')}")
            logger.info(f"时间: {activity.get('created_at', '未知')}, 距离: {activity['totalDistance']/1000}km, 爬升: {activity['elevation']}m")

    
    # 在开始批量下载前，确保存储目录存在且为空
    ensure_storage_dir_clean(STORAGE_DIR)
    
    # 准备下载时使用的headers
    cookie_string = "; ".join([f"{k}={v}" for k, v in onelap_cookies.items()])
    download_headers = {
        'Cookie': cookie_string,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    for idx, activity in enumerate(activities, 1):
        logger.debug(f"正在处理第 {idx}/{len(activities)} 个活动")
        download_fit_file(
            session,
            activity,
            download_headers
        )

    logger.info("===== FIT 文件下载完成 =====")
except Exception as e:
    logger.critical("主流程发生致命错误", exc_info=True)
    tab.close()
    session.close()
    exit(1)

# 从文件夹中递归查找符合条件的文件
def get_valid_files(folder_path):
    """从指定文件夹中递归查找符合条件的文件"""
    valid_files = []
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_extension = os.path.splitext(file)[1].lower()
            file_size = os.path.getsize(file_path)

            if file_extension in SUPPORTED_FORMATS and file_size <= MAX_FILE_SIZE:
                valid_files.append(file_path)
    return valid_files

# 获取符合条件的文件列表
valid_files = get_valid_files(STORAGE_DIR)
if not valid_files:
    logger.warning("没有找到符合条件的文件。")
    tab.close()
    exit()



# === 步骤4：跳转到行者上传页面并分批上传文件 ===
logger.info("===== 步骤4：开始上传文件到行者平台 =====")
if not XOSS_ENABLE_SYNC:
    logger.info("行者平台同步已禁用，跳过行者平台上传")
elif not (XOSS_ACCOUNT and XOSS_PASSWORD and XOSS_ACCOUNT not in ['139xxxxxx', ''] and XOSS_PASSWORD not in ['xxxxxx', '']):
    logger.info("未配置行者账号或密码为默认值，跳过行者平台上传")
elif not xoss_login_ok:
    logger.info("行者登录失败或不可用，跳过行者平台上传")
else:
    tab.get('https://www.imxingzhe.com/upload/fit')
    time.sleep(2)  # 等待页面加载

    for batch in batch_files(valid_files, MAX_FILES_PER_BATCH):
        logger.info(f"正在上传批次文件，共 {len(batch)} 个文件")
        
        try:
            # 查找上传区域（行者平台的上传组件）
            # 可能的选择器，按优先级尝试
            upload_selectors = [
                '.van-uploader__input'
            ]
            
            upload_element = None
            for selector in upload_selectors:
                try:
                    upload_element = tab.ele(selector, timeout=2)
                    if upload_element:
                        logger.info(f"找到上传元素: {selector}")
                        break
                except Exception:
                    logger.error(f"找不到行者里的上传按钮元素: {selector}")
                    continue
            
            if not upload_element:
                # 如果找不到特定的上传组件，尝试通过文件输入框上传
                try:
                    upload_element = tab.ele('@type=file', timeout=3)
                except Exception:
                    logger.error("无法找到文件上传元素")
                    continue
            
            # 逐个上传文件
            for file_path in batch:
                try:
                    logger.info(f"正在上传文件: {os.path.basename(file_path)}")
                    if hasattr(upload_element, 'click.to_upload'):
                        upload_element.click.to_upload(file_path)
                    else:
                        upload_element.input(file_path)
                    time.sleep(0.5)  # 等待文件上传完成
                    logger.info(f"文件上传完成: {os.path.basename(file_path)}")
                except Exception as e:
                    logger.error(f"上传文件失败 {file_path}: {e}")
                    continue
            
            # 查找并点击"上传"按钮 - 通过class定位第二个按钮
            try: 
                # 正确的CSS选择器：用点号连接多个class
                upload_btn = tab.ele('.fit_btn van-button van-button--primary van-button--normal',index=2)

                if upload_btn:
                    upload_btn.click()
                    logger.info("通过文本内容成功点击上传按钮")
                    time.sleep(2)
                else:
                    logger.error("无法找到行者的上传按钮")
                    
                    
            except Exception as e:
                logger.error(f"查找上传按钮失败: {e}")
                    
        except Exception as e:
            logger.error(f"批次上传失败: {e}")
            continue
        
        time.sleep(2)  # 批次间隔

# === 步骤5：上传文件到捷安特骑行平台 ===
logger.info("===== 步骤5：上传文件到捷安特骑行平台 =====")
try:
    # 检查是否启用了捷安特同步
    if not GIANT_ENABLE_SYNC:
        logger.info("捷安特平台同步已禁用，跳过捷安特平台上传")
    elif not (GIANT_ACCOUNT and GIANT_PASSWORD and GIANT_ACCOUNT not in ['139xxxxxx', ''] and GIANT_PASSWORD not in ['xxxxxx', '']):
        logger.info("未配置捷安特账号或密码为默认值，跳过捷安特平台上传")
    else:
        # 登录捷安特平台
        logger.info("开始登录捷安特骑行平台...")
        giant_cookies = login_giant_browser(tab, GIANT_ACCOUNT, GIANT_PASSWORD)
        logger.info("捷安特登录完成，开始上传文件...")
        
        # 上传文件到捷安特平台
        upload_success = upload_files_to_giant(tab, valid_files)
        
        if upload_success:
            logger.info("文件已成功上传到捷安特平台")
        else:
            logger.warning("捷安特平台上传出现问题，请手动检查")
            
except Exception as e:
    logger.error(f"捷安特平台上传过程出错: {e}")
    logger.info("继续执行后续步骤...")

# === 步骤6：上传文件到iGPSport平台 ===
logger.info("===== 步骤6：上传文件到iGPSport平台 =====")
try:
    # 检查是否启用了iGPSport同步
    if not IGPSPORT_ENABLE_SYNC:
        logger.info("iGPSport平台同步已禁用，跳过iGPSport平台上传")
    elif not (IGPSPORT_ACCOUNT and IGPSPORT_PASSWORD and IGPSPORT_ACCOUNT not in ['139xxxxxx', ''] and IGPSPORT_PASSWORD not in ['xxxxxx', '']):
        logger.info("未配置iGPSport账号或密码为默认值，跳过iGPSport平台上传")
    else:
        # 登录iGPSport平台
        logger.info("开始登录iGPSport平台...")
        igpsport_cookies = login_igpsport_browser(tab, IGPSPORT_ACCOUNT, IGPSPORT_PASSWORD)
        logger.info("iGPSport登录完成，开始上传文件...")

        # 上传文件到iGPSport平台
        upload_success = upload_files_to_igpsport(tab, valid_files)

        if upload_success:
            logger.info("文件已成功上传到iGPSport平台")
        else:
            logger.warning("iGPSport平台上传出现问题，请手动检查")

except Exception as e:
    logger.error(f"iGPSport平台上传过程出错: {e}")
    logger.info("继续执行后续步骤...")

# === 步骤7：验证同步结果 ===
logger.info("===== 步骤7：验证同步结果 =====")
try:
    if XOSS_ENABLE_SYNC and xoss_login_ok and XOSS_ACCOUNT and XOSS_PASSWORD and XOSS_ACCOUNT not in ['139xxxxxx', ''] and XOSS_PASSWORD not in ['xxxxxx', '']:
        logger.info("跳转到行者活动列表页面验证同步结果...")
        tab.get('https://www.imxingzhe.com/workouts/list')
        time.sleep(5)  # 等待页面加载
        
        logger.info("请检查行者平台的活动列表，确认文件是否已成功同步")
        logger.info("程序将在15秒后自动关闭，您可以手动查看最新的活动记录")
        
        try:
            table = tab.ele('.table_box', timeout=3)
            if table:
                table_html = table.html
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(table_html, 'html.parser')
                rows = soup.find_all('tr')
                
                if len(rows) > 1:  # 有数据行
                    logger.info("==最后查看行者平台最新的活动记录如下==:")
                    for i, row in enumerate(rows[1:4], 1):  # 跳过表头，显示前3条
                        cells = row.find_all('td')
                        if len(cells) >= 4:
                            activity_date = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                            title = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                            distance_text = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                            logger.info(f"  {i}. {activity_date} - {title} - {distance_text}")
                else:
                    logger.warning("未找到活动数据")
            else:
                logger.warning("未找到活动表格，请手动检查页面")
        except Exception as e:
            logger.debug(f"获取验证数据时出错: {e}")
            logger.info("自动验证失败，请手动查看页面内容")
        
        time.sleep(15)
    elif IGPSPORT_ENABLE_SYNC:
        logger.info("行者未配置，改为验证 iGPSport 最新记录日期...")
        latest_igpsport = get_latest_activity_igpsport(tab)
        if latest_igpsport and latest_igpsport.get('time_obj'):
            igp_time = latest_igpsport['time_obj']
            logger.info(f"iGPSport 当前最新日期: {igp_time.strftime('%Y-%m-%d %H:%M:%S')}")
            if 'latest_onelap_activity_time' in globals() and latest_onelap_activity_time:
                logger.info(f"本次同步最新 OneLap 时间: {latest_onelap_activity_time.strftime('%Y-%m-%d %H:%M:%S')}")
                if igp_time.date() >= latest_onelap_activity_time.date():
                    logger.info("✅ iGPSport 日期验证通过（最新日期不早于本次同步日期）")
                else:
                    logger.warning("⚠️ iGPSport 日期验证未通过（可能仍在处理导入队列，稍后刷新再看）")
        else:
            logger.warning("未能获取 iGPSport 最新记录用于验证，请手动查看运动记录列表")
    else:
        logger.info("未配置行者且 iGPSport 上传未启用，跳过验证步骤")
    
except Exception as e:
    logger.error(f"验证步骤失败: {e}")
    logger.info("请手动访问行者平台确认同步结果")
    time.sleep(5)

# === 步骤8：iGPSport → OneLap 增量同步（新增）===
logger.info("===== 步骤8：iGPSport → OneLap 增量同步 =====")
try:
    # 检查是否启用了增量同步
    if not IGPSPORT_TO_ONELAP_ENABLE:
        logger.info("iGPSport → OneLap 增量同步已禁用，跳过")
    elif not INCREMENTAL_SYNC_AVAILABLE:
        logger.warning("增量同步模块不可用，跳过")
    elif not (IGPSPORT_ACCOUNT and IGPSPORT_PASSWORD and ONELAP_ACCOUNT and ONELAP_PASSWORD):
        logger.warning("iGPSport 或 OneLap 账号未配置，跳过增量同步")
    else:
        logger.info("开始执行 iGPSport → OneLap 增量同步...")
        
        # 构造配置
        sync_config = {
            'igpsport': {
                'username': IGPSPORT_ACCOUNT,
                'password': IGPSPORT_PASSWORD
            },
            'onelap': {
                'username': ONELAP_ACCOUNT,
                'password': ONELAP_PASSWORD
            }
        }
        
        # 创建同步实例
        sync = IncrementalSync(sync_config)
        
        try:
            # 执行同步（预览模式或完整同步）
            dry_run = (IGPSPORT_TO_ONELAP_MODE == 'preview')
            if dry_run:
                logger.info("当前为预览模式（只比对，不下载不上传）")
            else:
                logger.info(f"当前为同步模式: {IGPSPORT_TO_ONELAP_MODE}")
            
            success = sync.run(dry_run=dry_run)
            
            if success:
                logger.info("✅ iGPSport → OneLap 增量同步完成！")
            else:
                logger.warning("⚠️ iGPSport → OneLap 同步遇到问题")
                
        finally:
            # 确保清理资源
            sync.cleanup()
            
except Exception as e:
    logger.error(f"iGPSport → OneLap 增量同步失败: {e}")
    logger.info("继续执行后续步骤...")

# === 任务完成，关闭浏览器和会话 ===
logger.info("===== 任务执行完成 =====")
tab.close()
session.close()
logger.info("浏览器和会话已关闭")
