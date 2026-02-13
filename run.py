#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import DEBUG, HOST, PORT, HOT_RELOAD
from core.server import run_http_server
from core.hot_reload import start_hot_reload_monitor
from utils.logger import logger

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

def main():
    """项目主启动函数"""
    logger.info("[System] Starting admin system...")
    logger.info(f"[System] Debug mode: {DEBUG}, Host: {HOST}:{PORT}")
    
    
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