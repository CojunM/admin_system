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
# from core import Model
from core.peewee_orm_single1_1 import  IntegerField, StringField,  DateTimeField, ForeignKeyField
from apps.role.models import Role
from apps import BaseModel 

class User(BaseModel):
    
    id =  IntegerField(primary_key=True, comment="用户ID")
    username = StringField(max_length=32, unique=True, nullable=False, comment="用户名")
    password = StringField(max_length=255, nullable=False, comment="加密密码")
    nickname = StringField(max_length=32, nullable=False, comment="昵称")
    email = StringField(max_length=64, default="", comment="邮箱")
    phone = StringField(max_length=11, default="", comment="手机号")
    avatar = StringField(max_length=255, default="/static/imgs/avatar-default.png", comment="头像")
    role_id = ForeignKeyField(to=Role, nullable=False, comment="角色ID")
    status =  IntegerField(default=1, comment="状态 0-禁用 1-启用")
    last_login_time = DateTimeField(nullable=True, comment="最后登录时间")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")
    class Meta:
        table_name = "user"