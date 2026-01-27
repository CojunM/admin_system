'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:29:19
LastEditors: Cojun
LastEditTime: 2026-01-25 19:29:36
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
from collections import defaultdict
from config.settings import THROTTLE_TIMEOUT, DEBOUNCE_TIMEOUT
from utils.logger import logger

# 节流存储 {client_addr+path: last_request_time}
_throttle_storage = dict()
# 防抖存储 {client_addr+path: (last_request_time, timer)}
_debounce_storage = dict()
# 防抖定时器映射（用线程模拟，原生Python无定时器，简化实现）
_debounce_timers = dict()

def throttle_middleware(request, response):
    """请求节流中间件：指定时间内同一接口仅允许一次请求"""
    # 白名单：忽略静态文件和OPTIONS
    if request.path.startswith("/static/") or request.method == "OPTIONS":
        return None
    
    key = f"{request.client_addr[0]}_{request.path}_{request.method}"
    now = time.time()
    last_time = _throttle_storage.get(key, 0)

    if now - last_time < THROTTLE_TIMEOUT:
        logger.debug(f"[Throttle] Request blocked from {request.client_addr}, path: {request.path}")
        return response.json({
            "code": 429,
            "msg": f"Request too frequent, please wait {THROTTLE_TIMEOUT} seconds"
        }, 429)

    # 更新最后请求时间
    _throttle_storage[key] = now
    # 清理过期记录（超过10倍超时时间）
    for k in list(_throttle_storage.keys()):
        if now - _throttle_storage[k] > THROTTLE_TIMEOUT * 10:
            del _throttle_storage[k]
    return None

def debounce_middleware(request, response):
    """请求防抖中间件：指定时间内多次请求仅执行最后一次（简化实现，同步版）"""
    # 白名单：仅对POST/PUT/DELETE生效，忽略静态文件
    if request.method not in ["POST", "PUT", "DELETE"] or request.path.startswith("/static/"):
        return None
    
    key = f"{request.client_addr[0]}_{request.path}_{request.method}"
    now = time.time()
    debounce_info = _debounce_storage.get(key, (0, None))

    # 如果在防抖时间内，直接返回成功（实际后续执行，简化版忽略执行）
    if now - debounce_info[0] < DEBOUNCE_TIMEOUT:
        logger.debug(f"[Debounce] Request debounced from {request.client_addr}, path: {request.path}")
        return response.json({"code": 200, "msg": "Request accepted, processing..."})

    # 更新防抖时间
    _debounce_storage[key] = (now, None)
    # 清理过期记录
    for k in list(_debounce_storage.keys()):
        if now - _debounce_storage[k][0] > DEBOUNCE_TIMEOUT * 10:
            del _debounce_storage[k]
    return None