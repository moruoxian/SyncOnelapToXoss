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

# 导入配置 - 支持INI配置文件
import configparser

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
        cfg['GIANT_ACCOUNT'] = config.get('giant', 'username', fallback='')
        cfg['GIANT_PASSWORD'] = config.get('giant', 'password', fallback='')
        cfg['GIANT_ENABLE_SYNC'] = config.getboolean('giant', 'enable_sync', fallback=False)
        cfg['STORAGE_DIR'] = config.get('sync', 'storage_dir', fallback='./downloads')
        
        formats_str = config.get('sync', 'supported_formats', fallback='.fit,.gpx,.tcx')
        cfg['SUPPORTED_FORMATS'] = [fmt.strip() for fmt in formats_str.split(',')]
        
        cfg['MAX_FILE_SIZE'] = config.getint('sync', 'max_file_size_mb', fallback=50) * 1024 * 1024
        cfg['MAX_FILES_PER_BATCH'] = config.getint('sync', 'max_files_per_batch', fallback=5)
        
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
    GIANT_ACCOUNT = ini_config['GIANT_ACCOUNT']
    GIANT_PASSWORD = ini_config['GIANT_PASSWORD']
    GIANT_ENABLE_SYNC = ini_config['GIANT_ENABLE_SYNC']
    STORAGE_DIR = ini_config['STORAGE_DIR']
    SUPPORTED_FORMATS = ini_config['SUPPORTED_FORMATS']
    MAX_FILE_SIZE = ini_config['MAX_FILE_SIZE']
    MAX_FILES_PER_BATCH = ini_config['MAX_FILES_PER_BATCH']
    
    # 配置验证提示
    if ONELAP_ACCOUNT in ['139xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的OneLap账号")
    if ONELAP_PASSWORD in ['xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的OneLap密码")
    if XOSS_ACCOUNT in ['139xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的行者账号")  
    if XOSS_PASSWORD in ['xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的行者密码")
    if GIANT_ACCOUNT in ['139xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的捷安特账号")
    if GIANT_PASSWORD in ['xxxxxx', '']:
        print("⚠️ 请在 settings.ini 中配置正确的捷安特密码")
else:
    # 使用默认配置
    print("📄 使用默认配置")
    LOG_LEVEL = 'INFO'
    HEADLESS_MODE = False
    ONELAP_ACCOUNT = ''
    ONELAP_PASSWORD = ''
    XOSS_ACCOUNT = ''
    XOSS_PASSWORD = ''
    GIANT_ACCOUNT = ''
    GIANT_PASSWORD = ''
    GIANT_ENABLE_SYNC = False
    STORAGE_DIR = './downloads'
    SUPPORTED_FORMATS = ['.fit', '.gpx', '.tcx']
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    MAX_FILES_PER_BATCH = 5

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
def batch_files(file_list, batch_size):
    """将文件列表分批处理"""
    for i in range(0, len(file_list), batch_size):
        yield file_list[i:i + batch_size]
def fetch_activities(session, cookies_dict, latest_xoss_activity):
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

        # 如果有最新的行者活动记录，只同步比它更新的活动
        if latest_xoss_activity and latest_xoss_activity.get('activity_date'):
            try:
                # 解析行者活动时间
                xoss_time_str = latest_xoss_activity['activity_date']
                # 尝试不同的时间格式解析
                xoss_time = None
                for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                    try:
                        xoss_time = datetime.strptime(xoss_time_str[:19], fmt)
                        break
                    except ValueError:
                        continue
                
                if xoss_time:
                    # 筛选出比行者最新活动更新的OneLap活动
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
                                
                            if onelap_time > xoss_time:
                                activities_after_matched.append(activity)
                        except Exception as e:
                            logger.debug(f"解析OneLap活动时间失败: {e}, created_at={activity.get('created_at')}")
                            # 如果时间解析失败，保守地包含该活动
                            activities_after_matched.append(activity)
                    
                    logger.info(f"筛选到 {len(activities_after_matched)} 个比行者最新活动更新的OneLap活动")
                    return activities_after_matched
                else:
                    logger.warning("无法解析行者活动时间，返回所有OneLap活动")
                    return filtered
            except Exception as e:
                logger.error(f"处理行者活动时间时出错: {e}")
                return filtered
        else:
            logger.info("没有行者活动记录，返回所有OneLap活动")
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

    if activity.get('fitUrl'):
        filename = f"{activity['fitUrl']}.fit"
    else:
        filename = f"{activity['fileKey']}"
    filepath = os.path.join(STORAGE_DIR, filename)

    if os.path.exists(filepath):
        logger.warning(f"文件已存在，跳过下载: {filename}")
        return

    try:
        logger.info(f"开始下载: {filename}")
        if "http://u.onelap.cn" in download_url:
            response = session.get(download_url, headers=headers, timeout=10, stream=True)
        else:
            response = session.get(download_url, headers=headers, timeout=10, stream=True)

        response.raise_for_status()

        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logger.info(f"文件下载完成: {filepath}")
    except Exception as e:
        logger.error(f"下载失败: {filename}", exc_info=True)
        if os.path.exists(filepath):
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
                        if os.path.isabs(file_name):
                            file_paths.append(file_name)
                        else:
                            file_paths.append(os.path.join(STORAGE_DIR, file_name))
                    
                    # 打印即将上传的文件列表
                    for file_path in file_paths:
                        logger.info(f"准备上传: {os.path.basename(file_path)}")
                    
                    # 一次性选择所有文件（支持多文件选择）
                    try:
                        # 尝试传递多个文件路径
                        if len(file_paths) == 1:
                            # 单个文件
                            upload_element.input(file_paths[0])
                        else:
                            # 多个文件，使用换行符分隔的路径字符串
                            # 某些平台支持这种方式
                            upload_element.input('\n'.join(file_paths))
                        
                        logger.info(f"已选择 {len(file_paths)} 个文件进行上传")
                        
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
                        logger.info(f"找到提交按钮: {selector}")


                    
                    if submit_button:
                        submit_button.click()
                        logger.info("已点击捷安特上传提交按钮")
                        # time.sleep(1)
                    else:
                        logger.warning("未找到提交按钮，文件可能已自动上传")

                    time.sleep(1)
                    #缺少一个 btn ok的点击
                    tab.ele('.btn ok').click()
                    logger.info("已经提交成功了")

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
options.set_argument("--remote-debugging-port=9222")    # 设置调试端口

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

# === 步骤2：转到行者平台登录 ===
logger.info("===== 步骤2：转到行者平台登录 =====")
tab.get('https://www.imxingzhe.com/login')

# 等待页面完全加载
# time.sleep(3)

# 调试：输出页面标题和基本信息
logger.info(f"页面标题: {tab.title}")
logger.info(f"当前URL: {tab.url}")

# 调试：输出页面HTML结构（仅用于调试）
if LOG_LEVEL == 'DEBUG':
    try:
        page_html = tab.html
        logger.debug(f"页面HTML长度: {len(page_html)}")
        # 只输出前1000个字符用于调试
        logger.debug(f"页面HTML预览: {page_html[:1000]}")
    except Exception as e:
        logger.debug(f"获取页面HTML失败: {e}")

# 等待页面加载完成并输入登录信息
# 使用 DrissionPage 官方推荐的元素定位方式
logger.info("开始查找登录表单元素...")

# 点击“我已阅读并同意”复选框（VantUI自定义组件）
logger.info("查找并点击'我已阅读并同意'协议复选框...")
try:
    checkbox = tab.ele('.van-checkbox', timeout=1)
    if checkbox:
        checkbox.click()
        logger.info("成功点击自定义协议复选框")
        # time.sleep(1)
    else:
        logger.warning("未找到自定义协议复选框，继续登录流程")
except Exception as e:
    logger.warning(f"点击协议复选框失败: {e}")
    logger.info("继续登录流程...")

# === 官方推荐方式：用id/value精确定位输入框和按钮 ===
try:
    # 输入账号（用name属性）
    tab.ele('@name=account').clear()
    tab.ele('@name=account').input(XOSS_ACCOUNT)
    logger.info("已输入账号信息")

    
    # 输入密码（假设密码框也是用name属性）
    tab.ele('@name=password').clear()
    tab.ele('@name=password').input(XOSS_PASSWORD)
    logger.info("已输入密码信息")
  
    
# 点击登录按钮
    try:
        # 优先用最具体的class
        tab.ele('.login_btn_box login_btn van-button van-button--primary van-button--normal van-button--block').click()
        logger.info("已点击登录按钮")
    except Exception:
        try:
            # 备用class
            tab.ele('.login_btn').click()
            logger.info("已点击登录按钮（备用class）")
        except Exception:
            try:
                # 用type属性
                tab.ele('button[type=submit]').click()
                logger.info("已点击登录按钮（type方式）")
            except Exception:
                # 最后用文本内容
                tab.ele('button:contains("登录")').click()
                logger.info("已点击登录按钮（文本方式）")
    # time.sleep(2)
except Exception as e:
    logger.error(f"登录表单操作失败: {e}")
    raise
# 等待页面加载完成后跳转到活动列表页面
time.sleep(3)  # 等待登录完成

# 跳转到活动记录页面
logger.info("正在跳转到活动记录页面...")
tab.get('https://www.imxingzhe.com/workouts/list')
time.sleep(5)  # 增加等待时间，确保页面完全加载

# 调试：检查当前页面状态
logger.info(f"当前页面URL: {tab.url}")
logger.info(f"当前页面标题: {tab.title}")

# 获取行者活动数据（从HTML表格中提取）
try:
    logger.info("开始从行者活动列表页面提取数据...")
    xoss_activities = []
    
    # 1. 先定位表格 - 尝试多种选择器
    table = None
    table_selectors = [
        '.table_box'
    ]
    
    for selector in table_selectors:
        try:
            logger.info(f"尝试选择器: {selector}")
            table = tab.ele(selector, timeout=3)
            if table:
                logger.info(f"成功找到表格，使用选择器: {selector}")
                break
        except Exception as e:
            logger.debug(f"选择器 {selector} 失败: {e}")
            continue
    
    if not table:
        logger.error("未找到活动数据表格")
        # 尝试查找页面中的所有表格
        all_tables = tab.eles('table')
        logger.info(f"页面中共找到 {len(all_tables)} 个表格元素")
        for i, t in enumerate(all_tables):
            try:
                table_class = t.attr('class') or '无class'
                logger.info(f"表格 {i+1}: class='{table_class}'")
            except:
                logger.info(f"表格 {i+1}: 无法获取属性")
        raise Exception("页面中没有找到活动数据表格")
    
    logger.info("成功找到活动数据表格")
    
    # 等待表格数据加载
    logger.info("等待表格数据异步加载...")
    
    # 使用BeautifulSoup解析表格HTML
    try:
        table_html = table.html
        logger.info(f"表格HTML长度: {len(table_html)}")
        
        # 使用BeautifulSoup解析HTML
        soup = BeautifulSoup(table_html, 'html.parser')
        
        # 查找所有的表格行
        rows = soup.find_all('tr')
        logger.info(f"使用BeautifulSoup找到 {len(rows)} 行数据")
        
        # 解析表头
        if len(rows) > 0:
            header_row = rows[0]
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            logger.info(f"表头: {headers}")
        
        # 解析数据行（跳过表头）
        for i, row in enumerate(rows[1:], 1):
            cells = row.find_all('td')
            if len(cells) >= 8:  # 确保有足够的列
                try:
                    # 根据你提供的HTML结构提取数据：
                    # 第0列：图片，第1列：类型，第2列：日期，第3列：标题
                    # 第4列：距离，第5列：时间，第6列：爬升，第7列：负荷，第8列：其他
                    
                    # 提取各列数据
                    sport_type = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                    activity_date = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                    title = cells[3].get_text(strip=True) if len(cells) > 3 else ""
                    distance_text = cells[4].get_text(strip=True) if len(cells) > 4 else ""
                    duration_text = cells[5].get_text(strip=True) if len(cells) > 5 else ""
                    elevation_text = cells[6].get_text(strip=True) if len(cells) > 6 else ""
                    load_text = cells[7].get_text(strip=True) if len(cells) > 7 else ""
                    
                    # 解析距离（移除单位km）
                    distance = 0.0
                    if 'km' in distance_text:
                        try:
                            distance = float(distance_text.replace('km', '').strip())
                        except ValueError:
                            logger.debug(f"无法解析距离: {distance_text}")
                            distance = 0.0
                    
                    # 解析爬升（移除单位m）
                    elevation = 0
                    if 'm' in elevation_text:
                        try:
                            elevation = int(elevation_text.replace('m', '').strip())
                        except ValueError:
                            logger.debug(f"无法解析爬升: {elevation_text}")
                            elevation = 0
                    
                    # 构造活动数据结构
                    activity_data = {
                        "workout_id": f"xoss_{activity_date}_{i}",  # 使用日期和索引生成ID
                        "activity_date": activity_date,
                        "title": title,
                        "distance": distance,
                        "duration": duration_text,
                        "elevation": elevation,
                        "sport_type": "cycling",  # 从HTML看主要是骑行活动
                        "load": load_text
                    }
                    
                    xoss_activities.append(activity_data)
                    logger.info(f"提取活动 {i}: {activity_date} - {title} - {distance}km")
                    
                except Exception as e:
                    logger.warning(f"解析第 {i} 行活动数据失败: {e}")
                    continue
            else:
                logger.debug(f"第 {i} 行数据列数不足: {len(cells)}")
                
        logger.info(f"使用BeautifulSoup成功提取 {len(xoss_activities)} 个行者活动记录")
        
    except Exception as e:
        logger.debug(f"使用BeautifulSoup解析表格HTML失败: {e}")
        # 如果BeautifulSoup解析失败，设置为空列表
        xoss_activities = []
    
except Exception as e:
    logger.error(f"获取行者活动数据失败: {e}")
    xoss_activities = []

# 4. 对活动按时间排序，找到最新记录
def parse_activity_date(activity):
    """解析活动日期，返回datetime对象用于排序"""
    try:
        activity_date = activity.get('activity_date', '')
        if not activity_date:
            return datetime.min
        
        # 尝试解析不同的日期格式
        date_formats = [
            '%Y-%m-%d',           # 2025-07-24
            '%Y-%m-%d %H:%M:%S',  # 2025-07-24 14:30:00
            '%Y-%m-%dT%H:%M:%S',  # 2025-07-24T14:30:00
        ]
        
        for fmt in date_formats:
            try:
                # 对于只有日期的情况，从标题中提取上午/下午信息
                if fmt == '%Y-%m-%d' and len(activity_date) == 10:
                    title = activity.get('title', '')
                    if '下午' in title:
                        # 下午活动，设置为当天14:00
                        date_obj = datetime.strptime(activity_date, fmt)
                        return date_obj.replace(hour=14, minute=0, second=0)
                    elif '上午' in title:
                        # 上午活动，设置为当天08:00
                        date_obj = datetime.strptime(activity_date, fmt)
                        return date_obj.replace(hour=8, minute=0, second=0)
                    elif '晚上' in title:
                        # 晚上活动，设置为当天20:00
                        date_obj = datetime.strptime(activity_date, fmt)
                        return date_obj.replace(hour=19, minute=0, second=0)
                    else:
                        # 没有明确时间，设置为中午12:00
                        date_obj = datetime.strptime(activity_date, fmt)
                        return date_obj.replace(hour=12, minute=0, second=0)
                else:
                    return datetime.strptime(activity_date[:len(fmt)], fmt)
            except ValueError:
                continue
                
        logger.warning(f"无法解析活动日期: {activity_date}")
        return datetime.min
        
    except Exception as e:
        logger.error(f"解析活动时间戳失败: {activity} - {e}")
        return datetime.min

# 5. 按时间降序排序（最新的在前面）
if xoss_activities:
    xoss_activities.sort(key=parse_activity_date, reverse=True)
    
    # 获取最新的活动记录
    latest_xoss_activity = xoss_activities[0]
    latest_date = parse_activity_date(latest_xoss_activity)
    
    logger.info(f"行者最新活动记录:")
    logger.info(f"  - ID: {latest_xoss_activity.get('workout_id', 'N/A')}")
    logger.info(f"  - 日期: {latest_xoss_activity.get('activity_date', 'N/A')}")
    logger.info(f"  - 标题: {latest_xoss_activity.get('title', 'N/A')}")
    logger.info(f"  - 距离: {latest_xoss_activity.get('distance', 0)}km")
    logger.info(f"  - 解析时间: {latest_date}")

    # 显示前5条活动记录用于调试
    logger.info("前5条活动记录（按时间降序）:")
    for i, activity in enumerate(xoss_activities[:5]):
        date_parsed = parse_activity_date(activity)
        logger.info(f"  {i+1}. {activity['activity_date']} - {activity['title']} ({date_parsed})")
        
else:
    logger.warning("未找到任何行者活动记录，将同步所有OneLap活动")
    latest_xoss_activity = None

# === 步骤3：开始执行 FIT 文件下载任务 ===
logger.info("===== 步骤3：开始执行 FIT 文件下载任务 =====")
try:
    # 使用之前获取的顽鹿cookies获取活动数据
    activities = fetch_activities(session, onelap_cookies, latest_xoss_activity)

    logger.info(f"总共需要处理 {len(activities)} 个活动")
    #分别是什么需要打印出来
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

# === 步骤6：验证同步结果 ===
logger.info("===== 步骤6：验证同步结果 =====")
try:
    # 跳转到行者活动列表页面验证上传结果
    logger.info("跳转到行者活动列表页面验证同步结果...")
    tab.get('https://www.imxingzhe.com/workouts/list')
    time.sleep(5)  # 等待页面加载
    
    logger.info("请检查行者平台的活动列表，确认文件是否已成功同步")
    logger.info("程序将在15秒后自动关闭，您可以手动查看最新的活动记录")
    
    # 尝试获取最新的活动数据进行对比
    try:
        table = tab.ele('.table_box', timeout=3)
        if table:
            table_html = table.html
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(table_html, 'html.parser')
            rows = soup.find_all('tr')
            
            if len(rows) > 1:  # 有数据行
                # 获取前3条最新活动
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
    
    # 给用户时间查看结果
    time.sleep(15)
    
except Exception as e:
    logger.error(f"验证步骤失败: {e}")
    logger.info("请手动访问行者平台确认同步结果")
    time.sleep(5)

# === 任务完成，关闭浏览器和会话 ===
logger.info("===== 任务执行完成 =====")
tab.close()
session.close()
logger.info("浏览器和会话已关闭")
