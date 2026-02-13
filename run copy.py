#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import DEBUG, HOST, PORT, HOT_RELOAD
from core.server import run_http_server
from core.hot_reload import start_hot_reload_monitor
from utils.logger import logger

def _check_database_connection():
    """检查数据库连接"""
    try:
        from core.orm.pool import DatabasePool
        if DatabasePool.is_available():
            logger.info("[System] Database connection OK")
            return True
        else:
            logger.error("[System] Database connection failed")
            return False
    except Exception as e:
        logger.error(f"[System] Database connection check error: {str(e)}")
        return False

def _initialize_database_pool():
    """初始化数据库连接池"""
    try:
        from core.orm.pool import DatabasePool
        DatabasePool.init_pool()
        logger.info("[System] Database pool initialized successfully")
        return True
    except Exception as e:
        logger.error(f"[System] Database pool initialization failed: {str(e)}")
        return False

def _load_all_routes():
    """自动加载所有路由：扫描apps目录下所有views模块"""
    import importlib
    import apps
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))  # 项目根目录
    apps_dir = os.path.join(current_dir,  "apps")  # apps目录
    apps_dir = os.path.abspath(apps_dir)  # 确保是绝对路径
    
    loaded_modules = []
    failed_modules = []
    
    for app_dir in os.listdir(apps_dir):
        app_path = os.path.join(apps_dir, app_dir)
        if os.path.isdir(app_path):
            views_module_name = f"apps.{app_dir}.views"
            try:
                # 动态导入模块以触发路由装饰器执行
                importlib.import_module(views_module_name)
                logger.info(f"[Server] Loaded routes from {views_module_name}")
                loaded_modules.append(views_module_name)
            except ImportError as e:
                logger.error(f"[Server] Failed to load {views_module_name}: {str(e)}")
                failed_modules.append(views_module_name)
            except Exception as e:
                logger.error(f"[Server] Error in loading {views_module_name}: {str(e)}")
                failed_modules.append(views_module_name)
    
    logger.info(f"[Server] Route loading completed. Success: {len(loaded_modules)}, Failed: {len(failed_modules)}")
    if failed_modules:
        logger.warning(f"[Server] Failed modules: {failed_modules}")

def _test_basic_components():
    """测试基础组件功能"""
    logger.info("[System] Testing basic components...")
    
    # 测试JWT工具
    try:
        from utils.jwt_tool import jwt_encode, jwt_decode
        test_payload = {"user_id": 1, "username": "test"}
        token = jwt_encode(test_payload, "test_secret")
        decoded = jwt_decode(token, "test_secret")
        assert decoded["user_id"] == 1
        logger.info("[System] JWT tools working correctly")
    except Exception as e:
        logger.error(f"[System] JWT tools error: {str(e)}")
        return False
    
    # 测试密码加密
    try:
        from utils.crypto import encrypt_password, verify_password
        pwd = "123456"
        encrypted = encrypt_password(pwd)
        assert verify_password(pwd, encrypted)
        assert not verify_password("wrong", encrypted)
        logger.info("[System] Password encryption working correctly")
    except Exception as e:
        logger.error(f"[System] Password encryption error: {str(e)}")
        return False
    
    return True

def main():
    """项目主启动函数"""
    logger.info("[System] Starting admin system...")
    logger.info(f"[System] Debug mode: {DEBUG}, Host: {HOST}:{PORT}")
    
    # 组件健康检查
    if not _test_basic_components():
        logger.error("[System] Basic component test failed, exiting...")
        sys.exit(1)
    
    # 初始化数据库连接池
    if not _initialize_database_pool():
        logger.error("[System] Database initialization failed, exiting...")
        sys.exit(1)
    
    # 检查数据库连接
    if not _check_database_connection():
        logger.warning("[System] Database connection check failed, continuing anyway...")
    
    # 导入路由模块，确保装饰器被执行并注册路由
    _load_all_routes()
    
    # 启动热更新监控（仅开发环境）
    # if HOT_RELOAD and DEBUG:
        # start_hot_reload_monitor()
        # logger.info(f"[System] Hot reload: {HOT_RELOAD}")
      
    # 启动原生HTTP服务
    try:
        logger.info("[System] Starting HTTP server...")
        run_http_server(HOST, PORT)
    except Exception as e:
        logger.error(f"[System] Server startup failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("[System] Server stopped by user")
    except Exception as e:
        logger.error(f"[System] Unexpected error: {str(e)}")
        sys.exit(1)