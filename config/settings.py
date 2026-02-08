'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:13:41
LastEditors: Cojun
LastEditTime: 2026-01-25 22:45:17
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os


# 加载.env环境变量
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')



# 服务配置
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8080))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
SECRET_KEY = os.getenv("SECRET_KEY", "default_secret_key")
HOT_RELOAD = os.getenv("HOT_RELOAD", "True").lower() == "true"
HOT_RELOAD_INTERVAL = int(os.getenv("HOT_RELOAD_INTERVAL", 2))
HOT_RELOAD_DIRS = [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps")]

# PostgreSQL基础配置
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", 5432))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "postgres")
PG_DB = os.getenv("PG_DB", "admin_system")
PG_CHARSET = os.getenv("PG_CHARSET", "utf8")
# 数据库连接池-最小连接数，优先读系统环境变量 POOL_MIN_CONN，默认2
POOL_MIN_CONN: int = int(os.getenv("POOL_MIN_CONN", 2))
# 数据库连接池-最大连接数，优先读系统环境变量 POOL_MAX_CONN，默认10
POOL_MAX_CONN: int = int(os.getenv("POOL_MAX_CONN", 10))
POOL_IDLE_TIMEOUT: int = int(os.getenv("POOL_IDLE_TIMEOUT", 300))  # 空闲连接超时时间
# 安全配置
CSRF_SECRET = os.getenv("CSRF_SECRET", "default_csrf_secret")
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", 100))  # 每分钟请求数
PASSWORD_ROUNDS = int(os.getenv("PASSWORD_ROUNDS", 12))  # bcrypt轮数
DESENSITIZE_FIELDS = os.getenv("DESENSITIZE_FIELDS", "phone,email").split(",")
THROTTLE_TIMEOUT = 1  # 节流超时（秒）
DEBOUNCE_TIMEOUT = 0.5  # 防抖超时（秒）

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_FILE = os.getenv("LOG_FILE", "admin_system.log")
LOG_MAX_SIZE = int(os.getenv("LOG_MAX_SIZE", 10*1024*1024))  # 10MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

# 前端配置
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
TEMPLATE_DIR = os.path.join(STATIC_DIR, "pages")