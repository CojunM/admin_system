#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.settings import DEBUG, HOST, PORT, HOT_RELOAD
from core.server import run_http_server
from core.hot_reload import start_hot_reload_monitor
from utils.logger import logger

def main():
    """项目主启动函数"""
     
    # 启动热更新监控（仅开发环境）
    # if HOT_RELOAD and DEBUG:
        # start_hot_reload_monitor()
    logger.info(f"[System] Starting server on {HOST}:{PORT}, DEBUG={DEBUG}")
    logger.info(f"[System] Hot reload: {HOT_RELOAD}")
 
    # 启动原生HTTP服务
    run_http_server(HOST, PORT)
if __name__ == "__main__":
    print("asd")
    main()
   