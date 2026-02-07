#!/usr/bin/env python3
"""
iGPSport → OneLap 增量同步（基于最新时间戳）
策略：只同步 iGPSport 中时间晚于 OneLap 最新记录的数据
"""

import os
import sys
import json
import time
import configparser
import logging
from datetime import datetime
from collections import namedtuple

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('IncrementalSync')

ActivityRecord = namedtuple('ActivityRecord', [
    'ride_id', 'start_time', 'distance', 'duration', 'platform', 'download_url'
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
        data = json.dumps({
            'username': self.username,
            'password': self.password,
            'appId': 'igpsport-web'
        }).encode()
        
        req = urllib.request.Request(url, data=data, 
                                     headers={'Content-Type': 'application/json'})
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_data = json.loads(response.read().decode())
                if resp_data['code'] != 0:
                    logger.error(f"[iGPSport] 登录失败: {resp_data.get('message')}")
                    return False
                
                self.token = resp_data['data']['access_token']
                logger.info("[iGPSport] ✅ 登录成功")
                return True
        except Exception as e:
            logger.error(f"[iGPSport] 登录异常: {e}")
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
                        # 使用 startTime 字段（格式: 2026.02.05）
                        start_time = item.get('startTime', '')
                        # 转换为标准格式: 2026-02-05
                        if start_time:
                            start_time = start_time.replace('.', '-')
                        else:
                            start_time = "Unknown"
                        
                        # 使用 rideDistance（米）
                        distance = float(item.get('rideDistance', 0) or 0)
                        
                        # 使用 totalMovingTime（秒）
                        duration = int(item.get('totalMovingTime', 0) or 0)
                        
                        activity = ActivityRecord(
                            ride_id=str(item.get('rideId', '')),
                            start_time=start_time,
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
        
        url = f"{self.BASE_URL}/web-gateway/web-analyze/activity/getDownloadUrl/{ride_id}"
        req = urllib.request.Request(url)
        req.add_header('Authorization', f"Bearer {self.token}")
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                resp_data = json.loads(response.read().decode())
                if resp_data['code'] != 0:
                    return False
                
                download_url = resp_data['data']
                
                req2 = urllib.request.Request(download_url)
                req2.add_header('Authorization', f"Bearer {self.token}")
                
                with urllib.request.urlopen(req2, timeout=60) as resp, \
                     open(output_path, 'wb') as out_file:
                    out_file.write(resp.read())
                
                return True
        except Exception as e:
            logger.error(f"[iGPSport] 下载失败: {e}")
            return False


class OneLapClient:
    """OneLap 平台客户端"""
    
    def __init__(self, username, password, tab=None, owns_tab=True):
        self.username = username
        self.password = password
        self.tab = tab
        self.owns_tab = owns_tab
    
    def login(self):
        """登录 OneLap"""
        try:
            from DrissionPage import ChromiumPage, ChromiumOptions
        except ImportError:
            logger.error("[OneLap] 请先安装 DrissionPage")
            return False
        
        if self.tab:
            logger.info("[OneLap] 复用已有浏览器实例")
            return True

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
            self.tab.get('https://www.onelap.cn/login.html')
            time.sleep(3)
            
            self.tab.ele('.from1 login_1', timeout=10).clear().input(self.username)
            self.tab.ele('.from1 login_password ', timeout=10).clear().input(self.password)
            self.tab.ele('.from_yellow_btn', timeout=10).click()
            
            time.sleep(5)
            
            if 'login' in self.tab.url.lower():
                logger.error("[OneLap] 登录失败")
                return False
            
            logger.info("[OneLap] ✅ 登录成功")
            return True
            
        except Exception as e:
            logger.error(f"[OneLap] 登录异常: {e}")
            return False
    
    def get_latest_activity_time(self):
        """
        获取 OneLap 最新一条记录的时间（第一页第一条，倒序排列）
        返回: datetime 对象 或 None
        """
        if not self.tab:
            logger.error("[OneLap] 未登录")
            return None
        
        logger.info("[OneLap] 获取最新记录时间...")
        
        try:
            self.tab.get('https://u.onelap.cn/analysis')
            time.sleep(3)
            
            # 解析第一页的数据（不需要滚动，第一条就是最新的）
            html_content = self.tab.html
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # 找到第一条记录
            first_row = soup.find('div', class_='list')
            if not first_row:
                logger.warning("[OneLap] 没有找到任何记录")
                return None
            
            date_div = first_row.find('div', class_='date')
            if not date_div:
                logger.warning("[OneLap] 无法解析时间")
                return None
            
            time_str = date_div.text.strip()
            logger.info(f"[OneLap] 最新记录时间: {time_str}")
            
            # 解析时间字符串
            try:
                # 尝试多种格式
                for fmt in ['%Y-%m-%d %H:%M', '%Y.%m.%d %H:%M', '%Y-%m-%d', '%Y.%m.%d']:
                    try:
                        dt = datetime.strptime(time_str[:len(fmt)], fmt)
                        return dt
                    except:
                        continue
                # 如果都失败，尝试直接解析
                dt = datetime.strptime(time_str[:10], '%Y-%m-%d')
                return dt
            except Exception as e:
                logger.error(f"[OneLap] 时间解析失败: {e}")
                return None
            
        except Exception as e:
            logger.error(f"[OneLap] 获取最新时间异常: {e}")
            return None
    
    def upload_file(self, file_path):
        """
        上传单个 FIT 文件
        优化的批量上传：只在首次加载页面，之后复用同一页面
        """
        if not self.tab:
            return False
        
        try:
            # 检查是否需要加载页面（首次上传或不在分析页面）
            if 'analysis' not in self.tab.url:
                logger.info(f"      🔄 加载上传页面...")
                self.tab.get('https://u.onelap.cn/analysis')
                time.sleep(3)
            
            # 查找上传按钮
            try:
                upload_input = self.tab.ele('#jilu', timeout=10)
            except:
                upload_input = self.tab.ele('input[type="file"]', timeout=5)
            
            # 选择文件上传
            upload_input.input(file_path)
            logger.info(f"      📤 文件已选择，等待上传...")
            
            # 等待上传完成
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
                # 解析 iGPSport 记录的时间
                act_time = datetime.strptime(act.start_time, '%Y-%m-%d')
                
                # 只比较日期部分
                if act_time.date() > latest_time.date():
                    incremental.append(act)
            except Exception as e:
                logger.debug(f"时间解析失败: {act.start_time}, 错误: {e}")
                continue
        
        # 按时间排序（新的在前）
        incremental.sort(key=lambda x: x.start_time, reverse=True)
        
        return incremental
    
    def _download_incremental(self, activities):
        """下载增量文件"""
        downloaded = []
        
        for i, act in enumerate(activities, 1):
            logger.info(f"  [{i}/{len(activities)}] 下载: {act.start_time} ({act.distance/1000:.1f}km)")
            
            filename = f"{act.start_time}-{act.ride_id}.fit"
            filepath = os.path.join(self.download_dir, filename)
            
            # 如果文件已存在，跳过下载
            if os.path.exists(filepath):
                logger.info(f"      ⏭️  文件已存在，跳过")
                downloaded.append((act, filepath))
                continue
            
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
            
            if self.onelap.upload_file(filepath):
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
    config.read('settings.ini', encoding='utf-8-sig')
    
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
            print("\n🎉 同步完成！")
        else:
            print("\n⚠️ 同步遇到问题")
    finally:
        sync.cleanup()


if __name__ == '__main__':
    main()
