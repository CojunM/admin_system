'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:45:27
LastEditors: Cojun
LastEditTime: 2026-01-25 19:45:44
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core.router import get
from apps.user.models import User
from apps.role.models import Role
from apps.permission.models import Permission, Menu
from apps.notify.models import Notification

@get("/api/dashboard/stat")
def dashboard_stat(request):
    """仪表盘统计数据"""
    user_id = request.user.get("id")
    # 统计各模块数量
    stat = {
        "user_count": len(User.filter()),
        "role_count": len(Role.filter()),
        "perm_count": len(Permission.filter()),
        "menu_count": len(Menu.filter()),
        "unread_notify": len(Notification.filter(user_id__in=[None, user_id], is_read=0))
    }
    # 近7天注册用户（简化版）
    stat["new_user_7d"] = 0
    # 角色分布
    role_dist = []
    for role in Role.filter():
        role_dist.append({
            "name": role.name,
            "count": len(User.filter(role_id=role.id))
        })
    stat["role_dist"] = role_dist
    return stat