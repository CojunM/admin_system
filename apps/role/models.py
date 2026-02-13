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
from core.peewee_orm_single1_1 import   IntegerField, StringField,  DateTimeField
from apps import BaseModel

class Role(BaseModel):
    __table_name__ = "roles"
    id =  IntegerField(primary_key=True, comment="角色ID")
    name = StringField(max_length=32, unique=True, nullable=False, comment="角色名称")
    code = StringField(max_length=64, unique=True, nullable=False, comment="角色标识")
    desc = StringField(max_length=255, default="", comment="角色描述")
    is_admin =  IntegerField(default=0, comment="是否超级管理员 0-否 1-是")
    sort =  IntegerField(default=0, comment="排序")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")

class RolePermission(BaseModel):
    __table_name__ = "role_permissions"
    id =  IntegerField(primary_key=True, comment="关联ID")
    role_id =  IntegerField(nullable=False, comment="角色ID")
    permission_id =  IntegerField(nullable=False, comment="权限ID")