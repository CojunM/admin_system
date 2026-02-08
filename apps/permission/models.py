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
from core import Model, IntField, StrField, DateTimeField

class Permission(Model):
    __table_name__ = "permissions"
    id = IntField(primary_key=True, comment="权限ID")
    code = StrField(length=64, unique=True, nullable=False, comment="权限标识")
    name = StrField(length=32, nullable=False, comment="权限名称")
    type = IntField(nullable=False, comment="1-页面 2-按钮 3-接口")
    parent_id = IntField(default=0, comment="父权限ID")
    sort = IntField(default=0, comment="排序")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")

class Menu(Model):
    __table_name__ = "menus"
    id = IntField(primary_key=True, comment="菜单ID")
    name = StrField(length=32, nullable=False, comment="菜单名称")
    path = StrField(length=64, nullable=False, comment="路由路径")
    component = StrField(length=128, nullable=False, comment="前端组件路径")
    icon = StrField(length=64, default="", comment="菜单图标")
    parent_id = IntField(default=0, comment="父菜单ID")
    sort = IntField(default=0, comment="排序")
    is_show = IntField(default=1, comment="是否显示 0-隐藏 1-显示")
    permission_code = StrField(length=64, default="", comment="关联权限标识")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")
    update_time = DateTimeField(auto_now=True, comment="更新时间")