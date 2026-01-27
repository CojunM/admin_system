'''
Descripttion: 
version: 
Author: Cojun
Date: 2026-01-25 19:57:01
LastEditors: Cojun
LastEditTime: 2026-01-25 19:57:14
'''
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re

def is_username(username):
    """验证用户名：3-32位，字母/数字/下划线"""
    if not isinstance(username, str):
        return False
    return re.match(r"^[a-zA-Z0-9_]{3,32}$", username) is not None

def is_phone(phone):
    """验证手机号：11位数字，以1开头"""
    if not isinstance(phone, str):
        return False
    return re.match(r"^1[3-9]\d{9}$", phone) is not None

def is_email(email):
    """验证邮箱格式"""
    if not isinstance(email, str) or not email:
        return True  # 空邮箱允许
    return re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email) is not None

def is_password(pwd):
    """验证密码：6-20位，字母+数字（可选特殊字符）"""
    if not isinstance(pwd, str):
        return False
    return re.match(r"^(?=.*[a-zA-Z])(?=.*\d).{6,20}$", pwd) is not None

def validate_params(rules, params):
    """
    批量参数验证
    :param rules: 验证规则 {字段名: 验证函数}
    :param params: 待验证参数字典
    :return: (is_valid, error_msg)
    """
    for field, func in rules.items():
        value = params.get(field)
        if not func(value):
            return False, f"字段{field}格式错误"
    return True, "验证通过"