#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core.router import post, get, put, delete
from utils.logger import logger
from utils.tree import build_tree
from apps.permission.models import Permission, Menu

@post("/api/permission/add")
def perm_add(request):
    """添加权限"""
    code = request.body.get("code")
    name = request.body.get("name")
    type = request.body.get("type")
    if not code or not name or type is None:
        return 400, {"msg": "权限标识、名称、类型不能为空"}
    
    if Permission.get(code=code):
        return 400, {"msg": "权限标识已存在"}
    
    perm = Permission(
        code=code,
        name=name,
        type=type,
        parent_id=request.body.get("parent_id", 0),
        sort=request.body.get("sort", 0)
    )
    perm.save()
    logger.info(f"[Permission] Add perm {code} by {request.user.get('username')}")
    return perm.to_dict()

@get("/api/permission/list")
def perm_list(request):
    """权限列表（树形）"""
    perms = Permission.filter()
    perm_list = [p.to_dict() for p in perms]
    # 构建树形结构
    tree = build_tree(perm_list, "id", "parent_id", "children")
    return tree

@put("/api/permission/edit/<perm_id>")
def perm_edit(request, perm_id):
    """编辑权限"""
    perm = Permission.get(id=perm_id)
    if not perm:
        return 404, {"msg": "权限不存在"}
    
    if "code" in request.body:
        code = request.body.get("code")
        if code != perm.code and Permission.get(code=code):
            return 400, {"msg": "权限标识已存在"}
        perm.code = code
    if "name" in request.body:
        perm.name = request.body.get("name")
    if "type" in request.body:
        perm.type = request.body.get("type")
    if "parent_id" in request.body:
        perm.parent_id = request.body.get("parent_id", 0)
    if "sort" in request.body:
        perm.sort = request.body.get("sort", 0)
    
    perm.save()
    logger.info(f"[Permission] Edit perm {perm_id} by {request.user.get('username')}")
    return perm.to_dict()

@delete("/api/permission/delete/<perm_id>")
def perm_delete(request, perm_id):
    """删除权限"""
    perm = Permission.get(id=perm_id)
    if not perm:
        return 404, {"msg": "权限不存在"}
    # 删除子权限
    child_perms = Permission.filter(parent_id=perm_id)
    for cp in child_perms:
        cp.delete()
    # 删除角色-权限关联
    from apps.role.models import RolePermission
    for rp in RolePermission.filter(permission_id=perm_id):
        rp.delete()
    perm.delete()
    logger.info(f"[Permission] Delete perm {perm_id} by {request.user.get('username')}")
    return {"msg": "删除成功"}

@get("/api/menu/list")
def menu_list(request):
    """菜单列表（树形）"""
    menus = Menu.filter(is_show=1)
    menu_list = [m.to_dict() for m in menus]
    tree = build_tree(menu_list, "id", "parent_id", "children")
    return tree

@post("/api/menu/add")
def menu_add(request):
    """添加菜单"""
    name = request.body.get("name")
    path = request.body.get("path")
    component = request.body.get("component")
    if not name or not path or not component:
        return 400, {"msg": "菜单名称、路径、组件不能为空"}
    
    menu = Menu(
        name=name,
        path=path,
        component=component,
        icon=request.body.get("icon", ""),
        parent_id=request.body.get("parent_id", 0),
        sort=request.body.get("sort", 0),
        is_show=request.body.get("is_show", 1),
        permission_code=request.body.get("permission_code", "")
    )
    menu.save()
    logger.info(f"[Menu] Add menu {name} by {request.user.get('username')}")
    return menu.to_dict()