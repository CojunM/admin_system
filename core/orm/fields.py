'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:22:38
LastEditors: Cojun
LastEditTime: 2026-01-25 19:22:48
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import datetime
from core.orm.base import Field

class IntField(Field):
    """整型字段"""
    def _to_db(self, value):
        return int(value)

    def _from_db(self, value):
        return int(value) if value is not None else None

class StrField(Field):
    """字符串字段"""
    def __init__(self, length=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.length = length

    def _to_db(self, value):
        s = str(value)
        if self.length and len(s) > self.length:
            raise ValueError(f"StrField {self.name} exceeds max length {self.length}")
        return s

    def _from_db(self, value):
        return str(value) if value is not None else None

class BoolField(Field):
    """布尔字段"""
    def _to_db(self, value):
        return bool(value)

    def _from_db(self, value):
        return bool(value) if value is not None else None

class FloatField(Field):
    """浮点数字段"""
    def _to_db(self, value):
        return float(value)

    def _from_db(self, value):
        return float(value) if value is not None else None

class DateTimeField(Field):
    """日期时间字段"""
    def __init__(self, auto_now=False, auto_now_add=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.auto_now = auto_now  # 每次保存自动更新为当前时间
        self.auto_now_add = auto_now_add  # 新增时自动设置为当前时间

        if self.auto_now and self.auto_now_add:
            raise ValueError("Cannot set both auto_now and auto_now_add")

        # 自动设置默认值
        if self.auto_now_add:
            self.default = datetime.datetime.now

    def get_default(self):
        if self.auto_now:
            return datetime.datetime.now()
        return super().get_default()

    def _to_db(self, value):
        if isinstance(value, str):
            return datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return value

    def _from_db(self, value):
        return value if isinstance(value, datetime.datetime) else None

class ForeignKeyField(Field):
    """外键字段"""
    def __init__(self, to, on_delete="CASCADE", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.to = to  # 关联模型
        self.on_delete = on_delete  # 删除策略
        self.nullable = kwargs.get("nullable", False)

    def _to_db(self, value):
        # 支持传入模型实例或主键值
        if isinstance(value, self.to):
            return value._pk_value
        return int(value)

    def _from_db(self, value):
        # 返回关联模型实例（延迟加载，实际使用时再查询）
        if value is None:
            return None
        return self.to.get(**{self.to._meta["primary_key"]: value})