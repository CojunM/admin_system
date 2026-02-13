#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
import json
import urllib.parse
from typing import Callable, Dict, List, Tuple, Any, Optional, Pattern, List
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from utils.logger import logger
from config.settings import  STATIC_DIR, TEMPLATE_DIR
import os

# ===================== 新增：Hook管理器核心实现 =====================
class HookManager:
    """Hook管理器：实现before_request/after_request/app_reset"""
    def __init__(self):
        # 存储Hook回调函数列表
        self._before_request_hooks: List[Callable] = []  # 每个请求前执行
        self._after_request_hooks: List[Callable] = []   # 每个请求后执行
        self._app_reset_hooks: List[Callable] = []       # 应用重置时执行

    # ---------- before_request 注册/执行 ----------
    def before_request(self, func: Callable) -> Callable:
        """装饰器：注册before_request钩子（支持多个）"""
        self._before_request_hooks.append(func)
        logger.info(f"注册before_request钩子：{func.__name__}")
        return func

    def run_before_request(self, request: "Request") -> None:
        """执行所有before_request钩子（请求处理前）"""
        for hook in self._before_request_hooks:
            try:
                hook(request)  # 传递request对象给钩子函数
            except Exception as e:
                logger.error(f"before_request钩子[{hook.__name__}]执行失败：{str(e)}", exc_info=True)

    # ---------- after_request 注册/执行 ----------
    def after_request(self, func: Callable) -> Callable:
        """装饰器：注册after_request钩子（支持多个）"""
        self._after_request_hooks.append(func)
        logger.info(f"注册after_request钩子：{func.__name__}")
        return func

    def run_after_request(self, request: "Request", response: "Response") -> None:
        """执行所有after_request钩子（请求处理后）"""
        for hook in self._after_request_hooks:
            try:
                hook(request, response)  # 传递request/response对象给钩子函数
            except Exception as e:
                logger.error(f"after_request钩子[{hook.__name__}]执行失败：{str(e)}", exc_info=True)

    # ---------- app_reset 注册/执行 ----------
    def app_reset(self, func: Callable) -> Callable:
        """装饰器：注册app_reset钩子（支持多个）"""
        self._app_reset_hooks.append(func)
        logger.info(f"注册app_reset钩子：{func.__name__}")
        return func

    def run_app_reset(self) -> None:
        """执行所有app_reset钩子（应用重置时）"""
        logger.warning("开始执行应用重置钩子...")
        for hook in self._app_reset_hooks:
            try:
                hook()
                logger.info(f"app_reset钩子[{hook.__name__}]执行成功")
            except Exception as e:
                logger.error(f"app_reset钩子[{hook.__name__}]执行失败：{str(e)}", exc_info=True)
        logger.warning("应用重置钩子执行完成")

# 全局Hook管理器实例（项目中唯一）
hook_manager = HookManager()

# ===================== 新增：暴露app_reset全局函数 =====================
def trigger_app_reset():
    """触发应用重置（供热更新/重启时调用）"""
    hook_manager.run_app_reset()


class Router:
    """路由核心类：管理所有路由规则，匹配请求"""
    def __init__(self):
        self.routes = {
            "GET": {},
            "POST": {},
            "PUT": {},
            "DELETE": {},
            "PATCH": {}
        }
        # 路由参数正则（匹配<name>、<name:type>）
        self.param_pattern = re.compile(r"<([a-zA-Z0-9_]+)(?::([a-zA-Z0-9_]+))?>")
         # 新增：初始化日志
        logger.info(f"[Router] 全局路由表初始化完成，初始方法：{list(self.routes.keys())}")
       

    def add_route(self, method, path, handler):
        """添加路由规则"""
        if path in self.routes[method]:
            logger.warning(f"[Router] Route {method} {path} already exists, overwrite it")
        # 编译路由为正则，提取参数
        regex_path, params = self._compile_route(path)
        self.routes[method][path] = {
            "regex": re.compile(regex_path),
            "params": params,
            "handler": handler
        }
        logger.debug(f"[Router] Add route {method} {path} -> {handler.__module__}.{handler.__name__}")

    def _compile_route(self, path):
        """编译路由路径为正则表达式，返回(regex, params)"""
        regex_parts = []
        params = []
        parts = path.split("/")
        for part in parts:
            if not part:
                regex_parts.append(part)
                continue
            match = self.param_pattern.match(part)
            if match:
                # 提取参数名和类型（暂不做类型校验，仅记录）
                param_name, param_type = match.groups()
                params.append((param_name, param_type or "str"))
                # 生成参数正则（匹配任意非/字符）
                regex_parts.append(r"([^/]+)")
            else:
                regex_parts.append(re.escape(part))
        # 拼接正则，添加开始和结束标识
        regex_path = r"^" + r"/".join(regex_parts) + r"$"
        return regex_path, params

    def match(self, method, path):
        """匹配路由，返回(handler, params, query)"""
        method = method.upper()
        if method not in self.routes:
            return None, {}, {}
        
        # 解析查询参数
        parsed_url = urlparse(path)
        path = parsed_url.path
        query = parse_qs(parsed_url.query)
        # 转换query为单值（默认取第一个）
        query = {k: v[0] if len(v) > 0 else "" for k, v in query.items()}

        # 匹配路由规则
        for route_path, route_info in self.routes[method].items():
            match = route_info["regex"].match(path)
            if match:
                # 解析路径参数
                params = {}
                for idx, (param_name, _) in enumerate(route_info["params"]):
                    params[param_name] = match.group(idx + 1)
                logger.debug(f"[Router] Match route {method} {route_path}, params: {params}, query: {query}")
                return route_info["handler"], params, query
        logger.info(f"[Router] No match route {method} {path}")
        return None, {}, query

# 全局路由实例
router = Router()

def route(path, method=["GET"]):
    """Bottle风格路由装饰器，支持多方法"""
    if not isinstance(method, list):
        method = [method]
    
    def decorator(handler):
        for m in method:
            router.add_route(m, path, handler)
        return handler
    return decorator

# RESTful快捷装饰器
def get(path):
    return route(path, method="GET")

def post(path):
    return route(path, method="POST")

def put(path):
    return route(path, method="PUT")

def delete(path):
    return route(path, method="DELETE")

def patch(path):
    return route(path, method="PATCH")