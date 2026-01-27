'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:43:54
LastEditors: Cojun
LastEditTime: 2026-01-25 19:44:05
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core.router import post, get, put, delete
from utils.logger import logger
from apps.notify.models import Notification

@post("/api/notify/add")
def notify_add(request):
    """添加通知"""
    title = request.body.get("title")
    content = request.body.get("content")
    if not title or not content:
        return 400, {"msg": "通知标题和内容不能为空"}
    
    notify = Notification(
        title=title,
        content=content,
        type=request.body.get("type", 1),
        user_id=request.body.get("user_id", None),
        is_read=0
    )
    notify.save()
    logger.info(f"[Notify] Add notify {title} by {request.user.get('username')}")
    return notify.to_dict()

@get("/api/notify/list")
def notify_list(request):
    """通知列表（当前用户）"""
    page = int(request.query.get("page", 1))
    page_size = int(request.query.get("page_size", 10))
    user_id = request.user.get("id")
    # 全体通知+个人通知
    paginated = Notification.paginate(
        page=page,
        page_size=page_size,
        **{"user_id__in": [None, user_id]}  # ORM扩展in查询，简化版
    )
    paginated["list"] = [n.to_dict() for n in paginated["list"]]
    return paginated

@get("/api/notify/unread-count")
def unread_count(request):
    """未读通知数量"""
    user_id = request.user.get("id")
    # 简化版：实际需用count查询
    unread = Notification.filter(user_id__in=[None, user_id], is_read=0)
    return {"count": len(unread)}

@put("/api/notify/read/<notify_id>")
def notify_read(request, notify_id):
    """标记通知为已读"""
    notify = Notification.get(id=notify_id)
    if not notify:
        return 404, {"msg": "通知不存在"}
    # 检查权限：个人通知或全体通知
    if notify.user_id and notify.user_id != request.user.get("id"):
        return 403, {"msg": "无权限操作该通知"}
    notify.is_read = 1
    notify.save()
    return {"msg": "标记已读成功"}

@put("/api/notify/read-all")
def notify_read_all(request):
    """全部标为已读"""
    user_id = request.user.get("id")
    notifies = Notification.filter(user_id__in=[None, user_id], is_read=0)
    for n in notifies:
        n.is_read = 1
        n.save()
    logger.info(f"[Notify] Mark all notify as read by {request.user.get('username')}")
    return {"msg": "全部标为已读成功", "count": len(notifies)}

@delete("/api/notify/delete/<notify_id>")
def notify_delete(request, notify_id):
    """删除通知"""
    notify = Notification.get(id=notify_id)
    if not notify:
        return 404, {"msg": "通知不存在"}
    notify.delete()
    logger.info(f"[Notify] Delete notify {notify_id} by {request.user.get('username')}")
    return {"msg": "删除成功"}