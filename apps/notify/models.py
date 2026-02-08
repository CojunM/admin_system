'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:43:08
LastEditors: Cojun
LastEditTime: 2026-01-25 19:43:20
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core import Model, IntField, StrField, DateTimeField, ForeignKeyField
from apps.user.models import User

class Notification(Model):
    __table_name__ = "notifications"
    id = IntField(primary_key=True, comment="通知ID")
    title = StrField(length=128, nullable=False, comment="通知标题")
    content = StrField(nullable=False, comment="通知内容")
    type = IntField(default=1, comment="1-系统通知 2-业务通知")
    user_id = ForeignKeyField(to=User, nullable=True, comment="指定用户（NULL为全体）")
    is_read = IntField(default=0, comment="是否已读 0-未读 1-已读")
    create_time = DateTimeField(auto_now_add=True, comment="创建时间")