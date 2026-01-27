'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:30:05
LastEditors: Cojun
LastEditTime: 2026-01-25 22:17:32
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# import jwt
import time
from config.settings import SECRET_KEY
from utils.logger import logger
from apps.user.models import User, Role

# JWT配置
JWT_EXPIRE = 86400  # 24小时
# 白名单：无需认证的接口
WHITE_LIST = [
    "/", "/api/user/login", "/api/user/refresh",
    "/static/*", "/favicon.ico"
]

def _is_white_list(path):
    """判断是否在白名单"""
    for white in WHITE_LIST:
        if white.endswith("*"):
            prefix = white[:-1]
            if path.startswith(prefix):
                return True
        elif path == white:
            return True
    return False

def _verify_jwt(token):
    """验证JWT Token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        # 检查过期时间
        if "exp" not in payload or payload["exp"] < time.time():
            return None
        # 返回用户ID
        return payload.get("user_id")
    except Exception as e:
        logger.warning(f"[Auth] JWT verify failed: {str(e)}")
        return None

def auth_middleware(request, response):
    """权限认证中间件：JWT验证，白名单除外"""
    # 白名单跳过认证
    if _is_white_list(request.path):
        return None

    # 获取Token（从Header: Authorization，格式：Bearer <token>）
    auth_header = request.headers.get("Authorization", "")
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning(f"[Auth] No token from {request.client_addr}, path: {request.path}")
        return response.json({"code": 401, "msg": "Please login first"}, 401)
    
    token = auth_header[7:]
    user_id = _verify_jwt(token)
    if not user_id:
        logger.warning(f"[Auth] Invalid token from {request.client_addr}, path: {request.path}")
        return response.json({"code": 401, "msg": "Token invalid or expired"}, 401)

    # 查询用户信息（包含角色）
    user = User.get(id=user_id)
    if not user or user.status == 0:
        logger.warning(f"[Auth] User {user_id} not found or disabled")
        return response.json({"code": 401, "msg": "User not found or disabled"}, 401)

    # 存储用户信息到request
    request.user = user.to_dict()
    # 超级管理员跳过权限检查
    role = Role.get(id=user.role_id)
    if role.is_admin == 1:
        request.user["is_admin"] = True
        return None

    # 细粒度权限检查（接口路径匹配权限标识）
    # 权限映射：/api/user/add -> user:add
    path_parts = request.path.lstrip("/").split("/")
    if len(path_parts) >= 3 and path_parts[0] == "api":
        perm_code = f"{path_parts[1]}:{path_parts[2]}"
        # 检查用户角色是否拥有该权限（简化版：实际需查询role_permissions表）
        from apps.permission.models import RolePermission, Permission
        role_perms = RolePermission.filter(role_id=user.role_id)
        perm_codes = [Permission.get(id=p.permission_id).code for p in role_perms]
        if perm_code not in perm_codes:
            logger.warning(f"[Auth] User {user_id} no permission {perm_code} for {request.path}")
            return response.json({"code": 403, "msg": "No permission to access this resource"}, 403)

    request.user["is_admin"] = False
    return None