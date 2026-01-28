#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
纯Python原生实现JWT（HS256算法）
不依赖任何第三方库，严格遵循JWT规范，支持exp过期时间验证
"""
import json
import time
import hmac
import hashlib
from base64 import b64encode, b64decode

def base64url_encode(data: bytes) -> str:
    """
    JWT标准Base64URL编码（无填充）
    :param data: 待编码字节流
    :return: Base64URL编码后的字符串
    """
    encoded = b64encode(data)
    # 替换特殊字符，删除填充符
    return encoded.decode('utf-8').replace('+', '-').replace('/', '_').rstrip('=')

def base64url_decode(s: str) -> bytes:
    """
    JWT标准Base64URL解码（自动补全填充符）
    :param s: Base64URL编码的字符串
    :return: 解码后的字节流
    """
    # 补全填充符
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += '=' * padding
    # 还原特殊字符，解码
    s = s.replace('-', '+').replace('_', '/')
    return b64decode(s)

def jwt_encode(payload: dict, secret_key: str, algorithm: str = "HS256") -> str:
    """
    生成JWT Token（仅支持HS256算法，符合JWT规范）
    :param payload: 载荷字典，可包含标准exp过期时间（时间戳）
    :param secret_key: 签名密钥（与项目SECRET_KEY一致）
    :param algorithm: 签名算法，固定为HS256
    :return: 完整的JWT Token字符串
    """
    if algorithm != "HS256":
        raise ValueError("Only HS256 algorithm is supported")
    
    # 1. 构造JWT头部：指定算法和类型
    header = {
        "alg": algorithm,
        "typ": "JWT"
    }
    # 2. 头部和载荷分别JSON序列化+Base64URL编码
    header_encoded = base64url_encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_encoded = base64url_encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    # 3. 拼接头部和载荷，生成签名原始数据
    sign_data = f"{header_encoded}.{payload_encoded}".encode('utf-8')
    # 4. HMAC-SHA256生成签名，再Base64URL编码
    secret = secret_key.encode('utf-8')
    signature = hmac.new(secret, sign_data, hashlib.sha256).digest()
    signature_encoded = base64url_encode(signature)
    # 5. 拼接三部分得到最终Token
    return f"{header_encoded}.{payload_encoded}.{signature_encoded}"

def jwt_decode(token: str, secret_key: str, algorithm: str = "HS256", verify: bool = True) -> dict:
    """
    解析并验证JWT Token（仅支持HS256算法）
    :param token: 待解析的JWT Token
    :param secret_key: 签名密钥（与生成时一致）
    :param algorithm: 签名算法，固定为HS256
    :param verify: 是否验证签名和过期时间
    :return: 解析后的载荷字典
    :raises: 验证失败时抛出ValueError
    """
    if algorithm != "HS256":
        raise ValueError("Only HS256 algorithm is supported")
    
    # 1. 分割Token为三部分，验证格式合法性
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid JWT token: must have 3 parts")
    header_encoded, payload_encoded, signature_encoded = parts
    
    # 2. 验证签名（若开启验证）
    if verify:
        # 重新生成签名并与原签名对比
        sign_data = f"{header_encoded}.{payload_encoded}".encode('utf-8')
        secret = secret_key.encode('utf-8')
        expected_signature = hmac.new(secret, sign_data, hashlib.sha256).digest()
        actual_signature = base64url_decode(signature_encoded)
        # 常量时间比较，防止时序攻击
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("Invalid JWT signature: signature verification failed")
    
    # 3. 解析载荷
    payload_data = base64url_decode(payload_encoded)
    payload = json.loads(payload_data.decode('utf-8'))
    
    # 4. 验证过期时间（若开启验证且包含exp字段）
    if verify and "exp" in payload:
        current_time = time.time()
        if current_time > payload["exp"]:
            raise ValueError("Expired JWT token: token has expired")
    
    return payload