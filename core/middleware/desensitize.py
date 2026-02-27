#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
✅ 生产级脱敏中间件（深度优化版）
✅ 特性：高性能/易扩展/配置化/类型安全/异常隔离
"""
import json
import re
from typing import Dict, Callable, Any, Optional
from functools import lru_cache

# 导入项目配置和日志（保持和你项目一致）
from config.settings import DESENSITIZE_CONFIG
from utils.logger import logger

# ======================== 1. 常量定义（抽离配置，便于维护） ========================
# 可在 config/settings.py 中配置
# DESENSITIZE_CONFIG = {
#     "exclude_paths": ["/api/user/login", "/api/user/info", "/api/user/refresh"],
#     "rules": {
#         "phone": {
#             "pattern": r"^1[3-9]\d{9}$",  # 严格手机号正则
#             "handler": lambda x: f"{x[:3]}****{x[-4:]}"
#         },
#         "email": {
#             "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
#             "handler": lambda x: f"{x[:2]}****@{x.split('@', 1)[1]}"
#         },
#         "id_card": {
#             "pattern": r"^\d{18}$",
#             "handler": lambda x: f"{x[:6]}********{x[-4:]}"
#         }
#     },
#     "max_body_size": 1024 * 1024,  # 1MB
#     "enable": True  # 全局开关
# }

# ======================== 2. 高性能工具函数（缓存/预编译） ========================
@lru_cache(maxsize=128)
def compile_pattern(pattern_str: str) -> re.Pattern:
    """预编译正则表达式（缓存提升性能）"""
    return re.compile(pattern_str)

def is_excluded_path(path: str, exclude_paths: list) -> bool:
    """
    判断路径是否在排除列表（支持模糊匹配）
    示例：/api/user/info/1 → 匹配 /api/user/info
    """
    if not path or not exclude_paths:
        return False
    # 提取纯路径（去掉参数和尾部斜杠）
    clean_path = path.split("?")[0].rstrip("/")
    return any(clean_path.startswith(excl.rstrip("/")) for excl in exclude_paths)

def safe_json_loads(raw_str: str) -> Optional[Any]:
    """安全解析JSON（失败返回None）"""
    try:
        return json.loads(raw_str)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

def safe_json_dumps(data: Any) -> bytes:
    """安全序列化JSON（兼容特殊类型）"""
    try:
        return json.dumps(
            data,
            ensure_ascii=False,
            default=str,  # 兼容datetime/UUID/对象等
            separators=(",", ":"),  # 压缩JSON，减少传输体积
            indent=None
        ).encode("utf-8")
    except Exception as e:
        logger.error(f"JSON序列化失败: {str(e)}")
        return b""

# ======================== 3. 可扩展的脱敏处理器 ========================
class DesensitizeHandler:
    """脱敏处理器（面向对象，便于扩展）"""
    def __init__(self, config: Dict):
        self.config = config
        self.rules = config.get("rules", {})
        self.enable = config.get("enable", True)
        self.max_body_size = config.get("max_body_size", 1024 * 1024)

    def should_skip(self, request_path: str, body_size: int) -> bool:
        """判断是否需要跳过脱敏"""
        # 全局开关关闭
        if not self.enable:
            return True
        # 路径在排除列表
        if is_excluded_path(request_path, self.config.get("exclude_paths", [])):
            return True
        # 响应体过大
        if body_size > self.max_body_size:
            logger.debug(f"响应体过大({body_size}字节)，跳过脱敏")
            return True
        return False

    def desensitize_field(self, field_name: str, value: Any) -> Any:
        """
        单字段脱敏（核心逻辑）
        :param field_name: 字段名（如phone/email）
        :param value: 字段值（任意类型）
        :return: 脱敏后的值
        """
        # 非目标字段/空值直接返回
        if field_name not in self.rules or value is None:
            return value
        
        # 统一转为字符串并清理
        value_str = str(value).strip()
        if not value_str:
            return value
        
        # 匹配规则并脱敏
        rule = self.rules[field_name]
        pattern = compile_pattern(rule["pattern"])
        if pattern.match(value_str):
            try:
                return rule["handler"](value_str)
            except Exception as e:
                logger.warning(f"字段[{field_name}]脱敏失败: {str(e)} | 值: {value_str[:50]}")
        return value

    def traverse_desensitize(self, data: Any) -> Any:
        """
        递归遍历数据并脱敏（支持dict/list/nested结构）
        :param data: 任意类型数据（dict/list/基础类型）
        :return: 脱敏后的数据
        """
        # 基础类型直接返回
        if isinstance(data, (int, float, bool, bytes)):
            return data
        
        # 字典类型：遍历字段脱敏
        if isinstance(data, dict):
            return {
                k: self.desensitize_field(k, self.traverse_desensitize(v))
                for k, v in data.items()
            }
        
        # 列表/元组类型：递归处理每个元素
        if isinstance(data, (list, tuple)):
            return [self.traverse_desensitize(item) for item in data]
        
        # 其他类型（字符串等）直接返回
        return data

# ======================== 4. 最终中间件入口 ========================
def desensitize_middleware(request, response):
    """
    脱敏中间件入口（极简封装，便于维护）
    :param request: 请求对象
    :param response: 响应对象
    :return: None
    """
    # 初始化处理器
    handler = DesensitizeHandler(DESENSITIZE_CONFIG)
    
    try:
        # 1. 前置校验：是否跳过脱敏
        body_size = len(response.body) if response.body else 0
        if handler.should_skip(request.path, body_size):
            return None
        
        # 2. 仅处理JSON响应
        content_type = response.headers.get("Content-Type", "")
        if "application/json" not in content_type:
            return None
        
        # 3. 安全解码响应体
        if not response.body:
            return None
        body_str = response.body.decode("utf-8", errors="replace").strip()
        if not body_str:
            return None
        
        # 4. 安全解析JSON
        response_data = safe_json_loads(body_str)
        if response_data is None:
            logger.debug(f"非JSON格式响应，跳过脱敏 | 内容: {body_str[:100]}")
            return None
        
        # 5. 核心脱敏逻辑（仅处理data字段）
        if "data" in response_data and isinstance(response_data["data"], (dict, list)):
            response_data["data"] = handler.traverse_desensitize(response_data["data"])
            # 重新序列化回响应体
            new_body = safe_json_dumps(response_data)
            if new_body:
                response.body = new_body
    
    # 6. 全局异常捕获（不影响主流程）
    except Exception as e:
        logger.warning(f"脱敏中间件执行失败: {str(e)}")
    
    return None