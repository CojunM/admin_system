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
# 数据库配置（PostgreSQL）
DB_CONFIG = {
    "host":  os.getenv("PG_HOST", "127.0.0.1"),
    "port": int(os.getenv("PG_PORT", 5432)),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD", "postgres"),
    "database": os.getenv("PG_DB", "admin_system"),
    "charset": os.getenv("PG_CHARSET", "utf8"),
    "pool_enable":True,         # 测试阶段关闭连接池
    # 数据库连接池-最小连接数，优先读系统环境变量 POOL_MIN_CONN，
    "POOL_MIN_CONN":  int(os.getenv("POOL_MIN_CONN", 2)),
    # 数据库连接池-最大连接数，优先读系统环境变量 POOL_MAX_CONN，默认10
    "POOL_MAX_CONN":  int(os.getenv("POOL_MAX_CONN", 10)),
    "POOL_IDLE_TIMEOUT":  int(os.getenv("POOL_IDLE_TIMEOUT", 300))  # 空闲连接超时时间

}
# 安全配置
# 脱敏配置（独立管理，无需改代码）
DESENSITIZE_CONFIG = {
    # 跳过脱敏的路径（支持模糊匹配）
    "exclude_paths": ["/api/user/login", "/api/user/info", "/api/user/refresh"],
    # 脱敏规则（新增字段只需加这里）
    "rules": {
        "phone": {
            "pattern": r"^1[3-9]\d{9}$",  # 严格手机号正则
            "handler": lambda x: f"{x[:3]}****{x[-4:]}"
        },
        "email": {
            "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            "handler": lambda x: f"{x[:2]}****@{x.split('@', 1)[1]}"
        },
        "id_card": {
            "pattern": r"^\d{18}$",
            "handler": lambda x: f"{x[:6]}********{x[-4:]}"
        },
        "bank_card": {
            "pattern": r"^\d{16,19}$",
            "handler": lambda x: f"{x[:4]}********{x[-4:]}"
        }
    },
    # 性能控制
    "max_body_size": 1024 * 1024,  # 1MB以上跳过
    "enable": True  # 全局开关（测试环境可关闭）
}
CSRF_SECRET = os.getenv("CSRF_SECRET", "default_csrf_secret")
# 基础限流阈值（每分钟最大请求数）
RATE_LIMIT_MAX = int(os.getenv("RATE_LIMIT_MAX", 100))   # 从默认的10/20调高，避免正常请求被限
# 限流白名单（核心接口豁免）
RATE_LIMIT_WHITELIST = [
    "/api/user/info",       # 用户信息接口
    "/api/user/login",      # 登录接口
    "/api/dashboard/stats", # 仪表盘统计
    "/api/dashboard/role-distribution"  # 角色分布
]
# 限流时间窗口（秒）
RATE_LIMIT_WINDOW = 60
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