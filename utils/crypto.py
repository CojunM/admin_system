#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
密码加密工具（移除bcrypt，使用Python内置hashlib+secrets实现加盐哈希）
函数接口保持不变：encrypt_password / verify_password
"""
import hashlib
import secrets

# 配置常量（可根据需求调整）
SALT_LENGTH = 16  # 随机盐值长度（16字节，推荐）
HASH_ALGORITHM = 'sha256'  # 哈希算法（sha256/sha512，推荐sha256）
ITERATIONS = 100000  # 哈希迭代次数（次数越高越安全，耗时也越长，10万次兼顾安全和性能）


def encrypt_pwd(plain_password: str) -> str:
    """
    加密明文密码：生成随机盐值 + 加盐哈希，返回「盐值:哈希值」拼接的字符串
    :param plain_password: 明文密码
    :return: 加密后的字符串（格式：salt:hashed_password，可直接存入数据库）
    """
    # 1. 生成唯一随机盐值（16字节，转为十六进制字符串，便于存储）
    salt = secrets.token_hex(SALT_LENGTH)
    # 2. 将密码和盐值转为bytes（哈希需要字节流）
    password_bytes = plain_password.encode('utf-8')
    salt_bytes = salt.encode('utf-8')
    # 3. 加盐哈希：使用pbkdf2_hmac（行业标准的加盐哈希算法，内置模块支持）
    hashed_bytes = hashlib.pbkdf2_hmac(
        hash_name=HASH_ALGORITHM,
        password=password_bytes,
        salt=salt_bytes,
        iterations=ITERATIONS
    )
    # 4. 将哈希值转为十六进制字符串，与盐值用「:」拼接返回
    hashed_password = hashed_bytes.hex()
    return f"{salt}:{hashed_password}"


def verify_pwd(plain_password: str, encrypted_password: str) -> bool:
    """
    验证明文密码是否匹配加密密码
    :param plain_password: 待验证的明文密码
    :param encrypted_password: 数据库中存储的加密密码（格式：salt:hashed_password）
    :return: 匹配返回True，不匹配返回False
    """
    try:
        # 1. 拆分盐值和哈希值（按「:」分割，需保证加密后的字符串格式正确）
        salt, hashed_password = encrypted_password.split(':', 1)
        # 2. 明文密码按相同规则加盐哈希
        password_bytes = plain_password.encode('utf-8')
        salt_bytes = salt.encode('utf-8')
        verify_hashed_bytes = hashlib.pbkdf2_hmac(
            hash_name=HASH_ALGORITHM,
            password=password_bytes,
            salt=salt_bytes,
            iterations=ITERATIONS
        )
        verify_hashed_password = verify_hashed_bytes.hex()
        # 3. 比较哈希值（使用恒时比较，防止时序攻击）
        return secrets.compare_digest(verify_hashed_password, hashed_password)
    except (ValueError, IndexError):
        # 分割失败（加密格式错误），直接返回False
        return False


# 测试代码（运行该文件可验证加密/验证逻辑）
if __name__ == "__main__":
    test_pwd = "Admin@123"
    encrypted = encrypt_password(test_pwd)
    print(f"明文密码：{test_pwd}")
    print(f"加密后：{encrypted}")
    print(f"验证正确密码：{verify_password(test_pwd, encrypted)}")  # True
    print(f"验证错误密码：{verify_password('123456', encrypted)}")  # False