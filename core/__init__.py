'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 22:18:56
LastEditors: Cojun
LastEditTime: 2026-01-25 22:19:17
'''
# 核心框架模块初始化
from core.router import route, Router
from core.orm.base import Model
from core.orm.fields import IntField, StrField, BoolField, FloatField, DateTimeField, ForeignKeyField