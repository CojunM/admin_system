'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:41:09
LastEditors: Cojun
LastEditTime: 2026-01-25 19:41:39
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core.peewee_orm_single1_1 import   IntegerField, StringField, DateTimeField
from apps import BaseModel

class Permission(BaseModel):
    
    id =  IntegerField(primary_key=True, comment="权限ID")
    code = StringField(max_length=64, unique=True, nullable=False, comment="权限标识")
    name = StringField(max_length=32, nullable=False, comment="权限名称")
    type =  IntegerField(nullable=False, comment="1-页面 2-按钮 3-接口")
    parent_id =  IntegerField(default=0, comment="父权限ID")
    sort =  IntegerField(default=0, comment="排序")
    create_time = DateTimeField(auto_now_add=True,  comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")

class Menu(BaseModel):
    
    id =  IntegerField(primary_key=True, comment="菜单ID")
    name = StringField(max_length=32, nullable=False, comment="菜单名称")
    path = StringField(max_length=64, nullable=False, comment="路由路径")
    component = StringField(max_length=128, nullable=False, comment="前端组件路径")
    icon = StringField(max_length=64, default="", comment="菜单图标")
    parent_id =  IntegerField(default=0, comment="父菜单ID")
    sort =  IntegerField(default=0, comment="排序")
    is_show =  IntegerField(default=1, comment="是否显示 0-隐藏 1-显示")
    permission_code = StringField(max_length=64, default="", comment="关联权限标识")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")