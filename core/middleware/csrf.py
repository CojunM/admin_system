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

# ========== 新增：从请求中读取CSRF Token ==========
def _get_csrf_token_from_request(request):
    """
    从请求中读取CSRF Token，优先级：
    1. 请求头 X-CSRF-Token（推荐）
    2. POST表单中的 csrf_token 字段
    3. URL参数中的 csrf_token
    """
    # 1. 从请求头读取（前端主流方式）
    logger.info(f"[CSRF] 后端收到的所有请求头：{dict(request.headers)}")
    token = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")
    if token:
        return token.strip()
    
    # 2. 从POST表单读取
    if request.method == "POST" and hasattr(request, "form"):
        token = request.form.get("csrf_token")
        if token:
            return token.strip()
    
    # 3. 从URL参数读取（不推荐，仅兜底）
    if hasattr(request, "args"):
        token = request.args.get("csrf_token")
        if token:
            return token.strip()
    
    return None

def csrf_middleware(request, response):
    """CSRF防护中间件：验证Token，非GET请求必须携带"""
    # ========== 关键修改：给request添加csrf_token属性 ==========
    request.csrf_token = _get_csrf_token_from_request(request)
    
    # 清理过期Token
    _clean_expired_tokens()

    # 白名单：GET/OPTIONS请求不验证CSRF，生成Token并写入Cookie
    if request.method in ["GET", "OPTIONS"]:
        # 没有Token则生成并设置
        current_token = request.csrf_token
        if not current_token or current_token not in _csrf_tokens:
            new_token = _generate_csrf_token()
            logger.debug(f"[CSRF] Generate new token for {request.client_addr}: {new_token[:10]}...")
            _csrf_tokens[new_token] = (time.time(), request.client_addr)
            # 设置Cookie：确保跨域可读取（httpOnly=False）、路径正确
            response.set_cookie(
                "X-CSRF-Token", 
                new_token, 
                max_age=86400,
                path="/",  # 确保所有路径都能访问Cookie
                httponly=False,  # 允许前端JS读取
                samesite="Lax"  # 兼容跨域请求（生产环境可设为Strict）
            )
        return None

    # 非GET请求验证Token
    request_token = request.csrf_token
    if not request_token or request_token not in _csrf_tokens:
        logger.warning(f"[CSRF] Invalid token from {request.client_addr}, path: {request.path}, token: {request_token[:10] if request_token else 'None'}")
        # 返回403前重新生成Token（避免前端一直用无效Token）
        new_token = _generate_csrf_token()
        _csrf_tokens[new_token] = (time.time(), request.client_addr)
        response.set_cookie(
            "X-CSRF-Token", 
            new_token, 
            max_age=86400,
            path="/",
            httponly=False,
            samesite="Lax"
        )
        return response.json({"code": 403, "msg": "CSRF token invalid or missing"}, 403)

    # 验证Token归属（可选：注释掉则不校验IP）
    # token_ct, token_addr = _csrf_tokens[request_token]
    # if token_addr != request.client_addr:
    #     logger.warning(f"[CSRF] Token mismatch from {request.client_addr} (expected {token_addr})")
    #     return response.json({"code": 403, "msg": "CSRF token mismatch"}, 403)

    # 刷新Token过期时间
    _csrf_tokens[request_token] = (time.time(), request.client_addr)
    logger.debug(f"[CSRF] Token validated for {request.client_addr}, path: {request.path}")
    return None