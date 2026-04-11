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
from urllib.parse import unquote, urlparse, quote
import threading
import webbrowser
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

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
        cfg['STRAVA_ENABLE_SYNC'] = config.getboolean('strava', 'enable_sync', fallback=False)
        cfg['STRAVA_CLIENT_ID'] = config.get('strava', 'client_id', fallback='').strip()
        cfg['STRAVA_CLIENT_SECRET'] = config.get('strava', 'client_secret', fallback='').strip()
        cfg['STRAVA_ACCESS_TOKEN'] = config.get('strava', 'access_token', fallback='').strip()
        cfg['STRAVA_REFRESH_TOKEN'] = config.get('strava', 'refresh_token', fallback='').strip()
        cfg['STRAVA_EXPIRES_AT'] = config.getint('strava', 'expires_at', fallback=0)
        cfg['STRAVA_REDIRECT_PORT'] = config.getint('strava', 'redirect_port', fallback=8765)
        cfg['STRAVA_ATHLETE_ID'] = config.get('strava', 'athlete_id', fallback='').strip()
        cfg['STRAVA_ATHLETE_NAME'] = config.get('strava', 'athlete_name', fallback='').strip()
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
    STRAVA_ENABLE_SYNC = ini_config.get('STRAVA_ENABLE_SYNC', False)
    STRAVA_CLIENT_ID = ini_config.get('STRAVA_CLIENT_ID', '')
    STRAVA_CLIENT_SECRET = ini_config.get('STRAVA_CLIENT_SECRET', '')
    STRAVA_ACCESS_TOKEN = ini_config.get('STRAVA_ACCESS_TOKEN', '')
    STRAVA_REFRESH_TOKEN = ini_config.get('STRAVA_REFRESH_TOKEN', '')
    STRAVA_EXPIRES_AT = ini_config.get('STRAVA_EXPIRES_AT', 0)
    STRAVA_REDIRECT_PORT = ini_config.get('STRAVA_REDIRECT_PORT', 8765)
    STRAVA_ATHLETE_ID = ini_config.get('STRAVA_ATHLETE_ID', '')
    STRAVA_ATHLETE_NAME = ini_config.get('STRAVA_ATHLETE_NAME', '')
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
    STRAVA_ENABLE_SYNC = False
    STRAVA_CLIENT_ID = ''
    STRAVA_CLIENT_SECRET = ''
    STRAVA_ACCESS_TOKEN = ''
    STRAVA_REFRESH_TOKEN = ''
    STRAVA_EXPIRES_AT = 0
    STRAVA_REDIRECT_PORT = 8765
    STRAVA_ATHLETE_ID = ''
    STRAVA_ATHLETE_NAME = ''
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

CONFIG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'settings.ini')
STRAVA_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'strava_upload_state.json')

# 标记独立命令模式；真正执行放到 run_strava_auth_flow 定义之后，但仍早于主同步流程
STRAVA_AUTH_MODE = '--strava-auth' in sys.argv
STRAVA_TOKEN_REFRESH_MARGIN = 3600


def save_strava_config(updates, config_file=CONFIG_FILE_PATH):
    """将 Strava token/配置写回 settings.ini"""
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8-sig')
    if not config.has_section('strava'):
        config.add_section('strava')
    for key, value in updates.items():
        config.set('strava', key, str(value))
    with open(config_file, 'w', encoding='utf-8') as f:
        config.write(f)


def build_strava_redirect_uri(port=8765):
    return f'http://127.0.0.1:{port}/callback'


def build_strava_auth_url(client_id, port=8765):
    redirect_uri = build_strava_redirect_uri(port)
    scope = 'activity:write,activity:read_all'
    return (
        'https://www.strava.com/oauth/authorize'
        f'?client_id={client_id}'
        '&response_type=code'
        f'&redirect_uri={quote(redirect_uri, safe="")}'
        '&approval_prompt=auto'
        f'&scope={quote(scope, safe=",")}'
    )


def exchange_strava_code_for_token(client_id, client_secret, code):
    response = requests.post(
        'https://www.strava.com/api/v3/oauth/token',
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code'
        },
        timeout=20
    )
    response.raise_for_status()
    return response.json()


# 定义函数
def extract_datetimes_from_text(text):
    if not text:
        return []

    normalized = text.replace('\xa0', ' ').replace('/', '-').replace('.', '-')
    normalized = normalized.replace('年', '-').replace('月', '-').replace('日', ' ')
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    patterns = [
        (r'20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}:\d{2}', '%Y-%m-%d %H:%M:%S'),
        (r'20\d{2}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}', '%Y-%m-%d %H:%M'),
        (r'20\d{2}-\d{1,2}-\d{1,2}', '%Y-%m-%d')
    ]

    results = []
    seen = set()
    for pattern, fmt in patterns:
        for match in re.findall(pattern, normalized):
            try:
                parsed = datetime.strptime(match, fmt)
                key = parsed.strftime('%Y-%m-%d %H:%M:%S')
                if key not in seen:
                    seen.add(key)
                    results.append(parsed)
            except Exception:
                continue
    return results

def parse_xoss_latest_activity_from_html(page_html):
    if not page_html:
        return None

    soup = BeautifulSoup(page_html, 'html.parser')
    table_box = soup.select_one('.table_box')
    if table_box:
        rows = table_box.select('tr')
        for row in rows:
            cells = row.select('td')
            if not cells:
                continue
            row_text = ' '.join(cell.get_text(' ', strip=True) for cell in cells).strip()
            if not row_text:
                continue
            parsed_times = extract_datetimes_from_text(row_text)
            if parsed_times:
                first_time = parsed_times[0]
                return {
                    'activity_date': first_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'time_obj': first_time,
                    'source_text': row_text
                }

    page_text = soup.get_text(' ', strip=True)
    compact_text = re.sub(r'\s+', ' ', page_text)
    mobile_patterns = [
        r'(20\d{2}-\d{2}-\d{2}-(?:上午|下午|晚上|中午|凌晨)?-[^ ]+?)\s+\d+(?:\.\d+)?\s*公里',
        r'(20\d{2}-\d{2}-\d{2}-(?:上午|下午|晚上|中午|凌晨)?-[^ ]+?)\s+\d+(?:\.\d+)?\s*km'
    ]

    for pattern in mobile_patterns:
        match = re.search(pattern, compact_text)
        if not match:
            continue
        row_text = match.group(0)
        parsed_times = extract_datetimes_from_text(match.group(1))
        if parsed_times:
            first_time = parsed_times[0]
            return {
                'activity_date': first_time.strftime('%Y-%m-%d %H:%M:%S'),
                'time_obj': first_time,
                'source_text': row_text
            }

    candidate_texts = []
    seen_texts = set()

    selectors = [
        '.table_box tr',
        'table tr',
        '[class*="table"] tr',
        '[class*="list"] tr',
        '[class*="workout"] tr',
        '[class*="record"] tr',
        '[class*="workout"] [class*="item"]',
        '[class*="record"] [class*="item"]',
        '[class*="list"] [class*="item"]',
        '[class*="workout"] [class*="card"]',
        '[class*="record"] [class*="card"]',
        '[class*="list"] li',
        '[class*="workout"] li',
        '[class*="record"] li'
    ]

    for selector in selectors:
        for node in soup.select(selector):
            text = node.get_text(' ', strip=True)
            if not text or text in seen_texts:
                continue
            if '20' not in text:
                continue
            if len(text) > 160:
                continue
            if text.count('Created with Sketch') >= 1:
                continue
            if text.count('@2x') >= 2 or text.count('@3x') >= 2:
                continue
            if text.count('|') >= 6:
                continue
            if any(keyword in text for keyword in ['用户协议', '隐私条款', '帮助中心', '商城', '联系客服']):
                continue
            if text and text not in seen_texts:
                seen_texts.add(text)
                candidate_texts.append(text)

    latest_time = None
    latest_text = None
    for text in candidate_texts[:80]:
        for parsed in extract_datetimes_from_text(text):
            if latest_time is None or parsed > latest_time:
                latest_time = parsed
                latest_text = text

    if latest_time is None:
        return None

    return {
        'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
        'time_obj': latest_time,
        'source_text': latest_text
    }

def wait_xoss_activity_page_ready(tab, timeout=12):
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            page_html = tab.html or ''
            if 'table_box' in page_html and re.search(r'20\d{2}-\d{2}-\d{2}', page_html):
                return True
        except Exception:
            pass
        try:
            if tab.ele('css:.table_box', timeout=1):
                return True
        except Exception:
            pass
        try:
            rows = tab.eles('tag:tr')
            if rows and len(rows) > 1:
                return True
        except Exception:
            pass
        try:
            cards = tab.eles('css:[class*="workout"] [class*="item"], [class*="record"] [class*="item"], [class*="list"] [class*="item"]')
            if cards:
                return True
        except Exception:
            pass
        try:
            if tab.ele('text:暂无数据', timeout=1):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def is_xoss_login_page(tab):
    try:
        current_url = (tab.url or '').lower()
    except Exception:
        current_url = ''

    try:
        page_title = (tab.title or '').strip()
    except Exception:
        page_title = ''

    if 'login' in current_url:
        return True
    if '登录' in page_title:
        return True

    try:
        has_account = bool(tab.ele('@name=account', timeout=1))
        has_password = bool(tab.ele('@name=password', timeout=1))
        if has_account and has_password:
            return True
    except Exception:
        pass

    return False

def click_xoss_login_button(tab):
    selectors = [
        'css:button.login_btn_box.login_btn.van-button.van-button--primary.van-button--normal.van-button--block',
        'css:button[type="submit"]',
        'text:登录'
    ]
    for selector in selectors:
        try:
            btn = tab.ele(selector, timeout=2)
            if btn:
                btn.click()
                return selector
        except Exception:
            continue

    try:
        for btn in tab.eles('tag:button'):
            btn_text = (btn.text or '').strip()
            if '登录' in btn_text:
                btn.click()
                return f'tag:button:{btn_text}'
    except Exception:
        pass

    return None

def wait_xoss_login_success(tab, timeout=12):
    end_time = time.time() + timeout
    while time.time() < end_time:
        if not is_xoss_login_page(tab):
            return True
        try:
            current_url = (tab.url or '').lower()
            current_title = (tab.title or '').strip()
            if 'dashboard' in current_url or '运动能力' in current_title:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def get_xoss_latest_activity_from_logged_in_tab(tab):
    try:
        tab.get('https://www.imxingzhe.com/workouts/list')
        logger.info("[DEBUG] 已请求行者活动列表页")
        wait_xoss_activity_page_ready(tab, timeout=20)

        for attempt in range(4):
            page_html = tab.html or ''
            parsed = parse_xoss_latest_activity_from_html(page_html)
            if parsed:
                return parsed
            if attempt == 1:
                tab.get('https://www.imxingzhe.com/workouts/list')
            time.sleep(2)
        return None
    except Exception as e:
        logger.warning(f"[DEBUG] 行者当前页面基准提取失败: {e}")
        return None

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
        current_url = tab.url or ''
        # 如果已经在主页/运动记录页，直接复用登录态
        if ('app.igpsport.cn/user/home' in current_url) or ('app.igpsport.cn/sport/record' in current_url):
            logger.info(f"检测到 iGPSport 已登录态，直接复用当前会话: {current_url}")
            session_cookies = {}
            try:
                cookies = tab.cookies()
                for cookie in cookies:
                    session_cookies[cookie['name']] = cookie['value']
            except Exception:
                pass
            return session_cookies

        # 如果已经在 app.igpsport.cn 域下且不是登录页，也认为优先复用，再交给后续页面跳转处理
        if 'app.igpsport.cn/' in current_url and '/login' not in current_url:
            logger.info(f"检测到 iGPSport 应用内页面，尝试复用登录态: {current_url}")
            session_cookies = {}
            try:
                cookies = tab.cookies()
                for cookie in cookies:
                    session_cookies[cookie['name']] = cookie['value']
            except Exception:
                pass
            return session_cookies

        # 访问登录页面
        logger.info("正在访问iGPSport登录页面...")
        tab.get('https://login.passport.igpsport.cn/login?lang=zh-Hans')
        time.sleep(3)

        logger.info(f"iGPSport登录页面标题: {tab.title}")
        logger.info(f"iGPSport当前URL: {tab.url}")

        # 显式切到“密码登录”tab（如果存在）
        try:
            pwd_tab = tab.ele('text:密码登录', timeout=2)
            if pwd_tab:
                pwd_tab.click()
                logger.info("已切换到iGPSport密码登录")
                time.sleep(0.5)
        except Exception:
            pass

        # 输入账号
        try:
            username_selectors = [
                '#username',
                '#basic_username',
                '@id=username',
                '@name=username',
                '@type=text',
                '@placeholder=请输入正确的手机号/邮箱'
            ]
            username_input = None
            for selector in username_selectors:
                try:
                    username_input = tab.ele(selector, timeout=2)
                    if username_input:
                        logger.info(f"找到iGPSport用户名输入框: {selector}")
                        break
                except Exception:
                    continue
            if username_input:
                username_input.click()
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
            password_selectors = [
                '#password',
                '#basic_password',
                '@id=password',
                '@name=password',
                '@type=password',
                '@placeholder=请输入密码'
            ]
            password_input = None
            for selector in password_selectors:
                try:
                    password_input = tab.ele(selector, timeout=2)
                    if password_input:
                        logger.info(f"找到iGPSport密码输入框: {selector}")
                        break
                except Exception:
                    continue
            if password_input:
                password_input.click()
                password_input.clear()
                password_input.input(password)
                logger.info("已输入iGPSport密码信息")
            else:
                raise Exception("未找到密码输入框")
        except Exception as e:
            logger.error(f"输入密码失败: {e}")
            raise

        # 监听登录请求
        try:
            tab.listen.start('service/auth/account/login')
        except Exception as e:
            logger.warning(f"iGPSport登录监听启动失败: {e}")

        # 点击登录按钮
        try:
            login_selectors = [
                '@type=submit',
                '.submit',
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
                login_button.click(by_js=False)
                logger.info("已点击iGPSport登录按钮")
            else:
                raise Exception("未找到登录按钮")

        except Exception as e:
            logger.error(f"点击登录按钮失败: {e}")
            raise

        # 优先根据登录接口响应判断成功
        login_ok = False
        session_cookies = {}
        try:
            packets = list(tab.listen.steps(timeout=8))
            for pkt in packets:
                try:
                    if 'service/auth/account/login' not in pkt.url:
                        continue
                    body = getattr(pkt.response, 'body', None)
                    if isinstance(body, dict) and body.get('code') == 0 and body.get('data', {}).get('access_token'):
                        token_type = body['data'].get('token_type', 'Bearer')
                        access_token = body['data'].get('access_token')
                        refresh_token = body['data'].get('refresh_token')
                        # 写入 localStorage，兼容前端基于 token 的登录态
                        try:
                            tab.run_js(f"localStorage.setItem('token_type', {token_type!r});")
                            tab.run_js(f"localStorage.setItem('access_token', {access_token!r});")
                            if refresh_token:
                                tab.run_js(f"localStorage.setItem('refresh_token', {refresh_token!r});")
                        except Exception as e:
                            logger.warning(f"写入iGPSport localStorage失败: {e}")
                        session_cookies = {
                            'token_type': token_type,
                            'access_token': access_token,
                        }
                        if refresh_token:
                            session_cookies['refresh_token'] = refresh_token
                        login_ok = True
                        logger.info("iGPSport登录接口返回成功，已获取 access_token")
                        break
                except Exception as e:
                    logger.debug(f"处理iGPSport登录响应失败: {e}")
        except Exception as e:
            logger.warning(f"读取iGPSport登录监听结果失败: {e}")

        # 等待页面状态稳定
        time.sleep(2)
        current_url = tab.url
        logger.info(f"登录后URL: {current_url}")

        # 如接口未判定成功，再退回 cookies/URL 检查
        if not login_ok:
            try:
                cookies = tab.cookies()
                for cookie in cookies:
                    session_cookies[cookie['name']] = cookie['value']
                if session_cookies and 'login' not in current_url.lower():
                    login_ok = True
            except Exception:
                pass

        if not login_ok:
            try:
                error_elements = tab.eles('.ant-form-item-explain-error')
                for error_elem in error_elements:
                    if error_elem.text and error_elem.text.strip():
                        logger.error(f"iGPSport登录错误: {error_elem.text.strip()}")
            except:
                pass
            raise Exception("iGPSport登录请求已发送，但未建立可用登录态")

        logger.info("iGPSport登录成功！")
        return session_cookies

    except Exception as e:
        logger.error(f"iGPSport浏览器登录失败: {e}")
        raise

def get_latest_activity_igpsport(tab):
    """从iGPSport获取最新活动时间"""
    logger.info("正在从iGPSport获取最新活动记录...")
    try:
        # 确保在运动记录页（新版 iGPSport 使用 /sport/record）
        if '/sport/record' not in tab.url:
            tab.get('https://app.igpsport.cn/sport/record')
            
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
        # 访问运动记录页面
        logger.info("正在访问iGPSport运动记录页面...")
        if '/user/home' in tab.url:
            logger.info("当前在主页，点击'运动记录'进入记录页面")
            try:
                tab.ele('text:运动记录', timeout=3).click()
                time.sleep(4)
            except Exception as e:
                logger.error(f"点击'运动记录'按钮失败: {e}")
                raise
        elif '/sport/record' not in tab.url:
            logger.info("直接访问运动记录页面")
            tab.get('https://app.igpsport.cn/sport/record')
            time.sleep(4)
        else:
            logger.info("已在运动记录页面")

        logger.info(f"当前页面URL: {tab.url}")
        logger.info(f"当前页面标题: {tab.title}")

        # iGPSport 限制：每次最多上传9个文件
        max_files_per_batch = 9
        logger.info("定位导入按钮和文件输入框")

        # 找到并点击“导入运动记录”按钮
        import_btn = tab.ele('text:导入运动记录', timeout=5)
        logger.info(f"导入按钮类型: {import_btn.tag}")
        import_btn.click(by_js=True)
        logger.info("导入按钮点击成功，等待模态框加载")
        time.sleep(4)

        # 等待模态框内容出现
        try:
            batch_ele = tab.ele('text:批量导入运动', timeout=5)
            logger.info("批量导入运动模态框加载成功")
        except Exception as e:
            logger.error(f"模态框加载失败: {e}")
            raise

        # 在模态框中找到隐藏的文件输入框
        file_input = None

        # 优先用 CSS 选择器直接定位（更可靠）
        for selector in ['css:input[type="file"]', 'css:input[name="file"]', 'tag:input']:
            try:
                logger.info(f"尝试用选择器定位文件输入框: {selector}")
                if selector.startswith('css:'):
                    ele = tab.ele(selector, timeout=2)
                else:
                    eles = tab.eles(selector)
                    ele = None
                    # 遍历所有 input，找符合条件的
                    for e in eles:
                        try:
                            e_type = e.attr('type') or ''
                            e_name = e.attr('name') or ''
                            e_accept = e.attr('accept') or ''
                            if e_type == 'file' or e_name == 'file' or '.fit' in e_accept:
                                ele = e
                                logger.info(f"在 input 列表中找到符合条件的元素")
                                break
                        except:
                            continue
                if ele:
                    # 验证一下这个元素
                    e_type = ele.attr('type') or ''
                    e_name = ele.attr('name') or ''
                    e_accept = ele.attr('accept') or ''
                    e_style = ele.attr('style') or ''
                    logger.info(f"找到文件输入框: type={e_type}, name={e_name}, accept={e_accept}")
                    # 如果是隐藏的，通过 JavaScript 显示它
                    if e_style and 'display: none' in e_style:
                        logger.info("检测到输入框是隐藏的，通过 JavaScript 显示")
                        ele.run_js('this.style.display="block"; this.style.visibility="visible"; this.style.opacity="1"; this.style.zIndex="9999";')
                    file_input = ele
                    break
            except Exception as e:
                logger.debug(f"选择器 {selector} 定位失败: {e}")
                continue

        if not file_input:
            raise Exception("未找到iGPSport文件上传输入框")

        logger.info(f"文件输入框找到，是否隐藏: {('display: none' in (file_input.attr('style') or ''))}")

        # 分批上传
        for batch_start in range(0, len(valid_files), max_files_per_batch):
            batch_files = valid_files[batch_start:batch_start + max_files_per_batch]
            logger.info(f"正在处理批次 {batch_start // max_files_per_batch + 1}，共 {len(batch_files)} 个文件")

            try:
                # 处理隐藏输入框
                tab.run_js("""
                const el = document.querySelector('input[name="file"]');
                if (el) { el.style.display = 'block'; el.style.visibility = 'visible'; el.style.opacity = '1'; el.style.zIndex = '9999'; }
                """)
                logger.info("已处理隐藏输入框")
                time.sleep(0.5)
            except Exception as e:
                logger.debug(f"修改输入框样式失败: {e}")

            # 直接使用file_input引用（避免再次查找）
            if not file_input:
                raise Exception("未找到iGPSport文件输入框")

            try:
                abs_paths = [os.path.abspath(p) for p in batch_files]
                file_input.input("\n".join(abs_paths))
                logger.info(f"文件选择成功，共 {len(batch_files)} 个")
                for file_path in batch_files:
                    logger.info(f"  - {os.path.basename(file_path)}")
            except Exception as e:
                logger.error(f"iGPSport选择文件失败: {e}")
                return False

            # 等待文件列表加载
            time.sleep(2)

            # 点击“确认/上传”按钮完成最终提交
            try:
                upload_confirm_btn = None
                candidate_texts = ['确认', '上传']
                button_candidates = []

                # 优先在按钮元素中查找
                for selector in ['tag:button', 'tag:div', 'tag:span']:
                    try:
                        for ele in tab.eles(selector):
                            text = (ele.text or '').strip()
                            if text:
                                button_candidates.append((selector, text, ele))
                                if text in candidate_texts:
                                    upload_confirm_btn = ele
                                    logger.info(f"命中最终确认元素: selector={selector}, text={text}")
                                    break
                        if upload_confirm_btn:
                            break
                    except Exception:
                        continue

                if not upload_confirm_btn:
                    preview = [f"{sel}:{txt}" for sel, txt, _ in button_candidates[:20]]
                    logger.warning(f"未找到最终确认按钮（确认/上传）。当前候选元素文本: {preview}")
                    return False

                try:
                    upload_confirm_btn.click(by_js=True)
                except Exception:
                    upload_confirm_btn.click()
                logger.info("已点击最终确认按钮（确认/上传）")
                time.sleep(8)  # 等待上传开始/处理
            except Exception as e:
                logger.error(f"点击最终确认按钮失败: {e}")
                return False

            # 检查是否有成功提示，或等待模态框关闭
            time.sleep(3)

            # 如果还有下一批，需要等待页面恢复
            if batch_start + max_files_per_batch < len(valid_files):
                logger.info("等待页面恢复，准备下一批上传...")
                tab.get('https://app.igpsport.cn/sport/record')
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


def update_ini_config_values(config_file="settings.ini", section="strava", updates=None):
    """更新 INI 配置文件中的指定字段"""
    if not updates:
        return
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8-sig')
    if not config.has_section(section):
        config.add_section(section)
    for key, value in updates.items():
        config.set(section, key, '' if value is None else str(value))
    with open(config_file, 'w', encoding='utf-8') as f:
        config.write(f)


def build_strava_auth_url(client_id, redirect_uri, scope='activity:write,activity:read_all'):
    state = hashlib.md5(f"{client_id}-{time.time()}".encode('utf-8')).hexdigest()[:12]
    url = (
        f"https://www.strava.com/oauth/authorize?client_id={quote(str(client_id))}"
        f"&response_type=code"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
        f"&approval_prompt=auto"
        f"&scope={quote(scope)}"
        f"&state={state}"
    )
    return url, state


def exchange_strava_code_for_token(client_id, client_secret, code):
    resp = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code'
        },
        timeout=20
    )
    resp.raise_for_status()
    return resp.json()


def refresh_strava_token_if_needed(config_file='settings.ini'):
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8-sig')
    if not config.has_section('strava'):
        raise Exception('未找到 [strava] 配置节')

    enabled = config.getboolean('strava', 'enable_sync', fallback=False)
    if not enabled:
        return None

    client_id = config.get('strava', 'client_id', fallback='').strip()
    client_secret = config.get('strava', 'client_secret', fallback='').strip()
    access_token = config.get('strava', 'access_token', fallback='').strip()
    refresh_token = config.get('strava', 'refresh_token', fallback='').strip()
    expires_at = config.getint('strava', 'expires_at', fallback=0)

    if not client_id or not client_secret:
        raise Exception('Strava client_id/client_secret 未配置')
    if not refresh_token:
        raise Exception('Strava refresh_token 未配置，请先执行 --strava-auth')

    now_ts = int(time.time())
    if access_token and expires_at and expires_at > now_ts + 3600:
        return access_token

    logger.info('[Strava] access_token 缺失或即将过期，开始刷新')
    resp = requests.post(
        'https://www.strava.com/oauth/token',
        data={
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        },
        timeout=20
    )
    resp.raise_for_status()
    data = resp.json()

    athlete = data.get('athlete') or {}
    update_ini_config_values(config_file, 'strava', {
        'access_token': data.get('access_token', ''),
        'refresh_token': data.get('refresh_token', refresh_token),
        'expires_at': data.get('expires_at', 0),
        'athlete_id': athlete.get('id', ''),
        'athlete_name': athlete.get('username') or athlete.get('firstname') or ''
    })
    logger.info('[Strava] token 刷新成功')
    return data.get('access_token', '')


def poll_strava_upload_status(upload_id, access_token, timeout_seconds=60):
    headers = {'Authorization': f'Bearer {access_token}'}
    end_at = time.time() + timeout_seconds
    last_data = None
    while time.time() < end_at:
        resp = requests.get(f'https://www.strava.com/api/v3/uploads/{upload_id}', headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        last_data = data
        status_text = str(data.get('status', '') or '')
        error_text = str(data.get('error', '') or '')
        activity_id = data.get('activity_id') or data.get('id')
        if error_text and error_text.lower() not in ['none', 'null', '']:
            raise Exception(f'Strava 上传失败: {error_text}')
        if data.get('activity_id'):
            return data
        if 'ready' in status_text.lower() and not data.get('activity_id'):
            return data
        time.sleep(2)
    return last_data


def load_strava_upload_state(state_file=STRAVA_STATE_FILE):
    try:
        if os.path.exists(state_file):
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f'[Strava] 读取去重状态失败: {e}')
    return {}


def save_strava_upload_state(state, state_file=STRAVA_STATE_FILE):
    try:
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f'[Strava] 保存去重状态失败: {e}')


def build_strava_file_signature(file_path):
    stat = os.stat(file_path)
    return f"{os.path.basename(file_path)}|{stat.st_size}|{int(stat.st_mtime)}"


def upload_file_to_strava(file_path, access_token):
    headers = {'Authorization': f'Bearer {access_token}'}
    external_id = os.path.basename(file_path)
    with open(file_path, 'rb') as f:
        resp = requests.post(
            'https://www.strava.com/api/v3/uploads',
            headers=headers,
            data={
                'data_type': 'fit',
                'sport_type': 'Ride',
                'external_id': external_id,
            },
            files={'file': (os.path.basename(file_path), f, 'application/octet-stream')},
            timeout=60
        )
    resp.raise_for_status()
    data = resp.json()
    if data.get('error'):
        raise Exception(f"Strava 上传接口返回错误: {data.get('error')}")
    return data


def classify_strava_error(err_text):
    text = (err_text or '').lower()
    if 'duplicate of' in text:
        return 'duplicate', '检测到重复活动，已跳过'
    if '401' in text or 'unauthorized' in text or 'access token' in text:
        return 'auth', '授权失效或 token 不可用，请重新执行 --strava-test / --strava-auth'
    if '403' in text or 'scope' in text or 'permission' in text:
        return 'permission', '权限不足，请确认 Strava 授权包含 activity:write'
    if 'malformed' in text or 'unprocessable' in text or 'invalid' in text:
        return 'file', '活动文件格式异常，Strava 无法处理该 FIT 文件'
    if 'rate limit' in text or '429' in text or 'too many requests' in text:
        return 'rate_limit', '请求过于频繁，稍后再试'
    return 'unknown', err_text


def get_latest_activity_strava(config_file='settings.ini'):
    access_token = refresh_strava_token_if_needed(config_file)
    if not access_token:
        return None
    headers = {'Authorization': f'Bearer {access_token}'}
    resp = requests.get('https://www.strava.com/api/v3/athlete/activities?per_page=1&page=1', headers=headers, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    latest = data[0]
    time_str = latest.get('start_date_local') or latest.get('start_date')
    if not time_str:
        return None
    latest_time = datetime.fromisoformat(time_str.replace('Z', '+00:00')).replace(tzinfo=None)
    return {
        'platform': 'strava',
        'activity_date': latest_time.strftime('%Y-%m-%d %H:%M:%S'),
        'time_obj': latest_time
    }


def upload_files_to_strava(valid_files, config_file='settings.ini'):
    if not valid_files:
        logger.info('[Strava] 没有可上传文件，跳过')
        return {'ok': True, 'success': 0, 'skipped': 0, 'failed': 0}
    access_token = refresh_strava_token_if_needed(config_file)
    if not access_token:
        logger.info('[Strava] 未启用或 token 不可用，跳过')
        return {'ok': False, 'success': 0, 'skipped': 0, 'failed': len(valid_files)}
    state = load_strava_upload_state()
    success_count = 0
    skipped_count = 0
    failed_count = 0
    for file_path in valid_files:
        try:
            signature = build_strava_file_signature(file_path)
            state_item = state.get(signature) or {}
            if state_item.get('uploaded'):
                logger.info(f"[Strava] 跳过重复文件: {os.path.basename(file_path)}")
                skipped_count += 1
                continue
            logger.info(f"[Strava] 开始上传: {os.path.basename(file_path)}")
            upload_data = upload_file_to_strava(file_path, access_token)
            upload_id = upload_data.get('id') or upload_data.get('id_str')
            logger.info(f"[Strava] 上传已提交，upload_id={upload_id}")
            result = None
            if upload_id:
                result = poll_strava_upload_status(upload_id, access_token)
                logger.info(f"[Strava] 处理结果: {json.dumps(result, ensure_ascii=False)}")
            state[signature] = {
                'uploaded': True,
                'file': os.path.basename(file_path),
                'upload_id': str(upload_id or ''),
                'activity_id': str((result or {}).get('activity_id', '')),
                'uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            save_strava_upload_state(state)
            success_count += 1
        except Exception as e:
            err_text = str(e)
            category, friendly = classify_strava_error(err_text)
            if category == 'duplicate':
                dup_activity_id = ''
                m = re.search(r'/activities/(\d+)', err_text)
                if m:
                    dup_activity_id = m.group(1)
                state[signature] = {
                    'uploaded': True,
                    'file': os.path.basename(file_path),
                    'upload_id': '',
                    'activity_id': dup_activity_id,
                    'uploaded_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'note': 'duplicate acknowledged by strava'
                }
                save_strava_upload_state(state)
                logger.info(f"[Strava] {friendly}: {os.path.basename(file_path)}")
                skipped_count += 1
                continue
            failed_count += 1
            logger.error(f"[Strava] 上传失败 {os.path.basename(file_path)} [{category}]: {friendly}")
            logger.debug(f"[Strava] 原始错误: {err_text}")
    logger.info(f"[Strava] 上传完成，成功 {success_count}/{len(valid_files)}，跳过重复 {skipped_count}，失败 {failed_count}")
    return {
        'ok': failed_count == 0,
        'success': success_count,
        'skipped': skipped_count,
        'failed': failed_count
    }


def run_strava_auth_flow(config_file='settings.ini'):
    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8-sig')
    if not config.has_section('strava'):
        config.add_section('strava')

    client_id = config.get('strava', 'client_id', fallback='').strip()
    client_secret = config.get('strava', 'client_secret', fallback='').strip()
    port = config.getint('strava', 'redirect_port', fallback=8765)

    if not client_id or not client_secret:
        raise Exception('请先在 settings.ini 的 [strava] 中配置 client_id 和 client_secret')

    redirect_uri = f'http://127.0.0.1:{port}/callback'
    auth_url, expected_state = build_strava_auth_url(client_id, redirect_uri)
    auth_result = {'code': None, 'error': None, 'state': None}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(self.path)
            query = {}
            if '?' in self.path:
                query = parse_qs(parsed.query)
            auth_result['code'] = (query.get('code') or [None])[0]
            auth_result['error'] = (query.get('error') or [None])[0]
            auth_result['state'] = (query.get('state') or [None])[0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            msg = 'Strava 授权已接收，你可以关闭此页面并返回程序。'
            self.wfile.write(msg.encode('utf-8'))
        def log_message(self, format, *args):
            return

    httpd = HTTPServer(('127.0.0.1', port), CallbackHandler)
    server_thread = threading.Thread(target=httpd.handle_request, daemon=True)
    server_thread.start()

    logger.info(f'[Strava] 请在浏览器中完成授权: {auth_url}')
    logger.info(f'[Strava] 回调地址: {redirect_uri}')

    auth_tab = None
    try:
        logger.info('[Strava] 正在使用 ChromiumPage 打开授权页面...')
        auth_options = ChromiumOptions()
        auth_options.incognito()
        auth_options.set_argument('--no-sandbox')
        auth_options.set_argument('--disable-dev-shm-usage')
        auth_options.set_argument('--disable-web-security')
        auth_options.set_argument('--disable-features=VizDisplayCompositor')
        auth_options.set_argument('--disable-blink-features=AutomationControlled')
        auth_options.set_argument('--disable-extensions')
        auth_options.auto_port()
        if HEADLESS_MODE:
            auth_options.headless()
        auth_tab = ChromiumPage(auth_options)
        auth_tab.get(auth_url)
        logger.info(f'[Strava] 已通过 ChromiumPage 打开授权页，当前URL: {getattr(auth_tab, "url", "N/A")}')
    except Exception as e:
        logger.warning(f'[Strava] 使用 ChromiumPage 打开授权页失败，回退到系统浏览器: {e}')
        try:
            opened = bool(webbrowser.open(auth_url))
            if opened:
                logger.info('[Strava] 已尝试使用系统浏览器打开授权页')
        except Exception as inner_e:
            logger.warning(f'[Strava] 系统浏览器打开也失败: {inner_e}')

    wait_until = time.time() + 180
    while time.time() < wait_until and not auth_result.get('code') and not auth_result.get('error'):
        try:
            if auth_tab:
                current_url = getattr(auth_tab, 'url', '') or ''
                if 'code=' in current_url:
                    from urllib.parse import parse_qs
                    parsed = urlparse(current_url)
                    qs = parse_qs(parsed.query)
                    auth_result['code'] = (qs.get('code') or [None])[0]
                    auth_result['state'] = (qs.get('state') or [None])[0]
                    break
                if 'error=' in current_url:
                    from urllib.parse import parse_qs
                    parsed = urlparse(current_url)
                    qs = parse_qs(parsed.query)
                    auth_result['error'] = (qs.get('error') or [None])[0]
                    break
        except Exception:
            pass
        time.sleep(1)

    httpd.server_close()
    try:
        if auth_tab:
            auth_tab.close()
    except Exception:
        pass

    if auth_result.get('error'):
        raise Exception(f"Strava 授权失败: {auth_result['error']}")

    if not auth_result.get('code'):
        print('\n[Strava] 未收到自动回调。')
        print('[Strava] 你可以在完成浏览器授权后，把回调 URL 里的 code 参数手动粘贴进来。')
        manual_input = input('请输入完整回调 URL 或直接输入 code（留空则取消）: ').strip()
        if not manual_input:
            raise Exception('Strava 授权超时且未提供手动 code')
        if 'code=' in manual_input:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(manual_input)
            qs = parse_qs(parsed.query)
            auth_result['code'] = (qs.get('code') or [None])[0]
            auth_result['state'] = (qs.get('state') or [None])[0]
        else:
            auth_result['code'] = manual_input

    if auth_result.get('state') and auth_result.get('state') != expected_state:
        raise Exception('Strava 授权 state 校验失败')
    if not auth_result.get('code'):
        raise Exception('Strava 授权失败，未获取到 code')

    token_data = exchange_strava_code_for_token(client_id, client_secret, auth_result['code'])
    athlete = token_data.get('athlete') or {}
    update_ini_config_values(config_file, 'strava', {
        'enable_sync': 'true',
        'access_token': token_data.get('access_token', ''),
        'refresh_token': token_data.get('refresh_token', ''),
        'expires_at': token_data.get('expires_at', 0),
        'athlete_id': athlete.get('id', ''),
        'athlete_name': athlete.get('username') or athlete.get('firstname') or ''
    })
    logger.info(f"[Strava] 授权成功，已绑定账号: {athlete.get('username') or athlete.get('firstname') or athlete.get('id', '')}")

if STRAVA_AUTH_MODE:
    try:
        run_strava_auth_flow(CONFIG_FILE_PATH)
        logger.info('Strava 首次授权完成，程序结束。')
        sys.exit(0)
    except Exception as e:
        logger.error(f'Strava 授权初始化失败: {e}')
        sys.exit(1)

if '--strava-test' in sys.argv:
    try:
        token = refresh_strava_token_if_needed(CONFIG_FILE_PATH)
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_FILE_PATH, encoding='utf-8-sig')
        athlete_id = cfg.get('strava', 'athlete_id', fallback='').strip()
        athlete_name = cfg.get('strava', 'athlete_name', fallback='').strip()
        logger.info(f"[Strava] 测试成功，token 可用，账号: {athlete_name or athlete_id}")
        print('STRAVA_TEST_OK')
        sys.exit(0)
    except Exception as e:
        logger.error(f'[Strava] 测试失败: {e}')
        sys.exit(1)

if '--strava-upload-test' in sys.argv:
    try:
        idx = sys.argv.index('--strava-upload-test')
        if idx + 1 >= len(sys.argv):
            raise Exception('请在 --strava-upload-test 后面提供文件路径')
        test_file = sys.argv[idx + 1]
        if not os.path.isabs(test_file):
            test_file = os.path.abspath(test_file)
        if not os.path.exists(test_file):
            raise Exception(f'测试文件不存在: {test_file}')
        result = upload_files_to_strava([test_file], CONFIG_FILE_PATH)
        if not result.get('ok', False):
            raise Exception('Strava 上传测试未成功')
        print('STRAVA_UPLOAD_TEST_OK')
        sys.exit(0)
    except Exception as e:
        logger.error(f'[Strava] 上传测试失败: {e}')
        sys.exit(1)

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
logger.info("[DEBUG] 准备启动 ChromiumPage")
tab = ChromiumPage(options)
logger.info(f"[DEBUG] ChromiumPage 已启动，当前URL: {getattr(tab, 'url', 'N/A')}")

#test giant
# giant_cookies = login_giant_browser(tab, GIANT_ACCOUNT, GIANT_PASSWORD)
# # 测试上传文件 读取文件夹下所有文件
# valid_files = [f for f in os.listdir(STORAGE_DIR) if f.endswith('.fit') or f.endswith('.gpx')]
# upload_success = upload_files_to_giant(tab, valid_files)

# === 步骤1：先登录顽鹿获取cookies ===
logger.info("===== 步骤1：登录顽鹿平台 =====")
session = create_retry_session()
try:
    logger.info("[DEBUG] 开始调用 login_onelap_browser()")
    # 使用浏览器方式登录顽鹿账号
    onelap_cookies = login_onelap_browser(tab, ONELAP_ACCOUNT, ONELAP_PASSWORD)
    logger.info(f"[DEBUG] login_onelap_browser() 返回，cookies数量: {len(onelap_cookies) if onelap_cookies else 0}")

    logger.info("顽鹿登录完成，准备获取活动数据...")
except Exception as e:
    logger.critical(f"顽鹿登录失败: {e}")
    tab.close()
    sys.exit(1)

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
        logger.info("[DEBUG] 准备打开行者登录页")
        tab.get('https://www.imxingzhe.com/login')
        logger.info(f"[DEBUG] 行者登录页已打开，当前URL: {tab.url}")
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
        clicked_selector = click_xoss_login_button(tab)
        logger.info(f"[DEBUG] 行者登录按钮点击方式: {clicked_selector}")
        
        xoss_login_submitted = wait_xoss_login_success(tab, timeout=12)
        logger.info(f"[DEBUG] 行者提交登录后URL: {tab.url}, 标题: {tab.title}, login_success={xoss_login_submitted}")
        xoss_login_ok = xoss_login_submitted
        if not xoss_login_submitted:
            logger.warning("[DEBUG] 行者登录提交后仍未检测到成功登录态，跳过XOSS基准提取")
        else:
            try:
                logger.info("[DEBUG] 开始通过当前已登录页面解析行者最新活动时间")
                parsed = get_xoss_latest_activity_from_logged_in_tab(tab)
                if parsed:
                    latest_sync_activity = parsed
                    sync_benchmark_platform = 'xoss'
                    logger.info(f"成功通过当前页面获取行者最新记录: {parsed['activity_date']}")
                    if parsed.get('source_text'):
                        logger.info(f"[DEBUG] 行者当前页面来源文本: {parsed['source_text'][:200]}")
                else:
                    logger.warning("未能通过当前页面解析出行者最新活动时间")
            except Exception as e:
                logger.error(f"解析行者最新活动时间失败: {e}")
        
    except Exception as e:
        logger.error(f"行者登录或获取数据失败: {e}")
        xoss_login_ok = False
        # 失败后继续尝试下一个平台

# 如果行者失败或未配置，尝试 iGPSport
if not latest_sync_activity and IGPSPORT_ENABLE_SYNC and IGPSPORT_ACCOUNT and IGPSPORT_PASSWORD:
    logger.info("尝试使用 iGPSport 作为同步基准...")
    try:
        logger.info("[DEBUG] 开始调用 login_igpsport_browser() 获取基准")
        login_igpsport_browser(tab, IGPSPORT_ACCOUNT, IGPSPORT_PASSWORD)
        logger.info(f"[DEBUG] iGPSport 登录返回，当前URL: {tab.url}")
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
        logger.info("[DEBUG] 开始调用 login_giant_browser() 获取基准")
        login_giant_browser(tab, GIANT_ACCOUNT, GIANT_PASSWORD)
        logger.info(f"[DEBUG] Giant 登录返回，当前URL: {tab.url}")
        result = get_latest_activity_giant(tab)
        if result:
            latest_sync_activity = result
            sync_benchmark_platform = 'giant'
            logger.info(f"成功获取 Giant 最新记录: {result['activity_date']}")
    except Exception as e:
        logger.error(f"Giant 获取基准失败: {e}")

# 如果还不行，尝试 Strava
if not latest_sync_activity and STRAVA_ENABLE_SYNC and STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET and STRAVA_REFRESH_TOKEN:
    logger.info("尝试使用 Strava 作为同步基准...")
    try:
        result = get_latest_activity_strava(CONFIG_FILE_PATH)
        if result:
            latest_sync_activity = result
            sync_benchmark_platform = 'strava'
            logger.info(f"成功获取 Strava 最新记录: {result['activity_date']}")
        else:
            logger.warning("未获取到 Strava 最新记录")
    except Exception as e:
        logger.error(f"Strava 获取基准失败: {e}")

if not latest_sync_activity:
    if ONELAP_FULL_SYNC:
        logger.warning("⚠️ 未能从任何平台获取最新活动记录，但已显式启用 onelap_full_sync=true，将执行全量同步！")
    else:
        logger.critical("❌ 未能从任何平台获取最新活动记录，且未显式启用 onelap_full_sync=true；为避免误触发全量同步，程序终止。")
        tab.close()
        session.close()
        sys.exit(2)
else:
    logger.info(f"✅ 同步基准确定: {sync_benchmark_platform}, 最新时间: {latest_sync_activity['activity_date']}")

if ONELAP_FULL_SYNC:
    logger.info("✅ 已显式启用 OneLap 全量下载开关，将忽略同步基准，执行全量同步")
    latest_sync_activity = None


# === 步骤3：开始执行 FIT 文件下载任务 ===
logger.info("===== 步骤3：开始执行 FIT 文件下载任务 =====")
try:
    logger.info(f"[DEBUG] 进入步骤3，latest_sync_activity={'有' if latest_sync_activity else '无'}，benchmark平台={sync_benchmark_platform}")
    # 使用之前获取的顽鹿cookies获取活动数据
    activities = fetch_activities(session, onelap_cookies, latest_sync_activity)

    logger.info(f"[DEBUG] fetch_activities() 返回 {len(activities)} 个活动")
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
    sys.exit(1)

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
has_forward_sync_files = bool(valid_files)
if not has_forward_sync_files:
    logger.warning("没有找到符合条件的文件，跳过 OneLap 正向上传步骤。")

# === 步骤4：跳转到行者上传页面并分批上传文件 ===
logger.info("===== 步骤4：开始上传文件到行者平台 =====")
if not has_forward_sync_files:
    logger.info("没有 OneLap 新文件，跳过行者平台上传")
elif not XOSS_ENABLE_SYNC:
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
    if not has_forward_sync_files:
        logger.info("没有 OneLap 新文件，跳过捷安特平台上传")
    elif not GIANT_ENABLE_SYNC:
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
    if not has_forward_sync_files:
        logger.info("没有 OneLap 新文件，跳过iGPSport平台上传")
    elif not IGPSPORT_ENABLE_SYNC:
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

# === 步骤7：上传文件到 Strava 平台 ===
logger.info("===== 步骤7：上传文件到 Strava 平台 =====")
try:
    if not has_forward_sync_files:
        logger.info("没有 OneLap 新文件，跳过 Strava 上传")
    elif not STRAVA_ENABLE_SYNC:
        logger.info("Strava 平台同步已禁用，跳过 Strava 上传")
    elif not (STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET):
        logger.info("未配置 Strava client_id/client_secret，跳过 Strava 上传")
    else:
        strava_result = upload_files_to_strava(valid_files, 'settings.ini')
        logger.info(f"Strava 上传摘要: 成功 {strava_result.get('success', 0)}，重复跳过 {strava_result.get('skipped', 0)}，失败 {strava_result.get('failed', 0)}")
        if strava_result.get('ok', False):
            logger.info("文件已成功提交到 Strava 平台")
        else:
            logger.warning("Strava 平台存在失败项，请检查上方分类日志")
except Exception as e:
    logger.error(f"Strava 平台上传过程出错: {e}")
    logger.info("继续执行后续步骤...")

# === 步骤8：验证同步结果 ===
logger.info("===== 步骤8：验证同步结果 =====")
try:
    if not has_forward_sync_files:
        logger.info("没有 OneLap 新文件，跳过正向同步验证步骤")
    elif XOSS_ENABLE_SYNC and xoss_login_ok and XOSS_ACCOUNT and XOSS_PASSWORD and XOSS_ACCOUNT not in ['139xxxxxx', ''] and XOSS_PASSWORD not in ['xxxxxx', '']:
        logger.info("跳转到行者活动列表页面验证同步结果...")
        tab.get('https://www.imxingzhe.com/workouts/list')
        wait_xoss_activity_page_ready(tab, timeout=12)

        logger.info("请检查行者平台的活动列表，确认文件是否已成功同步")
        logger.info("程序将在15秒后自动关闭，您可以手动查看最新的活动记录")

        try:
            parsed = parse_xoss_latest_activity_from_html(tab.html)
            if parsed:
                logger.info("==最后查看行者平台最新的活动记录如下==:")
                logger.info(f"  1. {parsed['activity_date']} - {parsed.get('source_text', '')[:160]}")
            else:
                logger.warning("未找到活动表格或活动数据，请手动检查页面")
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

# === 步骤9：iGPSport → OneLap 增量同步（新增）===
logger.info("===== 步骤9：iGPSport → OneLap 增量同步 =====")
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
