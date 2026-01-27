#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
from collections import defaultdict
from config.settings import RATE_LIMIT_MAX
from utils.logger import logger

# 存储请求计数 {client_addr: [request_timestamps]}
_request_counts = defaultdict(list)
# 限流时间窗口（60秒）
_WINDOW = 60

def rate_limit_middleware(request, response):
    """接口访问频率限制中间件：每分钟最大RATE_LIMIT_MAX次"""
    client_addr = request.client_addr[0]  # 取客户端IP
    now = time.time()

    # 清理时间窗口外的请求记录
    _request_counts[client_addr] = [t for t in _request_counts[client_addr] if now - t < _WINDOW]

    # 检查请求次数
    if len(_request_counts[client_addr]) >= RATE_LIMIT_MAX:
        logger.warning(f"[RateLimit] Too many requests from {client_addr}, path: {request.path}, count: {len(_request_counts[client_addr])}")
        return response.json({
            "code": 429,
            "msg": f"Too many requests, please try again after {int(_WINDOW - (now - _request_counts[client_addr][0]))} seconds"
        }, 429)

    # 记录本次请求时间
    _request_counts[client_addr].append(now)
    return None