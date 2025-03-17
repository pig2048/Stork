import os
import sys
import json
import time
import random
import asyncio
import logging
import logging.handlers  
import requests
import traceback
import threading
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from colorama import init, Fore, Back, Style
import base64
import aiohttp
from pycognito import Cognito  


init(autoreset=True)


start_time = time.time()
current_config = {}
user_data = {}
validation_status = ""
price_data = {}
accounts = []
last_display_lines = 0


logger = logging.getLogger("stork_bot")
logger.setLevel(logging.INFO)


log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stork_bot.log")
file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=50*1024*1024, backupCount=3)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)


logger.addHandler(file_handler)
logger.propagate = False  


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
TOKENS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tokens.json')
PROXIES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proxies.txt')


DEFAULT_CONFIG = {
    "cognito": {
        "region": "ap-northeast-1",
        "clientId": "5msns4n49hmg3dftp2tp1t2iuh",
        "userPoolId": "ap-northeast-1_M22I44OpC",
    },
    "stork": {
        "intervalSeconds": 300 
    },
    "threads": {
        "maxWorkers": 1
    }
}


previous_stats = {"validCount": 0, "invalidCount": 0}


try:
    from accounts import accounts
except ImportError:
    print(f"{Fore.RED}[ERROR] accounts.py not found or has errors. Creating a template file...{Style.RESET_ALL}")
    with open("accounts.py", "w") as f:
        f.write("""
# List of accounts to use for validation
accounts = [
    {
        "username": "YOUR_EMAIL",
        "password": "YOUR_PASSWORD"
    }
    # Add more accounts as needed
]
""")
    accounts = []

def log(message: str, level: str = "INFO") -> None:
   
    
    clean_message = ''.join(c for c in message if ord(c) < 127)
    
    if level.upper() == "DEBUG":
        logger.debug(clean_message)
    elif level.upper() == "INFO":
        logger.info(clean_message)
    elif level.upper() == "WARN" or level.upper() == "WARNING":
        logger.warning(clean_message)
    elif level.upper() == "ERROR":
        logger.error(clean_message)
    elif level.upper() == "CRITICAL":
        logger.critical(clean_message)
    elif level.upper() == "API" or level.upper() == "SUCCESS":
        logger.info(clean_message)
    
    
    


def load_config() -> Dict:
   
    try:
        if not os.path.exists(CONFIG_PATH):
            log(f"Config file not found at {CONFIG_PATH}, using default configuration", "WARN")
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            return DEFAULT_CONFIG
        
        with open(CONFIG_PATH, 'r') as f:
            user_config = json.load(f)
        
        log('Configuration loaded successfully from config.json')
        log('Accounts loaded successfully from accounts.py')
        return user_config
    except Exception as e:
        log(f"Error loading config: {str(e)}", "ERROR")
        return DEFAULT_CONFIG


def validate_config() -> bool:
   
    if not accounts or not accounts[0].get("username") or not accounts[0].get("password"):
        log('ERROR: Username and password must be set in accounts.py', "ERROR")
        print(f"\n{Fore.YELLOW}Please update your accounts.py file with your credentials:{Style.RESET_ALL}")
        print(json.dumps({
            "username": "YOUR_EMAIL",
            "password": "YOUR_PASSWORD"
        }, indent=2))
        return False
    return True


def load_proxies() -> List[str]:
   
    try:
        if not os.path.exists(PROXIES_PATH):
            log(f"Proxy file not found at {PROXIES_PATH}, creating empty file", "WARN")
            with open(PROXIES_PATH, 'w') as f:
                pass
            return []
        
        with open(PROXIES_PATH, 'r') as f:
            proxies = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
        
        
        random.shuffle(proxies)
        
        log(f"Loaded {len(proxies)} proxies from {PROXIES_PATH}")
        if proxies:
            log(f"Trying to run with {proxies[0]}")
        return proxies
    except Exception as e:
        log(f"Error loading proxies: {str(e)}", "ERROR")
        return []


def save_tokens(tokens: Dict, username: str) -> bool:
   
    try:
        log(f"开始保存用户 {username} 的tokens...", "INFO")
        
        
        all_tokens = {}
        if os.path.exists(TOKENS_PATH):
            try:
                with open(TOKENS_PATH, 'r') as f:
                    file_content = f.read().strip()
                    if file_content:  
                        all_tokens = json.loads(file_content)
                        log(f"成功读取现有的tokens文件，包含 {len(all_tokens)} 个账户", "INFO")
                    else:
                        log("tokens.json文件为空，将创建新文件", "WARN")
            except json.JSONDecodeError as e:
                log(f"tokens.json文件损坏: {str(e)}，将重新创建", "WARN")
            except Exception as e:
                log(f"读取tokens.json时出错: {str(e)}，将重新创建", "WARN")
        else:
            log("tokens.json文件不存在，将创建新文件", "INFO")
        
        
        if 'expiresIn' in tokens and 'expiresAt' not in tokens:
            tokens['expiresAt'] = int(time.time() * 1000) + tokens['expiresIn']
            log(f"为用户 {username} 添加了expiresAt时间戳: {tokens['expiresAt']}", "INFO")
        
        
        required_fields = ['accessToken', 'idToken', 'refreshToken']
        missing_fields = [field for field in required_fields if field not in tokens or not tokens[field]]
        
        if missing_fields:
            log(f"警告: 用户 {username} 的tokens缺少以下字段: {', '.join(missing_fields)}", "WARN")
        
        
        all_tokens[username] = tokens
        log(f"已将用户 {username} 的tokens添加到内存中", "INFO")
        
        
        with open(TOKENS_PATH, 'w') as f:
            json.dump(all_tokens, f, indent=2)
        
        
        if os.path.exists(TOKENS_PATH):
            file_size = os.path.getsize(TOKENS_PATH)
            if file_size > 0:
                log(f"成功保存用户 {username} 的tokens到文件，文件大小: {file_size} 字节", "SUCCESS")
                
                
                try:
                    with open(TOKENS_PATH, 'r') as f:
                        saved_tokens = json.load(f)
                    if username in saved_tokens:
                        log(f"验证成功: 用户 {username} 的tokens已正确保存", "SUCCESS")
                    else:
                        log(f"验证失败: 文件中未找到用户 {username} 的tokens", "ERROR")
                        return False
                except Exception as e:
                    log(f"验证tokens文件时出错: {str(e)}", "ERROR")
                    return False
            else:
                log(f"保存失败: tokens.json文件大小为0", "ERROR")
                return False
        else:
            log(f"保存失败: tokens.json文件不存在", "ERROR")
            return False
        
        return True
    except Exception as e:
        log(f"保存tokens错误: {str(e)}", "ERROR")
        return False


def validate_tokens(tokens: Dict) -> bool:
    
    required_fields = ['accessToken', 'idToken', 'refreshToken']
    
    if not isinstance(tokens, dict):
        return False
        
    for field in required_fields:
        if field not in tokens or not tokens[field]:
            return False
    
    
    if 'expiresIn' not in tokens and 'expiresAt' not in tokens:
        return False
            
    return True


def get_tokens(username: str = None) -> Dict:
    
    try:
        log(f"尝试读取{'用户 ' + username if username else '所有用户'}的tokens...", "INFO")
        
        if not os.path.exists(TOKENS_PATH):
            log(f"Tokens文件不存在: {TOKENS_PATH}", "ERROR")
            raise FileNotFoundError(f"Tokens文件不存在: {TOKENS_PATH}")
        
        
        if os.path.getsize(TOKENS_PATH) == 0:
            log("Tokens文件为空", "ERROR")
            raise ValueError("tokens.json为空")
        
        try:
            with open(TOKENS_PATH, 'r') as f:
                file_content = f.read().strip()
                if not file_content:
                    log("Tokens文件内容为空", "ERROR")
                    raise ValueError("tokens.json内容为空")
                all_tokens = json.loads(file_content)
        except json.JSONDecodeError as e:
            log(f"Tokens文件格式错误: {str(e)}", "ERROR")
            raise ValueError(f"Tokens文件格式错误: {str(e)}")
        
        log(f"成功读取tokens文件，包含 {len(all_tokens)} 个账户", "INFO")
        
        
        if username:
            if username not in all_tokens:
                log(f"未找到用户 {username} 的tokens", "ERROR")
                raise ValueError(f"未找到用户 {username} 的tokens")
            tokens = all_tokens[username]
            log(f"成功获取用户 {username} 的tokens", "SUCCESS")
        else:
            
            if not all_tokens:
                log("tokens.json为空", "ERROR")
                raise ValueError("tokens.json为空")
            first_username = next(iter(all_tokens.keys()))
            tokens = all_tokens[first_username]
            log(f"未指定用户名，返回第一个用户 {first_username} 的tokens", "INFO")
        
        
        if not validate_tokens(tokens):
            log(f"用户 {username or first_username} 的tokens格式无效", "ERROR")
            raise ValueError("无效的tokens格式")
        
        
        current_time = time.time() * 1000  
        if 'expiresAt' in tokens and tokens['expiresAt'] < current_time:
            time_expired = (current_time - tokens['expiresAt']) / 1000 / 60  
            log(f"警告: 用户 {username or first_username} 的token已过期 {int(time_expired)} 分钟", "WARN")
        elif 'expiresAt' in tokens:
            time_remaining = (tokens['expiresAt'] - current_time) / 1000 / 60 
            log(f"用户 {username or first_username} 的token还有 {int(time_remaining)} 分钟过期", "INFO")
        
        log(f"成功读取access token: {tokens.get('accessToken', '')[:10]}...", "SUCCESS")
        return tokens
    except Exception as e:
        log(f"读取tokens错误: {str(e)}", "ERROR")
        raise


class CognitoAuth:
   
    
    def __init__(self, username: str, password: str, config: Dict):
        self.username = username
        self.password = password
        self.config = config
        self.region = config['cognito']['region']
        self.client_id = config['cognito']['clientId']
        self.user_pool_id = config['cognito']['userPoolId']
        self.auth_url = f"https://cognito-idp.{self.region}.amazonaws.com/"
        self.logger = logging.getLogger(__name__)
        
        
        self.proxies = load_proxies()
        self.current_proxy_index = 0
    
    def _get_proxy(self):
       
        if not self.proxies:
            return None
        
        
        proxy = self.proxies[self.current_proxy_index]
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        
        log(f"使用代理: {proxy}", "INFO")
        return {
            'http': proxy,
            'https': proxy
        }
    
    def _save_tokens(self, username, tokens):
        
        try:
            
            tokens_data = {}
            try:
                with open(TOKENS_PATH, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        tokens_data = json.loads(content)
            except (FileNotFoundError, json.JSONDecodeError) as e:
                self.logger.warning(f"无法读取tokens.json文件: {str(e)}")
                
                tokens_data = {}
            
            
            tokens_data[username] = tokens
            
            
            with open(TOKENS_PATH, 'w', encoding='utf-8') as f:
                json.dump(tokens_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"成功保存用户 {username} 的tokens")
            return True
        
        except Exception as e:
            self.logger.error(f"保存tokens时发生错误: {str(e)}")
            return False
    
    def test_token(self, access_token: str) -> bool:
        
        try:
            
            url = 'https://app-api.jp.stork-oracle.network/v1/me'
            headers = {
                'Authorization': f"Bearer {access_token}",
                'Content-Type': 'application/json',
                'Origin': 'chrome-extension://knnliglhgkmlblppdejchidfihjnockl',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
            }
            
            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                log(f"Token for {self.username[:3]}***@***{self.username[-3:]} is valid", "SUCCESS")
                return True
            else:
                log(f"Token for {self.username[:3]}***@***{self.username[-3:]} is invalid: {response.status_code}", "WARN")
                return False
                
        except Exception as e:
            log(f"Error testing token: {str(e)}", "ERROR")
            return False
    
    def authenticate(self, username, password):
       
        log(f"Authenticating user {username[:3]}***@***{username[-3:]}")
        
        
        max_retries = 5
        retry_delay = 30
        last_error = None
        
        for attempt in range(max_retries):
            try:
                log(f"认证尝试 {attempt+1}/{max_retries}")
                
                
                u = Cognito(
                    user_pool_id=self.user_pool_id,
                    client_id=self.client_id,
                    username=username
                )
                
                
                u.authenticate(password=password)
                
                
                access_token = u.access_token
                id_token = u.id_token
                refresh_token = u.refresh_token
                expires_in = 3600  
                
                if not access_token or not id_token or not refresh_token:
                    log("认证成功但未获取到完整的token", "ERROR")
                    raise Exception("认证成功但未获取到完整的token")
                
                
                expires_at = int(time.time() * 1000) + (expires_in * 1000)
                
                
                tokens = {
                    'accessToken': access_token,
                    'idToken': id_token,
                    'refreshToken': refresh_token,
                    'expiresIn': expires_in * 1000,  
                    'expiresAt': expires_at
                }
                
                
                self._save_tokens(username, tokens)
                log(f"用户 {username} 认证成功")
                
                return tokens
                
            except Exception as e:
                log(f"认证错误: {str(e)}", "ERROR")
                last_error = Exception(f"认证失败: {str(e)}")
                
                
                error_str = str(e).lower()
                if "too many requests" in error_str or "throttling" in error_str:
                    wait_time = retry_delay * (2 ** attempt)
                    log(f"请求过多，等待 {wait_time} 秒后重试", "WARN")
                    time.sleep(wait_time)
                    continue
                
                
                if "connection" in error_str or "timeout" in error_str:
                    wait_time = retry_delay * (2 ** attempt)
                    log(f"连接错误，等待 {wait_time} 秒后重试", "WARN")
                    time.sleep(wait_time)
                    continue
                
                
                wait_time = retry_delay * (2 ** attempt)
                log(f"认证错误，等待 {wait_time} 秒后重试", "WARN")
                time.sleep(wait_time)
        
        
        if last_error:
            raise last_error
        else:
            raise Exception("认证失败: 达到最大重试次数")
    
    def refresh_session(self, refresh_token: str) -> Dict:
       
        log(f"刷新用户token...")
        
        
        max_retries = 5
        retry_delay = 30
        last_error = None
        
        for attempt in range(max_retries):
            try:
                log(f"刷新token尝试 {attempt+1}/{max_retries}")
                
                
                u = Cognito(
                    user_pool_id=self.user_pool_id,
                    client_id=self.client_id,
                    refresh_token=refresh_token
                )
                
                
                u.renew_access_token()
                
                
                access_token = u.access_token
                id_token = u.id_token
                expires_in = 3600  
                
                if not access_token or not id_token:
                    log("刷新token成功但未获取到完整的token", "ERROR")
                    raise Exception("刷新token成功但未获取到完整的token")
                
                
                expires_at = int(time.time() * 1000) + (expires_in * 1000)
                
                
                tokens = {
                    'accessToken': access_token,
                    'idToken': id_token,
                    'refreshToken': refresh_token,  
                    'expiresIn': expires_in * 1000,  
                    'expiresAt': expires_at
                }
                
                log(f"成功刷新token")
                return tokens
                
            except Exception as e:
                log(f"刷新token错误: {str(e)}", "ERROR")
                last_error = Exception(f"刷新token失败: {str(e)}")
                
                
                error_str = str(e).lower()
                if "too many requests" in error_str or "throttling" in error_str:
                    wait_time = retry_delay * (2 ** attempt)
                    log(f"请求过多，等待 {wait_time} 秒后重试", "WARN")
                    time.sleep(wait_time)
                    continue
                
                
                if "connection" in error_str or "timeout" in error_str:
                    wait_time = retry_delay * (2 ** attempt)
                    log(f"连接错误，等待 {wait_time} 秒后重试", "WARN")
                    time.sleep(wait_time)
                    continue
                
                
                wait_time = retry_delay * (2 ** attempt)
                log(f"刷新token错误，等待 {wait_time} 秒后重试", "WARN")
                time.sleep(wait_time)
        
        
        if last_error:
            raise last_error
        else:
            raise Exception("刷新token失败: 达到最大重试次数")


class TokenManager:
    
    
    def __init__(self, account: Dict, config: Dict):
        self.access_token = None
        self.refresh_token = None
        self.id_token = None
        self.expires_at = 0
        self.last_refresh_time = 0
        self.refresh_interval = 50 * 60  
        self.username = account.get('username', account.get('email', ''))
        self.password = account.get('password', '')
        self.auth = CognitoAuth(self.username, self.password, config)
    
    def should_refresh_token(self) -> bool:
       
        current_time = time.time() * 1000  
        
        
        if not self.access_token:
            log("无token，需要获取新token", "INFO")
            return True
        
        
        if self.expires_at <= 0 or self.expires_at < current_time:
            log("Token已过期或expires_at无效，需要刷新", "INFO")
            return True
        
        
        time_until_expiry_sec = (self.expires_at - current_time) / 1000
        time_until_expiry_min = int(time_until_expiry_sec / 60)
        log(f"Token还剩 {time_until_expiry_min} 分钟过期", "INFO")
        
        
        if time_until_expiry_sec < 1800 and (time.time() - self.last_refresh_time > 3600):
            log(f"Token将在 {time_until_expiry_min} 分钟后过期，且距离上次刷新超过1小时，需要刷新", "INFO")
            return True
        
        return False
    
    async def get_valid_token(self) -> str:
      
        try:
            
            if self.access_token and not self.should_refresh_token():
                return self.access_token
            
            
            if self.should_refresh_token():
                try:
                    await self.refresh_or_authenticate()
                except Exception as e:
                    
                    if "TooManyRequestsException" in str(e) and self.access_token:
                        log("Token请求过于频繁，继续使用当前token", "WARN")
                        
                        current_time = time.time() * 1000
                        if self.expires_at < current_time + 600000:  
                            self.expires_at = current_time + 1800000  
                            log("临时延长token过期时间30分钟，避免频繁刷新", "INFO")
                        return self.access_token
                    elif "InvalidParameterException" in str(e) and self.access_token:
                        log("无效的参数，继续使用当前token", "WARN")
                        return self.access_token
                    else:
                        raise
            return self.access_token
        except Exception as e:
            if "TooManyRequestsException" in str(e):
                log("Token请求过于频繁，继续使用当前token", "WARN")
                
                if self.access_token:
                    
                    current_time = time.time() * 1000
                    if self.expires_at < current_time + 600000:  
                        self.expires_at = current_time + 1800000  
                        log("临时延长token过期时间30分钟，避免频繁刷新", "INFO")
                    return self.access_token
            elif "InvalidParameterException" in str(e):
                log("无效的参数，继续使用当前token", "WARN")
                if self.access_token:
                    return self.access_token
            raise
    
    async def refresh_or_authenticate(self) -> None:
       
        current_time = time.time() * 1000  
        
        
        if self.access_token and self.expires_at > 0:
            time_until_expiry_sec = (self.expires_at - current_time) / 1000
            
            
            if time_until_expiry_sec > 7200:  
                log(f"Token仍然有效，剩余 {int(time_until_expiry_sec/60)} 分钟，无需刷新", "INFO")
                return
            
            
            if time_until_expiry_sec > 1800 and ((current_time/1000) - self.last_refresh_time < 14400): 
                log(f"Token仍然有效，剩余 {int(time_until_expiry_sec/60)} 分钟，且距离上次刷新不到4小时，无需刷新", "INFO")
                return
        
       
        if self.last_refresh_time > 0 and (time.time() - self.last_refresh_time < 1800): 
            log(f"最近30分钟内已尝试刷新token，跳过本次刷新", "INFO")
            return
        
        
        max_retries = 2  
        retry_delay = 60  
        
        for attempt in range(max_retries):
            try:
                result = None
                if self.refresh_token:
                    try:
                        log(f"尝试使用refresh_token刷新token", "INFO")
                        result = self.auth.refresh_session(self.refresh_token)
                    except Exception as e:
                        if "TooManyRequestsException" in str(e):
                            log(f"刷新token请求过于频繁，等待下次尝试", "WARN")
                            
                            return
                        log(f"刷新token失败，尝试重新认证: {str(e)}", "WARN")
                        result = self.auth.authenticate(self.username, self.password)
                else:
                    log(f"没有refresh_token，尝试重新认证", "INFO")
                    result = self.auth.authenticate(self.username, self.password)
                
                self.access_token = result['accessToken']
                self.id_token = result['idToken']
                self.refresh_token = result['refreshToken']
                self.expires_at = result.get('expiresAt', time.time() * 1000 + result['expiresIn']) 
                self.last_refresh_time = time.time()
                
                log('Token已刷新', "SUCCESS")
                return
                
            except Exception as e:
                
                if "TooManyRequestsException" in str(e):
                    wait_time = retry_delay * (2 ** attempt)  
                    log(f"Token请求过于频繁，等待{wait_time}秒后重试", "WARN")
                    await asyncio.sleep(wait_time)
                    continue
                elif "NotAuthorizedException" in str(e):
                    log("认证失败：无效的凭证", "ERROR")
                    raise
                elif "UserNotFoundException" in str(e):
                    log("认证失败：用户不存在", "ERROR")
                    raise
                elif "InvalidParameterException" in str(e):
                    log("认证失败：无效的参数", "ERROR")
                   
                    raise
                else:
                    log(f"Token刷新/认证错误: {str(e)}", "ERROR")
                    raise
        
        raise Exception("Token刷新失败：达到最大重试次数")


class StorkAPI:
   
    
    def __init__(self, config: Dict):
      
        self.config = config
        self.base_url = config.get('api_url', 'https://app-api.jp.stork-oracle.network')
        self.origin = config.get('origin', 'chrome-extension://knnliglhgkmlblppdejchidfihjnockl')
        self.user_agent = config.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36')
        
        
        self.proxies = load_proxies()
        self.current_proxy = None
        self.current_proxy_index = 0  
        
        if self.proxies and len(self.proxies) > 0:
            self.current_proxy = self.proxies[0]
    
    def _get_proxy_config(self) -> Dict:
       
        if not self.proxies or len(self.proxies) == 0:
            return None
        
        
        if not hasattr(self, 'current_proxy') or not self.current_proxy or self.current_proxy_index >= len(self.proxies):
            self.current_proxy_index = 0
            self.current_proxy = self.proxies[0]
        
        log(f"Trying to run with {self.current_proxy}")
        
        
        proxy_config = {
            'http': self.current_proxy,
            'https': self.current_proxy
        }
        
        
        self.current_proxy_index = (self.current_proxy_index + 1) % len(self.proxies)
        self.current_proxy = self.proxies[self.current_proxy_index]
        
        return proxy_config
    
    async def get_signed_prices(self, tokens: Dict) -> List[Dict]:
        
        log("开始获取签名价格数据...", "INFO")
        
        proxy_config = self._get_proxy_config()
        proxy = proxy_config.get("proxy")
        
        if proxy:
            log(f"使用代理获取价格数据: {proxy}", "INFO")
        
        url = f"{self.base_url}/v1/stork_signed_prices"
        
        log(f"Request URL: {url}", "INFO")
        log(f"Request Method: GET", "INFO")
        
        try:
            headers = {
                'Authorization': f"Bearer {tokens['accessToken']}",
                'Content-Type': 'application/json',
                'Origin': self.origin,
                'User-Agent': self.user_agent
            }
            
            proxies = self._get_proxy_config()
            if proxies:
                log(f"使用代理获取价格数据: {self.current_proxy}", "API")
            
            
            log(f"Request URL: {url}", "API")
            log(f"Request Method: GET", "API")
            log(f"Request Headers: {headers}", "API")
            
            response = requests.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=30
            )
            
            
            log(f"Response Status: {response.status_code}", "API")
            log(f"Response Headers: {dict(response.headers)}", "API")
            
            response.raise_for_status()
            data = response.json()
            
            
            log(f"Raw Response Data Structure: {json.dumps(data, indent=2)[:500]}...", "API")
            
            if not data or not isinstance(data.get('data'), dict):
                log("响应数据为空或格式不正确", "ERROR")
                return []
            
            
            result = []
            data_obj = data.get('data', {})
            for asset_key, asset_data in data_obj.items():
                try:
                    if not isinstance(asset_data, dict):
                        log(f"跳过无效的资产数据: {asset_key}", "WARN")
                        continue
                    
                    
                    timestamped_sig = asset_data.get('timestamped_signature', {})
                    if not isinstance(timestamped_sig, dict):
                        log(f"资产 {asset_key} 的时间戳签名格式无效", "WARN")
                        continue
                    
                   
                    msg_hash = timestamped_sig.get('msg_hash')
                    if not msg_hash:
                        log(f"资产 {asset_key} 缺少msg_hash", "WARN")
                        continue
                    
                    
                    price = asset_data.get('price')
                    if not price:
                        log(f"资产 {asset_key} 缺少价格数据", "WARN")
                        continue
                    
                    
                    try:
                        price_decimal = int(price) / 1e18
                        price_str = f"{price_decimal:.8f}"
                    except ValueError:
                        price_str = price
                    
                    
                    timestamp = timestamped_sig.get('timestamp')
                    if not timestamp:
                        log(f"资产 {asset_key} 缺少时间戳", "WARN")
                        continue
                    
                   
                    log(f"资产 {asset_key} 的原始时间戳数据: {timestamp}", "INFO")
                    
                    
                    try:
                        
                        if isinstance(timestamp, str):
                            timestamp = timestamp.replace('0x', '').strip()
                            try:
                                timestamp = int(timestamp, 16)
                            except ValueError:
                                timestamp = int(float(timestamp))
                        else:
                            timestamp = int(timestamp)
                        
                        
                        log(f"资产 {asset_key} 的转换后时间戳: {timestamp}", "INFO")
                        
                        
                        timestamp_str = str(timestamp)
                        if len(timestamp_str) > 16:  
                            timestamp = timestamp // 1000000000
                        elif len(timestamp_str) > 13: 
                            timestamp = timestamp // 1000000
                        elif len(timestamp_str) > 10:  
                            timestamp = timestamp // 1000
                        
                        
                        iso_time = datetime.fromtimestamp(timestamp).isoformat()
                        log(f"资产 {asset_key} 的最终ISO时间: {iso_time}", "INFO")
                        
                    except (ValueError, OSError) as e:
                        log(f"处理资产 {asset_key} 的时间戳时出错: {str(e)}", "ERROR")
                        log(f"错误详情: timestamp={timestamp}, type={type(timestamp)}", "ERROR")
                        continue
                    
                    price_data = {
                        'asset': asset_key,
                        'msg_hash': msg_hash,
                        'price': price_str,
                        'timestamp': iso_time,
                        'raw_price': price  
                    }
                    
                    result.append(price_data)
                    log(f"成功处理资产 {asset_key}: 价格 = {price_str}", "SUCCESS")
                    
                except Exception as e:
                    log(f"处理资产 {asset_key} 时出错: {str(e)}", "ERROR")
                    continue
            
            log(f"总共处理了 {len(result)} 个有效价格数据", "SUCCESS")
            return result
            
        except requests.exceptions.RequestException as e:
            log(f"API请求失败: {str(e)}", "ERROR")
            if hasattr(e, 'response') and e.response is not None:
                log(f"错误响应: {e.response.text}", "ERROR")
            raise
        except Exception as e:
            log(f"获取价格数据时发生未知错误: {str(e)}", "ERROR")
            raise
    
    async def send_validation(self, tokens: Dict, msg_hash: str, is_valid: bool, proxy: Optional[str] = None) -> Dict:
       
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/v1/stork_signed_prices/validations"
                headers = {
                    'Authorization': f"Bearer {tokens['accessToken']}",
                    'Content-Type': 'application/json',
                    'Origin': self.origin,
                    'User-Agent': self.user_agent
                }
                data = {'msg_hash': msg_hash, 'valid': is_valid}
                
                proxies = {'http': proxy, 'https': proxy} if proxy else None
                
                response = requests.post(
                    url,
                    headers=headers,
                    json=data,
                    proxies=proxies,
                    timeout=30
                )
                
                try:
                    response.raise_for_status()
                    return {'success': True, 'data': response.json()}
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 401:
                        log("认证错误 - token可能无效", "ERROR")
                        raise
                    elif e.response.status_code == 429:
                        wait_time = retry_delay * (2 ** attempt)
                        log(f"请求频率限制 - 等待{wait_time}秒", "WARN")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        log(f"HTTP错误 {e.response.status_code}: {e.response.text}", "ERROR")
                        raise
                    
            except requests.exceptions.ConnectionError:
                log("连接错误 - 检查网络或代理设置", "ERROR")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                raise
            except requests.exceptions.Timeout:
                log("请求超时", "ERROR")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (2 ** attempt))
                    continue
                raise
            except Exception as e:
                log(f"验证请求错误: {str(e)}", "ERROR")
                raise
        
        return {'success': False, 'error': '达到最大重试次数'}
    
    async def get_user_stats(self, tokens: Dict) -> Dict:
       
        log('🔄 获取用户统计数据...')
        
        
        proxy_config = self._get_proxy_config()
        if proxy_config:
            log(f'🌐 使用代理获取用户统计: {proxy_config["http"]}')
        
        
        max_retries = 5
        retry_delay = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
             
                timeout = 30  
                
                
                url = 'https://app-api.jp.stork-oracle.network/v1/me'
                headers = {
                    'Authorization': f"Bearer {tokens['accessToken']}",
                    'Content-Type': 'application/json',
                    'Origin': 'chrome-extension://knnliglhgkmlblppdejchidfihjnockl',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36'
                }
                
              
                log(f"Request URL: {url}", "DEBUG")
                log(f"Request Method: GET", "DEBUG")
                log(f"Request Headers: {headers}", "DEBUG")
                
               
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=headers,
                        proxy=proxy_config.get('http') if proxy_config else None,
                        timeout=timeout,
                        ssl=False 
                    ) as response:
                      
                        log(f'📥 收到用户统计响应状态码: {response.status}')
                        
                        if response.status == 200:
                           
                            log('✅ 成功获取用户统计数据')
                            response_data = await response.json()
                            
                          
                            log(f"完整响应数据: {json.dumps(response_data, ensure_ascii=False)}", "DEBUG")
                            
                           
                            data = None
                            if 'data' in response_data:
                           
                                data = response_data['data']
                            else:
                               
                                data = response_data
                            
                            
                            if not data:
                                raise Exception("API返回的数据为空")
                            
                           
                            user_info = {}
                            
                            
                            if isinstance(data, dict):
                               
                                if 'id' in data:
                                    user_info['userId'] = data['id']
                                    log(f"从API响应中提取用户ID: {user_info['userId']}", "INFO")
                                
                               
                                if 'referral_code' in data:
                                    user_info['referralCode'] = data['referral_code']
                                    log(f"从API响应中提取推荐码: {user_info['referralCode']}", "INFO")
                                elif 'referralCode' in data:
                                    user_info['referralCode'] = data['referralCode']
                                    log(f"从API响应中提取推荐码: {user_info['referralCode']}", "INFO")
                                
                              
                                if 'email' in data:
                                    user_info['email'] = data['email']
                                    log(f"从API响应中提取邮箱: {user_info['email']}", "INFO")
                            
                            
                            if 'userId' not in user_info or 'referralCode' not in user_info:
                                try:
                                    id_token = tokens.get('idToken', '')
                                    if id_token:
                                       
                                        log(f"尝试从ID token解析用户信息，token长度: {len(id_token)}", "DEBUG")
                                        
                                        
                                        token_parts = id_token.split('.')
                                        if len(token_parts) == 3:
                                         
                                            payload = token_parts[1]
                                          
                                            payload += '=' * ((4 - len(payload) % 4) % 4)
                                            
                                            try:
                                               
                                                decoded_payload = base64.b64decode(payload)
                                                token_data = json.loads(decoded_payload.decode('utf-8', errors='ignore'))
                                                
                                          
                                                log(f"成功解码token payload，包含字段: {list(token_data.keys())}", "DEBUG")
                                                
                                               
                                                if 'userId' not in user_info and 'sub' in token_data:
                                                    user_info['userId'] = token_data['sub']
                                                    log(f"从ID token中提取用户ID: {user_info['userId']}", "INFO")
                                                
                                                if 'referralCode' not in user_info:
                                                
                                                    for field in ['custom:referral_code', 'referral_code', 'referralCode']:
                                                        if field in token_data and token_data[field]:
                                                            user_info['referralCode'] = token_data[field]
                                                            log(f"从ID token中提取推荐码: {user_info['referralCode']}", "INFO")
                                                            break
                                                
                                                if 'email' not in user_info and 'email' in token_data:
                                                    user_info['email'] = token_data['email']
                                                    log(f"从ID token中提取邮箱: {user_info['email']}", "INFO")
                                            except Exception as e:
                                                log(f"解析token payload失败: {str(e)}", "WARN")
                                except Exception as e:
                                    log(f"解析ID token失败: {str(e)}", "WARN")
                            
                           
                            user_data = {
                                "username": user_info.get("email", data.get("email", "未知")),
                                "userId": user_info.get("userId", data.get("userId", data.get("id", "未知"))),
                                "referralCode": user_info.get("referralCode", data.get("referralCode", data.get("referral_code", "未知"))),
                                "validations": data.get("validations", [])
                            }
                            
                           
                            if "stats" in data:
                                user_data["stats"] = data["stats"]
                            elif "validations" in data:
                               
                                valid_count = 0
                                invalid_count = 0
                                for validation in data["validations"]:
                                    if validation.get("valid", False):
                                        valid_count += 1
                                    else:
                                        invalid_count += 1
                                
                                user_data["stats"] = {
                                    "valid": valid_count,
                                    "invalid": invalid_count,
                                    "total": valid_count + invalid_count,
                                    "lastCheck": data.get("lastCheck", "")
                                }
                            else:
                               
                                user_data["stats"] = {
                                    "valid": 0,
                                    "invalid": 0,
                                    "total": 0,
                                    "lastCheck": ""
                                }
                            
                            log(f"构建的用户数据: {user_data}", "DEBUG")
                            return user_data
                        else:
                           
                            error_text = await response.text()
                            log(f'❌ 获取用户统计失败: {response.status} - {error_text}', "ERROR")
                            
                         
                            if response.status == 401:
                                raise Exception(f"认证失败: {error_text}")
                            
                            
                            if response.status >= 500:
                                wait_time = retry_delay * (2 ** attempt)
                                log(f"服务器错误，等待 {wait_time} 秒后重试...", "WARN")
                                await asyncio.sleep(wait_time)
                                continue
                            
                            raise Exception(f"请求失败: {response.status} - {error_text}")
            
            except aiohttp.ClientConnectorError as e:
                
                log(f"连接错误: {str(e)}", "ERROR")
                last_error = e
                wait_time = retry_delay * (2 ** attempt)
                log(f"连接错误，等待 {wait_time} 秒后重试...", "WARN")
                await asyncio.sleep(wait_time)
                
            except aiohttp.ClientSSLError as e:
              
                log(f"SSL错误: {str(e)}", "ERROR")
                last_error = e
                wait_time = retry_delay * (2 ** attempt)
                log(f"SSL错误，等待 {wait_time} 秒后重试，尝试禁用SSL验证...", "WARN")
                await asyncio.sleep(wait_time)
                
            except aiohttp.ClientError as e:
               
                log(f"客户端错误: {str(e)}", "ERROR")
                last_error = e
                wait_time = retry_delay * (2 ** attempt)
                log(f"客户端错误，等待 {wait_time} 秒后重试...", "WARN")
                await asyncio.sleep(wait_time)
                
            except asyncio.TimeoutError:
              
                log("请求超时", "ERROR")
                last_error = Exception("请求超时")
                wait_time = retry_delay * (2 ** attempt)
                log(f"请求超时，等待 {wait_time} 秒后重试...", "WARN")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
              
                log(f"❌ 获取用户统计失败: {str(e)}", "ERROR")
                last_error = e
                
               
                if "认证失败" in str(e):
                    raise
                
                wait_time = retry_delay * (2 ** attempt)
                log(f"未知错误，等待 {wait_time} 秒后重试...", "WARN")
                await asyncio.sleep(wait_time)
        
      
        log("所有重试都失败，返回默认用户数据", "WARN")
        
      
        user_info = {}
        try:
            id_token = tokens.get('idToken', '')
            if id_token:
                
                token_parts = id_token.split('.')
                if len(token_parts) == 3:
                  
                    payload = token_parts[1]
                 
                    payload += '=' * ((4 - len(payload) % 4) % 4)
                   
                    decoded_payload = base64.b64decode(payload)
                    token_data = json.loads(decoded_payload)
                    
                   
                    user_info = {
                        "email": token_data.get("email", "未知"),
                        "userId": token_data.get("sub", "未知"),
                        "referralCode": token_data.get("custom:referral_code", "未知")
                    }
                    log(f"从ID token中提取的用户信息: {user_info}", "DEBUG")
        except Exception as e:
            log(f"解析ID token失败: {str(e)}", "WARN")
        
      
        default_user_data = {
            "username": user_info.get("email", "未知"),
            "userId": user_info.get("userId", "未知"),
            "referralCode": user_info.get("referralCode", "未知"),
            "validations": [],
            "stats": {
                "valid": 0,
                "invalid": 0,
                "total": 0,
                "lastCheck": ""
            }
        }
        
        return default_user_data


def validate_price(price_data: Dict) -> bool:
  
   try:
       log(f"Validating data for {price_data.get('asset', 'unknown asset')}")
       
       if not price_data.get('msg_hash') or not price_data.get('price') or not price_data.get('timestamp'):
           log('Incomplete data, considered invalid', "WARN")
           return False
       
       current_time = time.time()
       data_time = datetime.fromisoformat(price_data['timestamp']).timestamp()
       time_diff_seconds = abs(current_time - data_time)
       
      
       if time_diff_seconds > 300: 
           log(f"数据时间差为 {round(time_diff_seconds)}秒，超过5分钟窗口", "WARN")
           return False
       
       log(f"数据时间差为 {round(time_diff_seconds)}秒，在有效范围内", "SUCCESS")
       return True
   except Exception as e:
       log(f"Validation error: {str(e)}", "ERROR")
       return False


class ValidationWorker:
   
   
   def __init__(self, price_data: Dict, tokens: Dict, proxy: Optional[str], config: Dict):
       self.price_data = price_data
       self.tokens = tokens
       self.proxy = proxy
       self.config = config
   
   async def validate_and_send(self) -> Dict:
    
       try:
           stork_api = StorkAPI(self.config)
           is_valid = validate_price(self.price_data)
           
           
           asset_name = self.price_data.get('asset', 'unknown')
           log(f"Validating {asset_name} price: {self.price_data.get('price', 'N/A')}")
           
           result = await stork_api.send_validation(self.tokens, self.price_data['msg_hash'], is_valid, self.proxy)
           
         
           status = "✅ valid" if is_valid else "❌ invalid"
           log(f"Price validation for {asset_name}: {status}")
           
           return {
               'success': True,
               'msg_hash': self.price_data['msg_hash'],
               'is_valid': is_valid,
               'asset': asset_name
           }
       except Exception as e:
           log(f"Validation error for {self.price_data.get('asset', 'unknown')}: {str(e)}", "ERROR")
           return {
               'success': False,
               'error': str(e),
               'msg_hash': self.price_data['msg_hash'],
               'asset': self.price_data.get('asset', 'unknown')
           }


def create_progress_bar(progress: float, width: int) -> str:
    
    
    filled_width = int(width * progress)
    empty_width = width - filled_width
    
   
    bar = "█" * filled_width + "░" * empty_width
    
    return bar


async def display_stats(user_data: Dict, validation_status: str = None, update_only: bool = False, config: Dict = None, account_index: int = 0, total_accounts: int = 1, price_data: Dict = None):
   
    global last_display_lines
    
   
    if not user_data:
        user_data = {
            "username": "未知",
            "userId": "未知",
            "referralCode": "未知",
            "validations": [],
            "stats": {
                "valid": 0,
                "invalid": 0,
                "total": 0,
                "lastCheck": ""
            }
        }
    
    
    if "stats" not in user_data:
        user_data["stats"] = {
            "valid": 0,
            "invalid": 0,
            "total": 0,
            "lastCheck": ""
        }
    
    
    username = user_data.get("username", "未知")
    if not username or username == "未知" or username == "N/A":
       
        username = user_data.get("email", "未知")
    
  
    user_id = user_data.get("userId", "未知")
    if user_id == "未知" or user_id == "N/A":
        user_id = user_data.get("user_id", "未知")
    
    
    stats = user_data.get("stats", {})
    valid_count = stats.get("valid", 0)
    if valid_count == 0:
        valid_count = stats.get("stork_signed_prices_valid_count", 0)
    
    invalid_count = stats.get("invalid", 0)
    if invalid_count == 0:
        invalid_count = stats.get("stork_signed_prices_invalid_count", 0)
    
    
    last_check = stats.get("lastCheck", "")
    if not last_check:
        last_check = stats.get("stork_signed_prices_last_verified_at", "")
    
   
    last_check_formatted = ""
    if last_check:
        try:
           
            if "T" in last_check:
                last_check_dt = datetime.fromisoformat(last_check.replace("Z", "+00:00"))
                last_check_formatted = last_check_dt.strftime("%m-%d %H:%M")
            else:
                last_check_formatted = last_check
        except:
            last_check_formatted = last_check
    
    referrals = stats.get("referrals", 0)
    if referrals == 0:
        referrals = stats.get("referral_usage_count", 0)
    
   
    referral_code = user_data.get("referralCode", "")
    if not referral_code:
        referral_code = user_data.get("referral_code", "")
    
   
    CYAN = Fore.CYAN
    GREEN = Fore.GREEN
    YELLOW = Fore.YELLOW
    RED = Fore.RED
    MAGENTA = Fore.MAGENTA
    BLUE = Fore.BLUE
    WHITE = Fore.WHITE
    BRIGHT = Style.BRIGHT
    RESET = Style.RESET_ALL
    
    
    def center_text(text: str, width: int) -> str:
        return text.center(width)
    
    
    width = 70
    
   
    title = f"{BRIGHT}{CYAN}🤖 STORK BOT - 作者:https://x.com/snifftunes{RESET}"
    
    
    current_time = datetime.now().strftime("%H:%M:%S")
    time_info = f"{YELLOW}当前时间: {current_time} • 账户 {account_index+1}/{total_accounts}{RESET}"
    
   
    status_text = ""
    if validation_status:
        
        status_text = validation_status.split("\n")[0]
        
        if "✅" in status_text:
            status_text = f"{GREEN}{status_text}{RESET}"
        elif "⚠️" in status_text:
            status_text = f"{YELLOW}{status_text}{RESET}"
        elif "❌" in status_text:
            status_text = f"{RED}{status_text}{RESET}"
        else:
            status_text = f"{BLUE}{status_text}{RESET}"
    
   
    price_info = ""
    if price_data:
       
        if isinstance(price_data, dict) and "BTCUSD" in price_data:
            btc_price = price_data["BTCUSD"].get("price", "")
            if btc_price:
                try:
                    
                    price_value = float(btc_price)
                    price_info = f"{CYAN}💰 BTC: ${price_value:.2f}{RESET}"
                except:
                    price_info = f"{CYAN}💰 BTC: {btc_price}{RESET}"
    
   
    total_lines = 12 + (2 if status_text else 0) + (2 if config else 0)
    
   
    output = []
    
    
    output.append(f"{CYAN}┌{'═' * width}┐{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(title, width)}{CYAN}│{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(time_info, width)}{CYAN}│{RESET}")
    
  
    output.append(f"{CYAN}├{'─' * width}┤{RESET}")
    
   
    if len(user_id) > 15:
        display_user_id = user_id[:12] + '...'
    else:
        display_user_id = user_id
    
    
    output.append(f"{CYAN}│{RESET}{center_text(f'{MAGENTA}👤 用户名: {BRIGHT}{username}{RESET}', width)}{CYAN}│{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(f'{MAGENTA}🆔 用户ID: {BRIGHT}{display_user_id}{RESET}', width)}{CYAN}│{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(f'{MAGENTA}🎫 推荐码: {BRIGHT}{referral_code}{RESET}', width)}{CYAN}│{RESET}")
    
   
    output.append(f"{CYAN}├{'─' * width}┤{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(f'{GREEN}✅ 有效验证: {BRIGHT}{valid_count}{RESET}', width)}{CYAN}│{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(f'{RED}❌ 无效验证: {BRIGHT}{invalid_count}{RESET}', width)}{CYAN}│{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(f'{BLUE}👥 推荐人数: {BRIGHT}{referrals}{RESET}', width)}{CYAN}│{RESET}")
    output.append(f"{CYAN}│{RESET}{center_text(f'{YELLOW}🕒 最后验证: {BRIGHT}{last_check_formatted}{RESET}', width)}{CYAN}│{RESET}")
    
  
    if price_info:
        output.append(f"{CYAN}│{RESET}{center_text(price_info, width)}{CYAN}│{RESET}")
    else:
        output.append(f"{CYAN}│{RESET}{center_text(f'{YELLOW}⏳ 等待价格数据...{RESET}', width)}{CYAN}│{RESET}")
    
    
    if status_text:
        output.append(f"{CYAN}├{'─' * width}┤{RESET}")
        output.append(f"{CYAN}│{RESET}{center_text(status_text, width)}{CYAN}│{RESET}")
    
    
    if config:
        interval = config.get('stork', {}).get('intervalSeconds', 300)
        elapsed = int(time.time() - start_time)
        remaining = max(0, interval - elapsed)
        progress = 1 - (remaining / interval)
        
        
        progress_bar = create_progress_bar(progress, width - 20)
        progress_percent = int(progress * 100)
        
       
        if progress_percent < 30:
            progress_color = RED
        elif progress_percent < 70:
            progress_color = YELLOW
        else:
            progress_color = GREEN
        
        output.append(f"{CYAN}├{'─' * width}┤{RESET}")
        output.append(f"{CYAN}│{RESET}{center_text(f'{YELLOW}⏳ {remaining}秒 {progress_color}{progress_bar}{RESET} {progress_percent}%', width)}{CYAN}│{RESET}")
    
    output.append(f"{CYAN}└{'═' * width}┘{RESET}")
    
   
    try:
        
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n".join(output), flush=True)
    except Exception as e:
       
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n".join(output), flush=True)
        log(f"显示更新时出错: {str(e)}", "ERROR")
    
   
    last_display_lines = len(output)

async def update_progress():
  
    global start_time, current_config, user_data, validation_status, price_data, accounts
    
    try:
        account_index = 0  
        last_update_time = 0
        
        while True:
            try:
                current_time = time.time()
                
                if current_time - last_update_time >= 1:
                   
                    if current_config and 'stork' in current_config:
                        interval = current_config.get('stork', {}).get('intervalSeconds', 300)
                        elapsed = int(current_time - start_time)
                        remaining = max(0, interval - elapsed)
                        
                       
                        if user_data:
                            try:
                                await display_stats(
                                    user_data, 
                                    validation_status=validation_status, 
                                    update_only=True,
                                    config=current_config,
                                    account_index=account_index,
                                    total_accounts=len(accounts) if accounts else 1,
                                    price_data=price_data
                                )
                            except Exception as e:
                                log(f"更新显示时出错: {str(e)}", "ERROR")
                    
                    last_update_time = current_time
                
             
                await asyncio.sleep(1)
            except Exception as e:
                log(f"进度更新循环中出错: {str(e)}", "ERROR")
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log(f"进度更新任务出错: {str(e)}", "ERROR")


async def run_validation_process(token_manager: TokenManager, config: Dict, account_index: int) -> bool:
   
    global validation_status, price_data
    
    try:
        
        stork_api = StorkAPI(config)
        
     
        access_token = await token_manager.get_valid_token()
        if not access_token:
            log(f"无法获取有效token，跳过验证流程", "ERROR")
            validation_status = "❌ 无法获取有效token"
            return False
            
        tokens = {
            "accessToken": access_token,
            "idToken": token_manager.id_token
        }
        
       
        try:
            log("获取价格数据...", "INFO")
            prices = await stork_api.get_signed_prices(tokens)
            
          
            processed_prices = {}
            if isinstance(prices, list):
               
                for price_item in prices:
                    if isinstance(price_item, dict) and 'asset' in price_item and 'price' in price_item:
                        asset_key = price_item['asset']
                        processed_prices[asset_key] = price_item
            elif isinstance(prices, dict):
                processed_prices = prices
                
            price_data = processed_prices
            log(f"获取到价格数据: {price_data}")
            validation_status = "✅ 成功获取价格数据"
        except Exception as e:
            log(f"获取价格数据失败: {str(e)}", "ERROR")
            validation_status = f"❌ 获取价格数据失败: {str(e)}"
            return False
        
       
        try:
           
            to_validate = []
            for asset, data in processed_prices.items():
                
                data_copy = data.copy()
                if 'asset' not in data_copy:
                    data_copy['asset'] = asset 
                to_validate.append(data_copy)
            
            if not to_validate:
                log("没有待验证的价格", "INFO")
                validation_status = "✅ 没有待验证的价格"
                return True
            
           
            log(f"找到 {len(to_validate)} 个价格待验证", "INFO")
            validation_status = f"📥 找到 {len(to_validate)} 个价格待验证"
            
         
            available_proxies = load_proxies()
            
          
            validation_tasks = []
            for price_data_item in to_validate:
               
                proxy = None
                if available_proxies:
                    proxy = random.choice(available_proxies)
                
              
                worker = ValidationWorker(price_data_item, tokens, proxy, config)
                validation_tasks.append(worker.validate_and_send())
            
           
            validation_results = await asyncio.gather(*validation_tasks)
            
           
            valid_count = sum(1 for result in validation_results if result.get('success', False) and result.get('is_valid', False))
            invalid_count = sum(1 for result in validation_results if result.get('success', False) and not result.get('is_valid', False))
            error_count = sum(1 for result in validation_results if not result.get('success', False))
            
            validation_status = f"✅ 验证完成! 有效: {valid_count}, 无效: {invalid_count}, 错误: {error_count}"
            log(f"验证结果: {validation_status}")
            return True
        except Exception as e:
            log(f"验证失败: {str(e)}", "ERROR")
            validation_status = f"❌ 验证失败: {str(e)}"
            return False
            
    except Exception as e:
        log(f"验证流程出错: {str(e)}", "ERROR")
        validation_status = f"❌ 验证流程出错: {str(e)}"
        return False


async def get_user_data(token_manager: TokenManager, config: Dict) -> Dict:
   
    try:
        
        access_token = await token_manager.get_valid_token()
        if not access_token:
            log("无法获取有效token，无法获取用户数据", "ERROR")
            raise Exception("无法获取有效token")
        
        tokens = {
            "accessToken": access_token,
            "idToken": token_manager.id_token
        }
        
       
        user_info_from_token = extract_user_info_from_token(token_manager.id_token)
        log(f"从ID token中提取的用户信息: {user_info_from_token}", "INFO")
        
        
        stork_api = StorkAPI(config)
        
        
        try:
            user_data = await stork_api.get_user_stats(tokens)
            log(f"从API获取到用户数据: {user_data}", "INFO")
        except Exception as e:
            log(f"从API获取用户数据失败: {str(e)}，将使用从token中提取的信息", "WARN")
           
            user_data = {
                "username": user_info_from_token.get("email", token_manager.username),
                "email": user_info_from_token.get("email", token_manager.username),
                "userId": user_info_from_token.get("userId", "未知"),
                "referralCode": user_info_from_token.get("referralCode", "未知"),
                "stats": {
                    "valid": 0,
                    "invalid": 0,
                    "total": 0,
                    "lastCheck": ""
                }
            }
        
        
        if not user_data:
            user_data = {}
        
       
        if "stats" not in user_data:
            user_data["stats"] = {
                "valid": 0,
                "invalid": 0,
                "total": 0,
                "lastCheck": ""
            }
        
       
        if not user_data.get("username") or user_data.get("username") == "未知":
            user_data["username"] = user_info_from_token.get("email", token_manager.username)
        
        if not user_data.get("email"):
            user_data["email"] = user_info_from_token.get("email", token_manager.username)
        
        
        if not user_data.get("userId") or user_data.get("userId") == "未知":
            user_data["userId"] = user_info_from_token.get("userId", "未知")
        
       
        if not user_data.get("referralCode") or user_data.get("referralCode") == "未知":
            user_data["referralCode"] = user_info_from_token.get("referralCode", "未知")
        
        
        log(f"最终用户数据: {user_data}", "INFO")
        
        return user_data
    except Exception as e:
        log(f"获取用户数据失败: {str(e)}", "ERROR")
        
       
        user_info = extract_user_info_from_token(token_manager.id_token)
        
        
        return {
            "username": user_info.get("email", token_manager.username),
            "email": user_info.get("email", token_manager.username),
            "userId": user_info.get("userId", "未知"),
            "referralCode": user_info.get("referralCode", "未知"),
            "stats": {
                "valid": 0,
                "invalid": 0,
                "total": 0,
                "lastCheck": ""
            }
        }


def extract_user_info_from_token(id_token: str) -> Dict:
   
    user_info = {
        "email": "未知",
        "userId": "未知",
        "referralCode": "未知"
    }
    
    if not id_token:
        log("ID token为空，无法提取用户信息", "WARN")
        return user_info
    
    try:
        
        log(f"尝试从ID token解析用户信息，token长度: {len(id_token)}", "DEBUG")
        
       
        token_parts = id_token.split('.')
        if len(token_parts) != 3:
            log(f"ID token格式不正确，无法解析", "WARN")
            return user_info
        
      
        payload = token_parts[1]
      
        payload += '=' * ((4 - len(payload) % 4) % 4)
        
        try:
           
            decoded_payload = base64.b64decode(payload)
            token_data = json.loads(decoded_payload.decode('utf-8', errors='ignore'))
            
            
            log(f"成功解码token payload，包含字段: {list(token_data.keys())}", "DEBUG")
            
           
            if 'sub' in token_data:
                user_info['userId'] = token_data['sub']
                log(f"从ID token中提取用户ID: {user_info['userId']}", "INFO")
            
            
            for field in ['custom:referral_code', 'referral_code', 'referralCode']:
                if field in token_data and token_data[field]:
                    user_info['referralCode'] = token_data[field]
                    log(f"从ID token中提取推荐码: {user_info['referralCode']}", "INFO")
                    break
            
            if 'email' in token_data:
                user_info['email'] = token_data['email']
                log(f"从ID token中提取邮箱: {user_info['email']}", "INFO")
                
        except Exception as e:
            log(f"解析token payload失败: {str(e)}", "WARN")
            
    except Exception as e:
        log(f"解析ID token失败: {str(e)}", "WARN")
    
    return user_info


async def process_account(account_index: int, config: Dict) -> bool:
   
    global user_data, validation_status, price_data
    
    try:
       
        account = accounts[account_index]
        log(f"处理账户 {account_index + 1}/{len(accounts)}: {account.get('email', account.get('username', 'unknown'))}")
        
        
        token_manager = TokenManager(account, config)
        
        
        try:
            user_data = await get_user_data(token_manager, config)
            log(f"获取到用户数据: {user_data}")
        except Exception as e:
            log(f"获取用户数据失败: {str(e)}", "ERROR")
            user_data = {
                "username": account.get("email", account.get("username", "未知")),
                "userId": "未知",
                "referralCode": "未知",
                "stats": {
                    "valid": 0,
                    "invalid": 0,
                    "total": 0,
                    "lastCheck": ""
                }
            }
        
       
        await display_stats(
            user_data, 
            validation_status="⚠️ 无法获取用户数据，但将继续验证", 
            update_only=True,
            config=config,
            account_index=account_index,
            total_accounts=len(accounts),
            price_data=price_data
        )
    
       
        success = await run_validation_process(token_manager, config, account_index)
        return success
        
    except Exception as e:
        log(f"处理账户时出错: {str(e)}", "ERROR")
        return False


async def main():
    
    global accounts, current_config, start_time, user_data, validation_status, price_data
    
    try:
       
        current_config = load_config()
        if not validate_config():
            log("配置验证失败，请检查config.json", "ERROR")
            return
        
        log("Configuration loaded successfully from config.json", "INFO")
        
     
        try:
            from accounts import accounts
            if not accounts or len(accounts) == 0:
                log("没有找到账户，请检查accounts.py", "ERROR")
                return
            log("Accounts loaded successfully from accounts.py", "INFO")
        except ImportError:
           
            try:
                accounts = []
                tokens_data = get_tokens()
                for username, token_info in tokens_data.items():
                    accounts.append({
                        "email": username,
                        "username": username,
                        "tokens": token_info
                    })
                if accounts:
                    log(f"从tokens.json加载了 {len(accounts)} 个账户", "INFO")
                else:
                    log("没有找到账户，请检查tokens.json或创建accounts.py", "ERROR")
                    return
            except Exception as e:
                log(f"加载账户失败: {str(e)}", "ERROR")
                return
        
       
        log("🚀 启动 Stork Oracle Auto Bot 🚀", "INFO")
        
       
        start_time = time.time()
        
      
        progress_task = asyncio.create_task(update_progress())
        
        backoff_time = 5 
        max_backoff = 3600  
        
        try:
            while True:
                try:
                   
                    start_time = time.time()
                    log("重置计时器，开始新一轮验证", "INFO")
                    
                  
                    for account_index in range(len(accounts)):
                        log(f"开始处理账户 {account_index + 1}/{len(accounts)}")
                        success = await process_account(account_index, current_config)
                        
                        if success:
                           
                            backoff_time = 5
                        else:
                          
                            log(f"等待 {backoff_time} 秒后重试...", "WARN")
                            await asyncio.sleep(backoff_time)
                            
                            backoff_time = min(backoff_time * 2, max_backoff)
                        
                      
                        if account_index < len(accounts) - 1:
                            await asyncio.sleep(10)
                    
                   
                    start_time = time.time()
                    interval = current_config['stork']['intervalSeconds'] + random.randint(-30, 30)
                    log(f"所有账户处理完毕，等待 {interval} 秒后重新开始...", "INFO")
                    validation_status = f"✅ 所有账户处理完毕，等待 {interval} 秒后重新开始..."
                    await asyncio.sleep(interval)
                    
                except KeyboardInterrupt:
                    log("程序被用户停止", "INFO")
                    break
                except Exception as e:
                    log(f"意外错误: {str(e)}", "ERROR")
                    await asyncio.sleep(60)
        finally:
            progress_task.cancel()
            
    except Exception as e:
        log(f"主程序错误: {str(e)}", "ERROR")
        logger.error(f"主程序错误: {str(e)}")
       
        await asyncio.sleep(60)
        await main()


if __name__ == "__main__":
    asyncio.run(main())