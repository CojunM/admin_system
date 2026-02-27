#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
from collections import defaultdict
from config.settings import RATE_LIMIT_MAX, RATE_LIMIT_WHITELIST
from utils.logger import logger

# 存储请求计数 {client_addr: {path: [request_timestamps]}}
# 优化：按「IP+接口路径」分别计数，避免单个接口触发全局限流
_request_counts = defaultdict(lambda: defaultdict(list))
# 限流时间窗口（可配置，默认60秒）
_WINDOW = 60

# def rate_limit(max_requests: int = 60, window_seconds: int = 60):
    # """
    # 接口限流装饰器（自定义版）
    # :param max_requests: 时间窗口内最大请求数（默认60次）
    # :param window_seconds: 时间窗口（默认60秒）
    # :return: 装饰器函数
    # """
    # def decorator(func):
    #     @wraps(func)  # 保留原函数的名称和文档字符串
    #     def wrapper(request, response, *args, **kwargs):
    #         # 1. 获取客户端IP（兼容你的框架请求对象）
    #         client_addr = request.client_addr[0] if request.client_addr else "unknown"
            
    #         # 2. 生成唯一接口标识（用函数名，确保不同接口计数隔离）
    #         endpoint = f"{func.__module__}.{func.__name__}"
            
    #         now = time.time()
    #         # 3. 清理时间窗口外的请求记录
    #         _request_counts[client_addr][endpoint] = [
    #             t for t in _request_counts[client_addr][endpoint]
    #             if now - t < window_seconds
    #         ]
            
    #         # 4. 检查请求次数是否超限
    #         current_count = len(_request_counts[client_addr][endpoint])
    #         if current_count >= max_requests:
    #             # 计算需要等待的时间
    #             wait_seconds = int(window_seconds - (now - _request_counts[client_addr][endpoint][0]))
    #             wait_seconds = max(wait_seconds, 1)  # 至少等待1秒
                
    #             # 记录限流日志
    #             logger.warning(
    #                 f"[RateLimit] Too many requests | IP: {client_addr} | Endpoint: {endpoint} "
    #                 f"| Count: {current_count}/{max_requests} | Wait: {wait_seconds}s"
    #             )
                
    #             # 5. 返回429响应（和你原有逻辑一致）
    #             return response.json({
    #                 "code": 429,
    #                 "msg": f"Too many requests, please try again after {wait_seconds} seconds"
    #             }, 429)
            
    #         # 6. 记录本次请求时间
    #         _request_counts[client_addr][endpoint].append(now)
            
    #         # 7. 执行原接口函数
    #         return func(request, response, *args, **kwargs)
    #     return wrapper
    # return decorator
def rate_limit_middleware(request, response):
    """
    接口访问频率限制中间件（优化版）
    特性：
    1. 核心接口白名单豁免
    2. 按「IP+路径」独立计数，避免全局限流
    3. 动态调整不同接口的限流阈值
    4. 返回标准429响应 + Retry-After头
    """
    
    # ========== 1. 核心接口白名单（豁免限流） ==========
    # 在 config/settings.py 中配置：
    # RATE_LIMIT_WHITELIST = ["/api/user/info", "/api/user/login", "/api/dashboard/stats"]
    request_path = request.path.split("?")[0] if request.path else ""  # 去掉参数，纯路径匹配
    logger.debug(f"[RateLimit] Request path (raw): {request.path} | (normalized): {request_path}")
    if request_path in RATE_LIMIT_WHITELIST:
        logger.debug(f"[RateLimit] Skip rate limit | IP: {request.client_addr} | Path: {request.path}")
        return None  # 白名单接口跳过限流
    
    # ========== 2. 按接口配置不同限流阈值（可选） ==========
    # 特殊接口放宽限流（如仪表盘接口）
    path_limits = {
        "/api/dashboard/role-distribution": RATE_LIMIT_MAX * 2,  # 翻倍
        "/api/user/list": RATE_LIMIT_MAX // 2  # 更严格
    }
    current_limit = path_limits.get(request_path, RATE_LIMIT_MAX)

    # ========== 3. 获取客户端IP（兼容代理场景） ==========
    # 优先取X-Forwarded-For（代理/nginx场景），否则取原生IP
    client_addr = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
    if not client_addr or client_addr == "unknown":
        client_addr = request.client_addr[0] if request.client_addr else "unknown"

    now = time.time()
    path_key = request_path  # 按接口路径独立计数

    # ========== 4. 清理时间窗口外的请求记录 ==========
    _request_counts[client_addr][path_key] = [
        t for t in _request_counts[client_addr][path_key] 
        if now - t < _WINDOW
    ]

    # ========== 5. 检查请求次数是否超限 ==========
    current_count = len(_request_counts[client_addr][path_key])
    if current_count >= current_limit:
        # 计算重试等待时间
        retry_after = int(_WINDOW - (now - _request_counts[client_addr][path_key][0]))
        retry_after = max(retry_after, 1)  # 至少等待1秒

        # 记录限流日志
        logger.warning(
            f"[RateLimit] Too many requests | IP: {client_addr} | Path: {request_path} "
            f"| Count: {current_count}/{current_limit} | Retry after: {retry_after}s"
        )

        # ========== 6. 返回标准429响应（前端可识别） ==========
        response_data = {
            "code": 429,
            "msg": f"Too many requests, please try again after {retry_after} seconds",
            "data": None
        }
        # 设置标准429状态码 + Retry-After响应头
        resp = response.json(response_data, status_code=429)
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    # ========== 7. 记录本次请求时间 ==========
    _request_counts[client_addr][path_key].append(now)
    return None