'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:27:25
LastEditors: Cojun
LastEditTime: 2026-01-25 19:27:38
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import uuid
import time
from config.settings import CSRF_SECRET
from utils.logger import logger

# 存储CSRF Token {token: (create_time, client_addr)}
_csrf_tokens = {}
# 清理过期Token的时间间隔（秒）
_CLEAN_INTERVAL = 3600
_last_clean_time = time.time()

def _generate_csrf_token():
    """生成CSRF Token"""
    return str(uuid.uuid4()) + "_" + CSRF_SECRET[:16]

def _clean_expired_tokens():
    """清理过期Token（有效期24小时）"""
    global _last_clean_time
    if time.time() - _last_clean_time < _CLEAN_INTERVAL:
        return
    now = time.time()
    expired = [t for t, (ct, _) in _csrf_tokens.items() if now - ct > 86400]
    for t in expired:
        del _csrf_tokens[t]
    _last_clean_time = time.time()
    logger.debug(f"[CSRF] Clean {len(expired)} expired tokens, remaining: {len(_csrf_tokens)}")

def csrf_middleware(request, response):
    """CSRF防护中间件：验证Token，非GET请求必须携带"""
    # 清理过期Token
    _clean_expired_tokens()

    # 白名单：GET/OPTIONS请求不验证CSRF
    if request.method in ["GET", "OPTIONS"]:
        # 没有Token则生成并设置
        if not request.csrf_token or request.csrf_token not in _csrf_tokens:
            new_token = _generate_csrf_token()
            _csrf_tokens[new_token] = (time.time(), request.client_addr)
            response.set_cookie("X-CSRF-Token", new_token, max_age=86400)
        return None

    # 非GET请求验证Token
    if not request.csrf_token or request.csrf_token not in _csrf_tokens:
        logger.warning(f"[CSRF] Invalid token from {request.client_addr}, path: {request.path}")
        return response.json({"code": 403, "msg": "CSRF token invalid or missing"}, 403)

    # 验证Token归属（可选：严格验证客户端地址）
    token_ct, token_addr = _csrf_tokens[request.csrf_token]
    # if token_addr != request.client_addr:
    #     logger.warning(f"[CSRF] Token mismatch from {request.client_addr}, path: {request.path}")
    #     return response.json({"code": 403, "msg": "CSRF token mismatch"}, 403)

    # 刷新Token过期时间
    _csrf_tokens[request.csrf_token] = (time.time(), request.client_addr)
    return None