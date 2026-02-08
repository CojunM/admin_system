#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
权限认证中间件：替换jwt.decode为自定义jwt_decode
"""
import time
# from core.response import Response
# 导入自定义JWT工具（替换原有jwt库）
from utils.jwt_tool import jwt_decode
from config.settings import SECRET_KEY

def auth_middleware(request, response):
    """
    权限认证中间件：从Header获取Token，解析验证后挂载用户信息到request.user
    """
    # 1. 接口白名单：无需登录的接口（保留原有配置）
    white_list = ["/api/user/login", "/static/*", "/", "/pages/login.html"]
    if request.path in white_list or (request.path.startswith("/static/")):
        return None
    
    # 2. 从Request Header获取Token（保留原有逻辑）
    token = None
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    if not token:
        return response.json({"code": 401, "msg": "未登录，请先登录"}, 401)
    
    # 3. 解析验证Token：核心替换jwt.decode → jwt_decode（自定义方法）
    try:
        # 原有代码：payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        # 新代码：使用自定义jwt_decode，参数完全一致
        payload = jwt_decode(token, SECRET_KEY, algorithm="HS256", verify=True)
    except ValueError as e:
        # 捕获自定义JWT的验证异常（签名错误/过期/格式错误）
        logger.error(f"[Auth] Token verify failed: {str(e)}")
        return response.json({"code": 401, "msg": str(e) or "登录状态无效，请重新登录"}, 401)
    
    # 4. 挂载用户信息到request.user（保留原有逻辑，可按需扩展字段）
    request.user = {
        "id": payload.get("user_id"),
        "username": payload.get("username"),
        "is_admin": False  # 可从数据库查询角色补充，原有逻辑不变
    }
    # 可选：补充管理员标识（原有逻辑不变）
    from apps.role.models import Role
    from apps.user.models import User
    user = User.get(id=payload.get("user_id"))
    if user:
        role = Role.get(id=user.role_id)
        request.user["is_admin"] = role.is_admin == 1 if role else False
    
    return None

# 其他中间件（限流/CSRF/脱敏等）：完全保留，无需修改