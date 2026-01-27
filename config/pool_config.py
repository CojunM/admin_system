'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:17:26
LastEditors: Cojun
LastEditTime: 2026-01-25 19:18:03
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from config.settings import (
    PG_HOST, PG_PORT, PG_USER, PG_PASSWORD, PG_DB, PG_CHARSET,
    POOL_MIN_CONN, POOL_MAX_CONN, POOL_IDLE_TIMEOUT, POOL_RECYCLE
)

# 连接池核心配置
POOL_CONFIG = {
    "minconn": int(os.getenv("POOL_MIN_CONN", 2)),
    "maxconn": int(os.getenv("POOL_MAX_CONN", 10)),
    "idle_timeout": int(os.getenv("POOL_IDLE_TIMEOUT", 300)),
    "recycle": int(os.getenv("POOL_RECYCLE", 3600)),
    "connect_kwargs": {
        "host": PG_HOST,
        "port": PG_PORT,
        "user": PG_USER,
        "password": PG_PASSWORD,
        "dbname": PG_DB,
        "options": f"-c client_encoding={PG_CHARSET}"
    }
}

# 连接池全局实例标识
POOL_INSTANCE_NAME = "pg_default_pool"