#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目核心配置（移除dotenv，直接读取系统环境变量+默认值）
"""
import os
from typing import Optional

# ==================== 基础服务配置 ====================
# 服务端口，优先读系统环境变量 PORT，默认8000
PORT: int = int(os.getenv("PORT", 8000))
# 调试模式，优先读系统环境变量 DEBUG，默认True（开发环境）
DEBUG: bool = os.getenv("DEBUG", "True").lower() in ("true", "1", "on")
# 热更新开关，优先读系统环境变量 HOT_RELOAD，默认True（开发环境）
HOT_RELOAD: bool = os.getenv("HOT_RELOAD", "True").lower() in ("true", "1", "on")
# 服务主机，优先读系统环境变量 HOST，默认0.0.0.0（允许所有IP访问）
HOST: str = os.getenv("HOST", "0.0.0.0")

# ==================== 数据库配置（PostgreSQL） ====================
# 数据库主机，优先读系统环境变量 PG_HOST，默认localhost
PG_HOST: str = os.getenv("PG_HOST", "localhost")
# 数据库端口，优先读系统环境变量 PG_PORT，默认5432
PG_PORT: int = int(os.getenv("PG_PORT", 5432))
# 数据库用户名，优先读系统环境变量 PG_USER，默认postgres
PG_USER: str = os.getenv("PG_USER", "postgres")
# 数据库密码，优先读系统环境变量 PG_PASSWORD，默认123456
PG_PASSWORD: str = os.getenv("PG_PASSWORD", "postgres")
# 数据库名，优先读系统环境变量 PG_DB，默认admin_system
PG_DB: str = os.getenv("PG_DB", "admin_system")
# 数据库连接池-最小连接数，优先读系统环境变量 POOL_MIN_CONN，默认2
POOL_MIN_CONN: int = int(os.getenv("POOL_MIN_CONN", 2))
# 数据库连接池-最大连接数，优先读系统环境变量 POOL_MAX_CONN，默认10
POOL_MAX_CONN: int = int(os.getenv("POOL_MAX_CONN", 10))

# ==================== 安全配置 ====================
# JWT密钥，优先读系统环境变量 SECRET_KEY，默认设置开发环境密钥（生产环境务必修改为随机32位以上字符串）
SECRET_KEY: str = os.getenv(
    "SECRET_KEY", 
    "dev_abc1234567890_admin_system_xyz987654321_def"
)
# JWT过期时间（秒），优先读系统环境变量 JWT_EXPIRE_SECONDS，默认8小时（28800秒）
JWT_EXPIRE_SECONDS: int = int(os.getenv("JWT_EXPIRE_SECONDS", 8 * 3600))
# CSRF密钥，优先读系统环境变量 CSRF_SECRET，默认开发环境密钥（生产环境务必修改）
CSRF_SECRET: str = os.getenv(
    "CSRF_SECRET", 
    "csrf_dev_1234567890_abcxyz_admin_system_987654321"
)
# 接口限流-每分钟最大请求数，优先读系统环境变量 RATE_LIMIT_PER_MINUTE，默认60
RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", 60))

# ==================== 路径配置 ====================
# 项目根目录（自动计算，无需修改）
BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 静态资源目录（自动计算，无需修改）
STATIC_DIR: str = os.path.join(BASE_DIR, "static")
# 上传文件目录（自动计算，无需修改）
UPLOAD_DIR: str = os.path.join(STATIC_DIR, "uploads")

# 确保上传目录存在
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==================== 数据库连接URL（自动拼接，无需修改） ====================
DATABASE_URL: str = (
    f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
)