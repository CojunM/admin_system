#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
# import jwt
from core.router import post, get, put, delete
from config.settings import SECRET_KEY
from utils.crypto import encrypt_pwd, verify_pwd
from utils.logger import logger
from apps.user.models import User
from apps.role.models import Role

# JWT过期时间（24小时）
JWT_EXPIRE = 86400

@post("/api/user/login")
def user_login(request):
    """用户登录接口"""
    username = request.body.get("username")
    password = request.body.get("password")
    if not username or not password:
        return 400, {"msg": "用户名和密码不能为空"}
    
    # 查询用户
    user = User.get(username=username)
    if not user:
        return 401, {"msg": "用户名或密码错误"}
    if user.status == 0:
        return 401, {"msg": "用户已被禁用"}
    
    # 验证密码
    if not verify_pwd(password, user.password):
        logger.warning(f"[User] Login failed, wrong password for {username}")
        return 401, {"msg": "用户名或密码错误"}
    
    # 更新最后登录时间
    user.last_login_time = time.strftime("%Y-%m-%d %H:%M:%S")
    user.save()
    
    # 生成JWT Token
    payload = {
        "user_id": user.id,
        "username": user.username,
        "exp": time.time() + JWT_EXPIRE
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
    
    # 返回用户信息（脱敏）
    user_info = user.to_dict(desensitize_fields=["phone", "email"])
    del user_info["password"]
    user_info["role"] = Role.get(id=user.role_id).name
    
    logger.info(f"[User] {username} login success from {request.client_addr}")
    return {
        "token": token,
        "user": user_info
    }

@get("/api/user/info")
def user_info(request):
    """获取当前用户信息"""
    user_id = request.user.get("id")
    user = User.get(id=user_id)
    role = Role.get(id=user.role_id)
    user_info = user.to_dict(desensitize_fields=["phone", "email"])
    del user_info["password"]
    user_info["role"] = role.name
    user_info["role_code"] = role.code
    user_info["is_admin"] = request.user.get("is_admin", False)
    return user_info

@post("/api/user/add")
def user_add(request):
    """添加用户"""
    required = ["username", "password", "nickname", "role_id"]
    for field in required:
        if not request.body.get(field):
            return 400, {"msg": f"{field}不能为空"}
    
    # 检查用户是否存在
    if User.get(username=request.body.get("username")):
        return 400, {"msg": "用户名已存在"}
    
    # 加密密码
    pwd = encrypt_pwd(request.body.get("password"))
    
    # 创建用户
    user = User(
        username=request.body.get("username"),
        password=pwd,
        nickname=request.body.get("nickname"),
        email=request.body.get("email", ""),
        phone=request.body.get("phone", ""),
        role_id=request.body.get("role_id"),
        status=request.body.get("status", 1)
    )
    user.save()
    logger.info(f"[User] Add user {user.username} by {request.user.get('username')}")
    return user.to_dict(desensitize_fields=["phone", "email"])

@get("/api/user/list")
def user_list(request):
    """用户列表（分页）"""
    page = int(request.query.get("page", 1))
    page_size = int(request.query.get("page_size", 10))
    keyword = request.query.get("keyword", "")
    
    # 条件查询
    if keyword:
        # 简化版：实际需用模糊查询，ORM扩展like即可
        users = User.filter(username__like=f"%{keyword}%")
        total = len(users)
        paginated = {
            "list": [u.to_dict(desensitize_fields=["phone", "email"]) for u in users[(page-1)*page_size:page*page_size]],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    else:
        paginated = User.paginate(page=page, page_size=page_size)
        paginated["list"] = [u.to_dict(desensitize_fields=["phone", "email"]) for u in paginated["list"]]
    
    # 补充角色名称
    for user in paginated["list"]:
        user["role_name"] = Role.get(id=user["role_id"]).name
    return paginated

@put("/api/user/edit/<user_id>")
def user_edit(request, user_id):
    """编辑用户"""
    user = User.get(id=user_id)
    if not user:
        return 404, {"msg": "用户不存在"}
    
    # 更新字段
    if "nickname" in request.body:
        user.nickname = request.body.get("nickname")
    if "email" in request.body:
        user.email = request.body.get("email", "")
    if "phone" in request.body:
        user.phone = request.body.get("phone", "")
    if "avatar" in request.body:
        user.avatar = request.body.get("avatar")
    if "role_id" in request.body:
        user.role_id = request.body.get("role_id")
    if "status" in request.body:
        user.status = request.body.get("status")
    # 密码更新
    if "password" in request.body and request.body.get("password"):
        user.password = encrypt_pwd(request.body.get("password"))
    
    user.save()
    logger.info(f"[User] Edit user {user_id} by {request.user.get('username')}")
    return user.to_dict(desensitize_fields=["phone", "email"])

@delete("/api/user/delete/<user_id>")
def user_delete(request, user_id):
    """删除用户"""
    user = User.get(id=user_id)
    if not user:
        return 404, {"msg": "用户不存在"}
    # 禁止删除超级管理员
    role = Role.get(id=user.role_id)
    if role.is_admin == 1:
        return 403, {"msg": "禁止删除超级管理员"}
    user.delete()
    logger.info(f"[User] Delete user {user_id} by {request.user.get('username')}")
    return {"msg": "删除成功"}

@post("/api/user/change-pwd")
def change_pwd(request):
    """修改密码"""
    old_pwd = request.body.get("old_pwd")
    new_pwd = request.body.get("new_pwd")
    if not old_pwd or not new_pwd:
        return 400, {"msg": "原密码和新密码不能为空"}
    
    user = User.get(id=request.user.get("id"))
    if not verify_pwd(old_pwd, user.password):
        return 400, {"msg": "原密码错误"}
    
    user.password = encrypt_pwd(new_pwd)
    user.save()
    logger.info(f"[User] Change password for {user.username}")
    return {"msg": "密码修改成功"}