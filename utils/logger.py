'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:47:36
LastEditors: Cojun
LastEditTime: 2026-01-25 23:51:41
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import logging
from logging.handlers import RotatingFileHandler
from config.settings import LOG_LEVEL, LOG_DIR, LOG_FILE, LOG_MAX_SIZE, LOG_BACKUP_COUNT

# 日志级别映射
LOG_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

def setup_logger():
    """初始化全局日志"""
    # 创建日志目录
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    log_file = os.path.join(LOG_DIR, LOG_FILE)

    # 配置日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 创建日志器
    logger = logging.getLogger("admin-system")
    logger.setLevel(LOG_LEVEL_MAP.get(LOG_LEVEL, logging.INFO))
    logger.handlers.clear()  # 清除默认处理器

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器（按大小切割）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=LOG_MAX_SIZE,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# 全局日志实例
logger = setup_logger()