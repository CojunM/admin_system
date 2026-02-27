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

@get("/api/dashboard/stats")
def dashboard_stat(request):
    """仪表盘统计数据"""
    try :
            user_id = request.user.get("id")
            print(f"[Dashboard] Get stat by {request.user.get('username')}")
            # Permission.migrate_table()
            # Menu.migrate_table()

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
            print(f"[Dashboard] Get stat: {stat}")
            return {
                    "code": 200,
                    "msg": "success",
                    "data": stat
                }
    except Exception as e:
            return {
                "code": 500,
                "msg": f"获取仪表盘数据失败：{str(e)}",
                "data": {}
            }

# ========== 新增：独立的角色分布接口（解决前端404） ==========
@get("/api/dashboard/role-distribution")
def dashboard_role_distribution(request):
    """角色分布接口（适配前端请求）"""
    try:
        # 复用角色分布的逻辑，返回前端需要的格式
        role_dist = []
        for role in Role.filter():
            role_dist.append({
                "name": role.name,  # 角色名称
                "count": len(User.filter(role_id=role.id))  # 该角色下的用户数
            })
        
        # 返回标准格式（兼容前端解析）
        return {
            "code": 200,
            "msg": "success",
            "data": role_dist
        }
    except Exception as e:
        print(f"[Error] 获取角色分布失败：{str(e)}")
        # 异常返回，避免前端崩溃
        return {
            "code": 500,
            "msg": f"获取角色分布失败：{str(e)}",
            "data": []
        }