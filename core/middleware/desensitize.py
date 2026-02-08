#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
from config.settings import DESENSITIZE_FIELDS
from utils.logger import logger

def desensitize_middleware(request, response):
    """敏感数据脱敏中间件：对响应中的指定字段进行脱敏"""
    # 白名单：忽略登录、令牌相关接口
    no_desensitize_paths = ["/api/user/login", "/api/user/info", "/api/user/refresh"]
    if request.path in no_desensitize_paths:
        return None

    # 仅对JSON响应生效
    if "application/json" not in response.headers.get("Content-Type", ""):
        return None

    # 脱敏处理函数
    def _desensitize(data):
        if isinstance(data, dict):
            for k, v in data.items():
                if k in DESENSITIZE_FIELDS and isinstance(v, str):
                    # 手机号脱敏：138****1234
                    if k == "phone" and len(v) == 11:
                        data[k] = f"{v[:3]}****{v[-4:]}"
                    # 邮箱脱敏：te****@example.com
                    elif k == "email" and "@" in v:
                        prefix, suffix = v.split("@", 1)
                        if len(prefix) > 2:
                            prefix = f"{prefix[:2]}****"
                        data[k] = f"{prefix}@{suffix}"
                else:
                    _desensitize(v)
        elif isinstance(data, list):
            for item in data:
                _desensitize(item)
        return data

    # 解析响应体并脱敏
    try:
        response_data = json.loads(response.body.decode("utf-8", errors="ignore"))
        if "data" in response_data:
            response_data["data"] = _desensitize(response_data["data"])
            response.body = json.dumps(response_data, ensure_ascii=False, default=str).encode("utf-8")
    except Exception as e:
        logger.warning(f"[Desensitize] Process failed: {str(e)}")
    return None