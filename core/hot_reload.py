#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import time
import importlib
from threading import Thread
from config.settings import HOT_RELOAD_INTERVAL, HOT_RELOAD_DIRS
from utils.logger import logger

# 记录文件最后修改时间 {文件路径: 最后修改时间}
_file_mtimes = {}
# 记录已加载的模块 {模块名: 模块对象}
_loaded_modules = {}

def _get_module_path(module):
    """获取模块的文件路径"""
    if hasattr(module, "__file__") and module.__file__:
        return os.path.abspath(module.__file__)
    return None

def _scan_modules(dirs):
    """扫描指定目录下的所有Python模块"""
    modules = []
    for dir_path in dirs:
        if not os.path.isdir(dir_path):
            continue
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".py") and file != "__init__.py":
                    # 转换为模块名（如：apps/user/views.py -> apps.user.views）
                    rel_path = os.path.relpath(root, sys.path[0])
                    module_name = rel_path.replace(os.sep, ".") + "." + file[:-3]
                    module_path = os.path.abspath(os.path.join(root, file))
                    modules.append((module_name, module_path))
            # 处理__init__.py
            init_file = os.path.join(root, "__init__.py")
            if os.path.exists(init_file):
                rel_path = os.path.relpath(root, sys.path[0])
                module_name = rel_path.replace(os.sep, ".") if rel_path != "." else root.split(os.sep)[-1]
                modules.append((module_name, os.path.abspath(init_file)))
    return modules

def _check_file_changes():
    """检查文件是否有修改"""
    changed_modules = []
    modules = _scan_modules(HOT_RELOAD_DIRS)
    
    for module_name, module_path in modules:
        try:
            mtime = os.path.getmtime(module_path)
            # 新文件或已修改文件
            if module_path not in _file_mtimes or mtime > _file_mtimes[module_path]:
                _file_mtimes[module_path] = mtime
                changed_modules.append((module_name, module_path))
        except Exception as e:
            logger.warning(f"[HotReload] Check file {module_path} failed: {str(e)}")
            continue
    return changed_modules

def _reload_module(module_name):
    """重新加载模块"""
    try:
        if module_name in sys.modules:
            # 重新加载已存在的模块
            module = importlib.reload(sys.modules[module_name])
            logger.info(f"[HotReload] Reload module {module_name} success")
        else:
            # 导入新模块
            module = importlib.import_module(module_name)
            logger.info(f"[HotReload] Import module {module_name} success")
        _loaded_modules[module_name] = module
        return True
    except Exception as e:
        logger.error(f"[HotReload] Reload module {module_name} failed: {str(e)}", exc_info=True)
        return False

def hot_reload_monitor():
    """热更新监控线程：循环检查文件变化并重新加载模块"""
    logger.info(f"[HotReload] Start monitor, interval: {HOT_RELOAD_INTERVAL}s, dirs: {HOT_RELOAD_DIRS}")
    while True:
        try:
            changed_modules = _check_file_changes()
            if changed_modules:
                for module_name, _ in changed_modules:
                    _reload_module(module_name)
            time.sleep(HOT_RELOAD_INTERVAL)
        except Exception as e:
            logger.error(f"[HotReload] Monitor error: {str(e)}", exc_info=True)
            time.sleep(HOT_RELOAD_INTERVAL)

def start_hot_reload_monitor():
    """启动热更新监控（后台线程）"""
    # 先扫描并加载所有初始模块
    initial_modules = _scan_modules(HOT_RELOAD_DIRS)
    for module_name, _ in initial_modules:
        _reload_module(module_name)
    # 启动监控线程
    t = Thread(target=hot_reload_monitor, daemon=True)
    t.start()
    return t