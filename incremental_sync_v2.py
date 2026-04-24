#!/usr/bin/env python3
"""
iGPSport → OneLap 增量同步（基于最新时间戳）
策略：只同步 iGPSport 中时间晚于 OneLap 最新记录的数据
"""

import os
import re
import sys
import json
import time
import configparser
import logging
import requests
import hashlib
import random
import string
from datetime import datetime
from collections import namedtuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('IncrementalSync')

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_app_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return SCRIPT_DIR


APP_DIR = get_app_dir()
CONFIG_FILE_PATH = os.path.join(APP_DIR, 'settings.ini')

ONELAP_BASE_WEB_URL = 'https://www.onelap.cn'
ONELAP_BASE_APP_URL = 'https://u.onelap.cn'
ONELAP_LIST_API = f'{ONELAP_BASE_APP_URL}/api/otm/ride_record/list'
ONELAP_UPLOAD_API = f'{ONELAP_BASE_APP_URL}/api/otm/ride_record/upload/fit'
ONELAP_SIGN_KEY = 'fe9f8382418fcdeb136461cac6acae7b'
ONELAP_USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'


def rand_nonce(length=16):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))


def replace_empty_with_none(value):
    if isinstance(value, dict):
        return {k: replace_empty_with_none(v) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_empty_with_none(v) for v in value]
    if value == '':
        return None
    return value


def process_sign_params(params):
    result = {}
    for key, value in (params or {}).items():
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                result[key] = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
            else:
                result[key] = ','.join(str(v) for v in value)
        elif isinstance(value, dict):
            result[key] = json.dumps(value, ensure_ascii=False, separators=(',', ':'))
        else:
            result[key] = value
    return result


def generate_onelap_sign_headers(params):
    nonce = rand_nonce(16)
    timestamp = str(int(time.time()))
    normalized = process_sign_params(replace_empty_with_none(params or {}))
    all_params = {**normalized, 'nonce': nonce, 'timestamp': timestamp}
    parts = []
    for key in sorted(all_params.keys()):
        value = all_params[key]
        if value is not None:
            parts.append(f'{key}={value}')
    string_to_sign = '&'.join(parts) + f'&key={ONELAP_SIGN_KEY}'
    sign = hashlib.md5(string_to_sign.encode('utf-8')).hexdigest()
    return {'nonce': nonce, 'timestamp': timestamp, 'sign': sign}


def wait_for_onelap_login_result(tab, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        current_url = tab.url or ''
        if 'u.onelap.cn' in current_url and 'login.html' not in current_url:
            return True
        user_info = tab.run_js("return localStorage.getItem('userInfo');")
        if user_info:
            return True
        time.sleep(1)
    return False


def get_onelap_auth_context(tab):
    token = tab.run_js("return localStorage.getItem('token');")
    user_info_raw = tab.run_js("return localStorage.getItem('userInfo');")
    user_info = None
    if user_info_raw:
        try:
            user_info = json.loads(user_info_raw)
        except Exception:
            user_info = None

    if not token and isinstance(user_info, list) and user_info and isinstance(user_info[0], dict):
        token = user_info[0].get('token')
    if not token and isinstance(user_info, dict):
        token = user_info.get('token')

    cookies = {}
    for cookie in tab.cookies():
        cookies[cookie['name']] = cookie['value']

    return {'token': token or '', 'cookies': cookies, 'user_info': user_info}


def build_onelap_api_session(token, cookies_dict):
    session = requests.Session()
    session.headers.update({
        'User-Agent': ONELAP_USER_AGENT,
        'Authorization': token,
        'Origin': ONELAP_BASE_APP_URL,
        'Referer': f'{ONELAP_BASE_APP_URL}/analysis',
    })
    session.cookies.update(cookies_dict or {})
    return session


def parse_onelap_activity_time(activity):
    candidates = []
    if isinstance(activity, dict):
        candidates.extend([
            activity.get('start_riding_time'),
            activity.get('startTime'),
            activity.get('created_at'),
            activity.get('updated_at'),
            activity.get('date'),
        ])

    def parse_candidate(value):
        if isinstance(value, int):
            if value <= 0:
                return None
            timestamp = value / 1000 if value > 10**11 else value
            dt = datetime.fromtimestamp(timestamp)
            return dt if dt.year >= 2000 else None
        if isinstance(value, float):
            if value <= 0:
                return None
            timestamp = value / 1000 if value > 10**11 else value
            dt = datetime.fromtimestamp(timestamp)
            return dt if dt.year >= 2000 else None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(text, fmt)
                    return dt if dt.year >= 2000 else None
                except Exception:
                    pass
            try:
                dt = datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
                return dt if dt.year >= 2000 else None
            except Exception:
                return None
        return None

    for candidate in candidates:
        parsed = parse_candidate(candidate)
        if parsed:
            return parsed
    return None


def parse_igpsport_activity_time(item):
    if not isinstance(item, dict):
        return None

    title = str(item.get('title') or '').strip()
    match = re.search(r'_(\d{10})(?:_|$)', title)
    if match:
        try:
            return datetime.fromtimestamp(int(match.group(1)))
        except Exception:
            pass

    start_time = str(item.get('startTime') or '').strip().replace('.', '-')
    if start_time:
        try:
            return datetime.strptime(start_time, '%Y-%m-%d')
        except Exception:
            pass

    return None


def sanitize_filename_component(value):
    text = str(value or '').strip()
    if not text:
        return 'unknown'
    text = re.sub(r'[<>:"/\\|?*]+', '-', text)
    text = re.sub(r'\s+', ' ', text).strip().strip('.')
    return text or 'unknown'


ActivityRecord = namedtuple('ActivityRecord', [
    'ride_id', 'start_time', 'start_time_obj', 'distance', 'duration', 'platform', 'download_url'
])


class IGPSportClient:
    """iGPSport 平台客户端"""
    
    BASE_URL = "https://prod.zh.igpsport.com/service"
    
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.token = None
    
    def login(self):
        """登录获取 token"""
        import urllib.request
        import json

        logger.info("[iGPSport] 登录中...")

        url = f"{self.BASE_URL}/auth/account/login"
        payload = json.dumps({
            'username': self.username,
            'password': self.password,
            'appId': 'igpsport-web'
        }).encode('utf-8')
        headers = {
            'Content-Type': 'application/json;charset=UTF-8',
            'Accept': 'application/json, text/plain, */*',
            'Origin': 'https://app.igpsport.cn',
            'Referer': 'https://app.igpsport.cn/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Connection': 'close'
        }

        for attempt in range(1, 4):
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    resp_data = json.loads(response.read().decode('utf-8'))
                    if resp_data['code'] != 0:
                        logger.error(f"[iGPSport] 登录失败: {resp_data.get('message')}")
                        return False

                    self.token = resp_data['data']['access_token']
                    logger.info("[iGPSport] ✅ 登录成功")
                    return True
            except Exception as e:
                logger.error(f"[iGPSport] 登录异常(第{attempt}/3次): {e}")
                if attempt < 3:
                    time.sleep(attempt)

        return False
    
    def get_all_activities(self):
        """获取所有活动记录"""
        import urllib.request
        import json
        
        if not self.token:
            logger.error("[iGPSport] 未登录")
            return []
        
        all_activities = []
        page = 1
        total_pages = 1
        
        logger.info("[iGPSport] 获取活动列表...")
        
        while page <= total_pages:
            params = {
                'pageNo': page,
                'pageSize': 20,
                'reqType': 0,
                'sort': 1
            }
            
            import urllib.parse
            query_string = urllib.parse.urlencode(params)
            url = f"{self.BASE_URL}/web-gateway/web-analyze/activity/queryMyActivity?{query_string}"
            
            req = urllib.request.Request(url)
            req.add_header('Authorization', f"Bearer {self.token}")
            
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    resp_data = json.loads(response.read().decode())
                    
                    if resp_data['code'] != 0:
                        logger.error(f"[iGPSport] 获取列表失败: {resp_data.get('message')}")
                        break
                    
                    data = resp_data['data']
                    rows = data.get('rows', [])
                    total_pages = data.get('totalPage', 1)
                    
                    for item in rows:
                        start_time_obj = parse_igpsport_activity_time(item)
                        start_time = start_time_obj.strftime('%Y-%m-%d %H:%M:%S') if start_time_obj else ''
                        if not start_time:
                            raw_start_time = str(item.get('startTime') or '').strip()
                            start_time = raw_start_time.replace('.', '-') if raw_start_time else 'Unknown'

                        # 使用 rideDistance（米）
                        distance = float(item.get('rideDistance', 0) or 0)

                        # 使用 totalMovingTime（秒）
                        duration = int(item.get('totalMovingTime', 0) or 0)

                        activity = ActivityRecord(
                            ride_id=str(item.get('rideId', '')),
                            start_time=start_time,
                            start_time_obj=start_time_obj,
                            distance=distance,
                            duration=duration,
                            platform='igpsport',
                            download_url=item.get('durl', '')
                        )
                        all_activities.append(activity)
                    
                    logger.info(f"[iGPSport] 第 {page}/{total_pages} 页: {len(rows)} 条记录")
                    
                    if not rows:
                        break
                    
                    page += 1
                    time.sleep(0.3)
                    
            except Exception as e:
                logger.error(f"[iGPSport] 获取列表异常: {e}")
                break
        
        logger.info(f"[iGPSport] 共获取 {len(all_activities)} 条记录")
        return all_activities
    
    def download_file(self, ride_id, output_path):
        """下载单个 FIT 文件"""
        import urllib.request
        import json

        if not self.token:
            return False

        part_path = f"{output_path}.part"
        if os.path.exists(part_path):
            os.remove(part_path)

        for attempt in range(1, 4):
            url = f"{self.BASE_URL}/web-gateway/web-analyze/activity/getDownloadUrl/{ride_id}"
            req = urllib.request.Request(url)
            req.add_header('Authorization', f"Bearer {self.token}")

            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    resp_data = json.loads(response.read().decode())
                    if resp_data['code'] != 0:
                        logger.error(f"[iGPSport] 获取下载地址失败: {resp_data.get('message')}")
                        return False

                    download_url = resp_data['data']
                    if not download_url:
                        logger.error("[iGPSport] 下载地址为空")
                        return False

                req2 = urllib.request.Request(download_url)
                req2.add_header('Authorization', f"Bearer {self.token}")

                with urllib.request.urlopen(req2, timeout=120) as resp, \
                     open(part_path, 'wb') as out_file:
                    while True:
                        chunk = resp.read(1024 * 256)
                        if not chunk:
                            break
                        out_file.write(chunk)

                if not os.path.exists(part_path) or os.path.getsize(part_path) <= 0:
                    raise RuntimeError('下载结果为空文件')

                os.replace(part_path, output_path)
                return True
            except Exception as e:
                if os.path.exists(part_path):
                    os.remove(part_path)
                logger.error(f"[iGPSport] 下载失败(第{attempt}/3次): {e}")
                if attempt < 3:
                    time.sleep(attempt)

        return False


class OneLapClient:
    """OneLap 平台客户端"""

    def __init__(self, username, password, tab=None, owns_tab=True):
        self.username = username
        self.password = password
        self.tab = tab
        self.owns_tab = owns_tab
        self.auth_context = None

    def login(self):
        """登录 OneLap"""
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions
        except ImportError:
            logger.error("[OneLap] 请先安装 DrissionPage")
            return False

        if self.tab:
            logger.info("[OneLap] 复用已有浏览器实例")
            self.auth_context = get_onelap_auth_context(self.tab)
            if self.auth_context.get('token'):
                return True

            try:
                self.tab.get(f'{ONELAP_BASE_APP_URL}/analysis')
                time.sleep(3)
            except Exception:
                pass
            self.auth_context = get_onelap_auth_context(self.tab)
            return bool(self.auth_context.get('token'))

        logger.info("[OneLap] 启动浏览器...")

        options = ChromiumOptions()
        options.auto_port()
        if os.name != 'nt':
            for candidate in ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser']:
                if os.path.exists(candidate):
                    options.set_paths(browser_path=candidate)
                    break
        options.headless()
        options.set_argument("--no-sandbox")
        options.set_argument("--disable-dev-shm-usage")
        options.set_argument("--disable-gpu")
        options.set_argument("--window-size=1920,1080")

        try:
            self.tab = ChromiumPage(options)
            self.owns_tab = True
        except Exception as e:
            logger.error(f"[OneLap] 浏览器启动失败: {e}")
            return False

        logger.info("[OneLap] 登录中...")

        try:
            self.tab.get(f'{ONELAP_BASE_WEB_URL}/login.html')
            time.sleep(3)

            self.tab.ele('.from1 login_1', timeout=10).clear().input(self.username)
            self.tab.ele('.from1 login_password ', timeout=10).clear().input(self.password)
            self.tab.ele('.from_yellow_btn', timeout=10).click()
            logger.info("[OneLap] 如果出现验证码/二次确认，请在浏览器中手动完成")

            if not wait_for_onelap_login_result(self.tab, timeout=90):
                logger.error(f"[OneLap] 登录失败，当前 URL: {self.tab.url}")
                return False

            self.tab.get(f'{ONELAP_BASE_APP_URL}/analysis')
            time.sleep(5)
            self.auth_context = get_onelap_auth_context(self.tab)
            if not self.auth_context.get('token'):
                logger.error("[OneLap] 未能从 localStorage 读取 token")
                return False

            logger.info("[OneLap] ✅ 登录成功")
            return True

        except Exception as e:
            logger.error(f"[OneLap] 登录异常: {e}")
            return False

    def _refresh_auth_context(self):
        if not self.tab:
            return {}
        self.auth_context = get_onelap_auth_context(self.tab)
        return self.auth_context or {}

    def _create_api_session(self):
        auth_context = self._refresh_auth_context()
        token = str(auth_context.get('token') or '').strip()
        cookies = auth_context.get('cookies') or {}
        if not token:
            try:
                self.tab.get(f'{ONELAP_BASE_APP_URL}/analysis')
                time.sleep(3)
            except Exception:
                pass
            auth_context = self._refresh_auth_context()
            token = str(auth_context.get('token') or '').strip()
            cookies = auth_context.get('cookies') or {}

        if not token:
            raise RuntimeError('未获取到 OneLap token')

        return build_onelap_api_session(token, cookies)

    def _fetch_recent_activities(self, limit=10):
        session = self._create_api_session()
        try:
            payload = {'page': 1, 'limit': limit}
            headers = generate_onelap_sign_headers(payload)
            response = session.post(ONELAP_LIST_API, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            page_data = (data.get('data') or {}) if isinstance(data, dict) else {}
            return page_data.get('list') or []
        finally:
            session.close()

    def _count_activities_with_time(self, expected_time, max_pages=5, page_size=20):
        if not expected_time:
            return 0

        session = self._create_api_session()
        try:
            matched = 0
            for page in range(1, max_pages + 1):
                payload = {'page': page, 'limit': page_size}
                headers = generate_onelap_sign_headers(payload)
                response = session.post(ONELAP_LIST_API, json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
                page_data = (data.get('data') or {}) if isinstance(data, dict) else {}
                items = page_data.get('list') or []
                if not items:
                    break

                for activity in items:
                    activity_time = parse_onelap_activity_time(activity)
                    if activity_time == expected_time:
                        matched += 1

                if len(items) < page_size:
                    break

            return matched
        finally:
            session.close()

    def _wait_for_uploaded_activity(self, expected_time, baseline_count=0, timeout=120, interval=5):
        if not expected_time:
            return False

        end_time = time.time() + timeout
        while time.time() < end_time:
            try:
                current_count = self._count_activities_with_time(expected_time)
            except Exception as e:
                logger.warning(f"[OneLap] 上传结果校验查询失败: {e}")
                time.sleep(interval)
                continue

            if current_count > baseline_count:
                logger.info(
                    f"[OneLap] 已确认活动入库: {expected_time.strftime('%Y-%m-%d %H:%M:%S')} (数量 {baseline_count} -> {current_count})"
                )
                return True

            logger.info(
                f"[OneLap] 尚未查到新增活动，当前数量 {current_count}，{interval} 秒后重试"
            )
            time.sleep(interval)

        return False

    def get_latest_activity_time(self):
        """
        获取 OneLap 最新一条记录的时间（通过新签名 API）
        返回: datetime 对象 或 None
        """
        if not self.tab:
            logger.error("[OneLap] 未登录")
            return None

        logger.info("[OneLap] 获取最新记录时间...")

        try:
            self.auth_context = get_onelap_auth_context(self.tab)
            token = str((self.auth_context or {}).get('token') or '').strip()
            cookies = (self.auth_context or {}).get('cookies') or {}
            if not token:
                logger.warning("[OneLap] 当前页面未读到 token，尝试跳转分析页刷新认证上下文")
                self.tab.get(f'{ONELAP_BASE_APP_URL}/analysis')
                time.sleep(3)
                self.auth_context = get_onelap_auth_context(self.tab)
                token = str((self.auth_context or {}).get('token') or '').strip()
                cookies = (self.auth_context or {}).get('cookies') or {}

            if not token:
                logger.warning("[OneLap] 未获取到 token，无法查询最新记录")
                return None

            session = build_onelap_api_session(token, cookies)
            try:
                payload = {'page': 1, 'limit': 1}
                headers = generate_onelap_sign_headers(payload)
                response = session.post(ONELAP_LIST_API, json=payload, headers=headers, timeout=30)
                response.raise_for_status()
                data = response.json()
            finally:
                session.close()

            page_data = (data.get('data') or {}) if isinstance(data, dict) else {}
            items = page_data.get('list') or []
            if not items:
                logger.info("[OneLap] 当前无记录")
                return None

            latest_activity = items[0]
            latest_time = parse_onelap_activity_time(latest_activity)
            if not latest_time:
                logger.warning(f"[OneLap] 无法解析最新记录时间: {latest_activity}")
                return None

            logger.info(f"[OneLap] 最新记录时间: {latest_time.strftime('%Y-%m-%d %H:%M:%S')}")
            return latest_time

        except Exception as e:
            logger.error(f"[OneLap] 获取最新时间异常: {e}")
            return None

    def _ensure_analysis_page(self):
        current_url = self.tab.url or ''
        if 'analysis' not in current_url:
            logger.info("      🔄 加载上传页面...")
            self.tab.get(f'{ONELAP_BASE_APP_URL}/analysis')
            time.sleep(3)

    def _find_upload_input(self):
        selectors = [
            'css:input[type="file"]',
            '@type=file',
            'tag:input',
        ]

        for selector in selectors:
            try:
                ele = self.tab.ele(selector, timeout=5)
                if not ele:
                    continue
                input_type = str(ele.attr('type') or '').strip().lower()
                if selector == 'tag:input' and input_type != 'file':
                    continue
                logger.info(f"      📎 找到上传输入框: {selector}")
                return ele
            except Exception:
                continue

        return None

    def _direct_upload_file(self, file_path):
        session = self._create_api_session()
        try:
            filename = os.path.basename(file_path)
            with open(file_path, 'rb') as f:
                response = session.post(
                    ONELAP_UPLOAD_API,
                    files={'jilu0': (filename, f, 'application/octet-stream')},
                    timeout=120,
                )
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise RuntimeError(f'上传返回异常: {response.text[:500]}')
            if data.get('code') != 200:
                raise RuntimeError(f"上传失败: code={data.get('code')} message={data.get('message')}")
            payload = data.get('data') or {}
            failed_count = int(payload.get('failed_count') or 0)
            success_count = int(payload.get('success_count') or 0)
            if failed_count > 0 or success_count <= 0:
                raise RuntimeError(f'上传未成功入队: {json.dumps(data, ensure_ascii=False)}')
            logger.info(f"      📤 直传接口返回成功: success_count={success_count}")
            return True
        finally:
            session.close()

    def upload_file(self, file_path, expected_time=None):
        """
        上传单个 FIT 文件，并校验是否真正入库
        """
        if not self.tab:
            return False

        try:
            baseline_count = 0
            if expected_time:
                baseline_count = self._count_activities_with_time(expected_time)
                logger.info(
                    f"[OneLap] 上传前同时间活动数量: {baseline_count} ({expected_time.strftime('%Y-%m-%d %H:%M:%S')})"
                )

            self._direct_upload_file(file_path)

            if expected_time:
                if self._wait_for_uploaded_activity(expected_time, baseline_count=baseline_count, timeout=120, interval=5):
                    return True
                logger.error("[OneLap] 直传成功，但在等待期内未查到新增活动入库")
                return False

            time.sleep(3)
            return True

        except Exception as e:
            logger.error(f"[OneLap] 上传失败: {e}")
            return False

    def close(self):
        """关闭浏览器"""
        if self.tab and self.owns_tab:
            try:
                self.tab.close()
            except:
                pass


class IncrementalSync:
    """增量同步管理器（基于最新时间戳）"""
    
    def __init__(self, config):
        self.config = config
        self.igpsport = IGPSportClient(
            config['igpsport']['username'],
            config['igpsport']['password']
        )
        onelap_tab = config.get('onelap', {}).get('tab')
        onelap_owns_tab = config.get('onelap', {}).get('owns_tab', True)
        self.onelap = OneLapClient(
            config['onelap']['username'],
            config['onelap']['password'],
            tab=onelap_tab,
            owns_tab=onelap_owns_tab
        )
        self.download_dir = './incremental_sync'
        os.makedirs(self.download_dir, exist_ok=True)
    
    def run(self, dry_run=False):
        """
        执行增量同步（基于时间戳）
        
        参数:
            dry_run: 如果为True，只比对不下载不上传（预览模式）
        """
        logger.info("="*70)
        logger.info("iGPSport → OneLap 增量同步（基于最新时间戳）")
        logger.info("="*70)
        
        # 1. 登录两个平台
        logger.info("\n【步骤1】登录两个平台...")
        if not self.igpsport.login():
            return False
        if not self.onelap.login():
            return False
        
        # 2. 获取 iGPSport 所有记录
        logger.info("\n【步骤2】获取 iGPSport 所有记录...")
        igpsport_acts = self.igpsport.get_all_activities()
        
        if not igpsport_acts:
            logger.error("[iGPSport] 没有获取到数据")
            return False
        
        logger.info(f"[iGPSport] 共 {len(igpsport_acts)} 条记录")
        
        # 3. 获取 OneLap 最新记录时间
        logger.info("\n【步骤3】获取 OneLap 最新记录时间...")
        latest_time = self.onelap.get_latest_activity_time()
        
        if not latest_time:
            logger.warning("[OneLap] 无法获取最新时间，将同步所有 iGPSport 记录")
            incremental = igpsport_acts
        else:
            logger.info(f"[对比] OneLap 最新记录时间: {latest_time.strftime('%Y-%m-%d')}")
            
            # 4. 筛选出 iGPSport 中时间 > OneLap 最新时间的记录
            logger.info("\n【步骤4】筛选增量记录（时间 > OneLap 最新时间）...")
            incremental = self._find_incremental_by_time(igpsport_acts, latest_time)
        
        if not incremental:
            logger.info("\n✅ 没有需要同步的增量数据")
            return True
        
        logger.info(f"\n📈 找到 {len(incremental)} 条增量记录")
        
        # 显示增量记录
        logger.info("\n增量记录列表:")
        for i, act in enumerate(incremental, 1):
            logger.info(f"  {i}. {act.start_time} - {act.distance/1000:.1f}km")
        
        # 如果是预览模式，到这里结束
        if dry_run:
            logger.info("\n📋 预览模式完成，未执行实际同步")
            return True
        
        # 5. 下载增量文件
        logger.info(f"\n【步骤5】下载 {len(incremental)} 个增量文件...")
        downloaded = self._download_incremental(incremental)
        
        if not downloaded:
            logger.error("没有成功下载任何文件")
            return False
        
        # 6. 上传到 OneLap
        logger.info(f"\n【步骤6】上传到 OneLap...")
        uploaded = self._upload_to_onelap(downloaded)
        
        # 7. 报告
        logger.info("\n" + "="*70)
        logger.info("📋 同步报告")
        logger.info("="*70)
        logger.info(f"iGPSport 总记录: {len(igpsport_acts)}")
        logger.info(f"OneLap 最新时间: {latest_time.strftime('%Y-%m-%d') if latest_time else 'N/A'}")
        logger.info(f"增量记录: {len(incremental)}")
        logger.info(f"成功下载: {len(downloaded)}")
        logger.info(f"成功上传: {uploaded}")
        logger.info("="*70)
        
        if uploaded == len(downloaded):
            logger.info("✅ 增量同步完成！")
            return True
        else:
            logger.warning(f"⚠️ 部分上传失败: {uploaded}/{len(downloaded)}")
            return False
    
    def _find_incremental_by_time(self, source_list, latest_time):
        """
        基于时间筛选增量记录
        返回 iGPSport 中时间 > latest_time 的记录
        """
        incremental = []
        
        for act in source_list:
            try:
                act_time = act.start_time_obj
                if not act_time:
                    continue

                if act_time > latest_time:
                    incremental.append(act)
            except Exception as e:
                logger.debug(f"时间解析失败: {act.start_time}, 错误: {e}")
                continue

        # 按时间排序（新的在前）
        incremental.sort(key=lambda x: x.start_time_obj or datetime.min, reverse=True)
        
        return incremental
    
    def _download_incremental(self, activities):
        """下载增量文件"""
        downloaded = []
        
        for i, act in enumerate(activities, 1):
            logger.info(f"  [{i}/{len(activities)}] 下载: {act.start_time} ({act.distance/1000:.1f}km)")
            
            safe_start_time = sanitize_filename_component(act.start_time)
            filename = f"{safe_start_time}-{act.ride_id}.fit"
            filepath = os.path.join(self.download_dir, filename)
            
            # 如果文件已存在，跳过下载
            if os.path.exists(filepath):
                if os.path.getsize(filepath) > 0:
                    logger.info(f"      ⏭️  文件已存在，跳过")
                    downloaded.append((act, filepath))
                    continue
                logger.warning("      [WARN] 发现空文件，准备重新下载")
                os.remove(filepath)

            part_path = f"{filepath}.part"
            if os.path.exists(part_path):
                logger.warning("      [WARN] 发现未完成临时文件，准备重新下载")
                os.remove(part_path)

            if self.igpsport.download_file(act.ride_id, filepath):
                file_size = os.path.getsize(filepath)
                logger.info(f"      ✅ 完成 ({file_size/1024:.1f} KB)")
                downloaded.append((act, filepath))
            else:
                logger.error(f"      ❌ 下载失败")
            
            time.sleep(0.3)  # 避免请求过快
        
        return downloaded
    
    def _upload_to_onelap(self, file_list):
        """上传到 OneLap"""
        uploaded = 0
        
        for i, (act, filepath) in enumerate(file_list, 1):
            logger.info(f"\n  [{i}/{len(file_list)}] 上传: {os.path.basename(filepath)}")
            logger.info(f"      日期: {act.start_time}, 距离: {act.distance/1000:.1f}km")
            
            if self.onelap.upload_file(filepath, expected_time=act.start_time_obj):
                logger.info(f"      ✅ 上传成功")
                uploaded += 1
            else:
                logger.error(f"      ❌ 上传失败")
        
        return uploaded
    
    def cleanup(self):
        """清理资源"""
        self.onelap.close()


def main():
    """主函数"""
    # 读取配置
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE_PATH, encoding='utf-8-sig')
    
    sync_config = {
        'igpsport': {
            'username': config.get('igpsport', 'username', fallback=''),
            'password': config.get('igpsport', 'password', fallback='')
        },
        'onelap': {
            'username': config.get('onelap', 'username', fallback=''),
            'password': config.get('onelap', 'password', fallback='')
        }
    }
    
    if not sync_config['igpsport']['username'] or not sync_config['onelap']['username']:
        logger.error("请在 settings.ini 中配置账号密码")
        return
    
    # 询问是否预览模式
    print("\n选择运行模式:")
    print("1. 预览模式（只比对，不下载不上传）")
    print("2. 完整同步（下载并上传增量）")
    
    choice = input("\n请输入选项 (1/2): ").strip()
    dry_run = (choice == '1')
    
    # 执行同步
    sync = IncrementalSync(sync_config)

    try:
        success = sync.run(dry_run=dry_run)
        if success:
            print("\n同步完成！")
        else:
            print("\n同步遇到问题")
    finally:
        sync.cleanup()


if __name__ == '__main__':
    main()
