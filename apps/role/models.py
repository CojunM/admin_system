'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:39:18
LastEditors: Cojun
LastEditTime: 2026-01-25 19:39:29
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core import Model, IntField, StrField, BoolField, DateTimeField

class Role(Model):
    __table_name__ = "roles"
    id = IntField(primary_key=True, comment="角色ID")
    name = StrField(length=32, unique=True, nullable=False, comment="角色名称")
    code = StrField(length=64, unique=True, nullable=False, comment="角色标识")
    desc = StrField(length=255, default="", comment="角色描述")
    is_admin = IntField(default=0, comment="是否超级管理员 0-否 1-是")
    sort = IntField(default=0, comment="排序")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")

class RolePermission(Model):
    __table_name__ = "role_permissions"
    id = IntField(primary_key=True, comment="关联ID")
    role_id = IntField(nullable=False, comment="角色ID")
    permission_id = IntField(nullable=False, comment="权限ID")