#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from core.router import post, get, put, delete
from utils.logger import logger
from apps.role.models import Role, RolePermission
from apps.permission.models import Permission

@post("/api/role/add")
def role_add(request):
    """添加角色"""
    name = request.body.get("name")
    code = request.body.get("code")
    if not name or not code:
        return 400, {"msg": "角色名称和标识不能为空"}
    
    if Role.get(name=name):
        return 400, {"msg": "角色名称已存在"}
    if Role.get(code=code):
        return 400, {"msg": "角色标识已存在"}
    
    role = Role(
        name=name,
        code=code,
        desc=request.body.get("desc", ""),
        is_admin=request.body.get("is_admin", 0),
        sort=request.body.get("sort", 0)
    )
    role.save()
    logger.info(f"[Role] Add role {name} by {request.user.get('username')}")
    return role.to_dict()

@get("/api/role/list")
def role_list(request):
    """角色列表"""
    page = int(request.query.get("page", 1))
    page_size = int(request.query.get("page_size", 10))
    paginated = Role.paginate(page=page, page_size=page_size)
    # 补充权限数量
    for role in paginated["list"]:
        perm_count = len(RolePermission.filter(role_id=role.id))
        role.perm_count = perm_count
    paginated["list"] = [r.to_dict() for r in paginated["list"]]
    return paginated

@put("/api/role/edit/<role_id>")
def role_edit(request, role_id):
    """编辑角色"""
    role = Role.get(id=role_id)
    if not role:
        return 404, {"msg": "角色不存在"}
    # 禁止修改超级管理员标识
    if role.is_admin == 1 and "is_admin" in request.body:
        return 403, {"msg": "禁止修改超级管理员属性"}
    
    if "name" in request.body:
        name = request.body.get("name")
        if name != role.name and Role.get(name=name):
            return 400, {"msg": "角色名称已存在"}
        role.name = name
    if "code" in request.body:
        code = request.body.get("code")
        if code != role.code and Role.get(code=code):
            return 400, {"msg": "角色标识已存在"}
        role.code = code
    if "desc" in request.body:
        role.desc = request.body.get("desc", "")
    if "sort" in request.body:
        role.sort = request.body.get("sort", 0)
    
    role.save()
    logger.info(f"[Role] Edit role {role_id} by {request.user.get('username')}")
    return role.to_dict()

@delete("/api/role/delete/<role_id>")
def role_delete(request, role_id):
    """删除角色"""
    role = Role.get(id=role_id)
    if not role:
        return 404, {"msg": "角色不存在"}
    if role.is_admin == 1:
        return 403, {"msg": "禁止删除超级管理员角色"}
    # 删除角色及关联权限
    RolePermission.filter(role_id=role_id)
    for rp in RolePermission.filter(role_id=role_id):
        rp.delete()
    role.delete()
    logger.info(f"[Role] Delete role {role_id} by {request.user.get('username')}")
    return {"msg": "删除成功"}

@post("/api/role/assign-perm/<role_id>")
def assign_perm(request, role_id):
    """角色分配权限"""
    perm_ids = request.body.get("perm_ids", [])
    if not isinstance(perm_ids, list):
        return 400, {"msg": "权限ID必须为数组"}
    
    # 删除原有权限
    for rp in RolePermission.filter(role_id=role_id):
        rp.delete()
    # 添加新权限
    for perm_id in perm_ids:
        if Permission.get(id=perm_id):
            rp = RolePermission(role_id=role_id, permission_id=perm_id)
            rp.save()
    logger.info(f"[Role] Assign {len(perm_ids)} permissions to role {role_id} by {request.user.get('username')}")
    return {"msg": "权限分配成功", "count": len(perm_ids)}

@get("/api/role/perm-list/<role_id>")
def role_perm_list(request, role_id):
    """获取角色已分配权限"""
    rp_list = RolePermission.filter(role_id=role_id)
    perm_ids = [rp.permission_id for rp in rp_list]
    perms = [Permission.get(id=p).to_dict() for p in perm_ids if Permission.get(id=p)]
    return perm_ids