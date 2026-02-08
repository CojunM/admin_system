'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:36:07
LastEditors: Cojun
LastEditTime: 2026-01-25 19:36:43
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core import Model, IntField, StrField, BoolField, DateTimeField, ForeignKeyField
from apps.role.models import Role

class User(Model):
    __table_name__ = "users"
    id = IntField(primary_key=True, comment="用户ID")
    username = StrField(length=32, unique=True, nullable=False, comment="用户名")
    password = StrField(length=255, nullable=False, comment="加密密码")
    nickname = StrField(length=32, nullable=False, comment="昵称")
    email = StrField(length=64, default="", comment="邮箱")
    phone = StrField(length=11, default="", comment="手机号")
    avatar = StrField(length=255, default="/static/imgs/avatar-default.png", comment="头像")
    role_id = ForeignKeyField(to=Role, nullable=False, comment="角色ID")
    status = IntField(default=1, comment="状态 0-禁用 1-启用")
    last_login_time = DateTimeField(nullable=True, comment="最后登录时间")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")