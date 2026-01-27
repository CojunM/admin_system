#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import mimetypes
from urllib.parse import unquote
from http.server import HTTPServer, BaseHTTPRequestHandler

# 原有所有导入依赖（完全不变）
from core.router import router
from config.settings import STATIC_DIR, DEBUG
from utils.logger import logger
from core.middleware import (
    csrf_middleware, rate_limit_middleware, throttle_middleware,
    debounce_middleware, auth_middleware, desensitize_middleware
)

# 注册全局中间件（执行顺序：从上到下，完全不变）
GLOBAL_MIDDLEWARES = [
    rate_limit_middleware,    # 接口限流
    csrf_middleware,          # CSRF防护
    auth_middleware,          # 权限认证
    throttle_middleware,      # 请求节流
    debounce_middleware,      # 请求防抖
    desensitize_middleware    # 敏感数据脱敏
]

# ===================== 原有Request类（完全不变） =====================
class Request:
    """HTTP请求对象：解析请求数据"""
    def __init__(self, raw_data, client_addr):
        self.raw_data = raw_data.decode("utf-8", errors="ignore")
        self.client_addr = client_addr
        self.method = "GET"
        self.path = "/"
        self.headers = {}
        self.body = {}
        self.cookies = {}
        self.csrf_token = None
        self.user = None  # 认证后用户信息
        self._parse()

    def _parse(self):
        """解析HTTP请求"""
        if not self.raw_data:
            return
        
        # 分割请求行、头部、体
        parts = self.raw_data.split("\r\n\r\n", 1)
        header_part = parts[0]
        body_part = parts[1] if len(parts) > 1 else ""

        # 解析请求行和头部
        lines = header_part.split("\r\n")
        if lines:
            # 请求行：METHOD PATH PROTOCOL
            request_line = lines[0].strip()
            if request_line:
                method, path, _ = request_line.split(" ", 2)
                self.method = method
                self.path = unquote(path)
            # 解析头部
            for line in lines[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    self.headers[key.strip()] = value.strip()

        # 解析Cookies
        if "Cookie" in self.headers:
            cookie_str = self.headers["Cookie"]
            for cookie in cookie_str.split(";"):
                if "=" in cookie:
                    k, v = cookie.split("=", 1)
                    self.cookies[k.strip()] = v.strip()
            self.csrf_token = self.cookies.get("X-CSRF-Token")

        # 解析请求体
        content_type = self.headers.get("Content-Type", "")
        if "application/json" in content_type and body_part:
            try:
                self.body = json.loads(body_part)
            except json.JSONDecodeError:
                self.body = {}
        elif "application/x-www-form-urlencoded" in content_type and body_part:
            from urllib.parse import parse_qs
            self.body = parse_qs(body_part)
            self.body = {k: v[0] if len(v) > 0 else "" for k, v in self.body.items()}
        else:
            self.body = {}

# ===================== 原有Response类（完全不变） =====================
class Response:
    """HTTP响应对象：构造响应数据"""
    def __init__(self, status=200, headers=None, body=None):
        self.status = status
        self.headers = headers or {}
        self.body = body or b""
        self._set_default_headers()

    def _set_default_headers(self):
        """设置默认响应头"""
        if "Content-Type" not in self.headers:
            self.headers["Content-Type"] = "application/json; charset=utf-8"
        if "Server" not in self.headers:
            self.headers["Server"] = "Python-Native-HTTP-Server"
        # 跨域配置
        self.headers["Access-Control-Allow-Origin"] = "*"
        self.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,PATCH,OPTIONS"
        self.headers["Access-Control-Allow-Headers"] = "Content-Type,X-CSRF-Token,Authorization"

    def set_cookie(self, name, value, max_age=None, path="/"):
        """设置Cookie"""
        cookie = f"{name}={value}; Path={path}"
        if max_age:
            cookie += f"; Max-Age={max_age}"
        self.headers["Set-Cookie"] = cookie

    def json(self, data, status=200):
        """构造JSON响应"""
        self.status = status
        self.body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        return self

    def html(self, html, status=200):
        """构造HTML响应"""
        self.status = status
        self.headers["Content-Type"] = "text/html; charset=utf-8"
        self.body = html.encode("utf-8")
        return self

    def static(self, file_path):
        """构造静态文件响应"""
        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.status = 404
            self.body = b"404 Not Found"
            return self
        
        # 获取文件MIME类型
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            self.headers["Content-Type"] = mime_type
        else:
            self.headers["Content-Type"] = "application/octet-stream"
        
        # 读取文件内容
        with open(file_path, "rb") as f:
            self.body = f.read()
        return self

    def build(self):
        """构建最终的HTTP响应字节流"""
        # 状态码描述
        status_messages = {
            200: "OK", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
            404: "Not Found", 405: "Method Not Allowed", 500: "Internal Server Error"
        }
        status_msg = status_messages.get(self.status, "Unknown Status")
        # 构建响应行
        response_line = f"HTTP/1.1 {self.status} {status_msg}\r\n"
        # 构建响应头
        response_headers = "".join([f"{k}: {v}\r\n" for k, v in self.headers.items()])
        # 构建响应体
        response_body = self.body
        # 拼接所有部分
        return (response_line + response_headers + "\r\n").encode("utf-8") + response_body

# ===================== 原有请求处理逻辑（完全不变） =====================
def handle_request(raw_data, client_addr):
    """处理单个HTTP请求"""
    try:
        # 1. 解析请求
        request = Request(raw_data, client_addr)
        response = Response()

        # 处理OPTIONS预检请求
        if request.method == "OPTIONS":
            return response.build()

        # 2. 匹配路由（静态文件优先）
        if request.path.startswith("/static/"):
            file_path = os.path.join(STATIC_DIR, request.path[8:])
            response.static(file_path)
            return response.build()
        
        # 匹配接口路由
        handler, params, query = router.match(request.method, request.path)
        if not handler:
            # 匹配前端页面
            if request.path == "/":
                file_path = os.path.join(STATIC_DIR, "index.html")
            else:
                file_path = os.path.join(STATIC_DIR, "pages", request.path.lstrip("/") + ".html")
            if os.path.exists(file_path):
                response.static(file_path)
            else:
                response.json({"code": 404, "msg": "API not found"}, 404)
            return response.build()

        # 3. 执行全局中间件
        for middleware in GLOBAL_MIDDLEWARES:
            middleware_result = middleware(request, response)
            if middleware_result is not None:
                # 中间件返回非None表示中断请求
                return middleware_result.build()

        # 4. 执行接口处理器
        # 合并参数：path_params > query > body
        all_params = {**request.body, **query, **params}
        result = handler(request, **all_params)

        # 5. 构造响应
        if isinstance(result, dict):
            response.json({"code": 200, "msg": "success", "data": result})
        elif isinstance(result, tuple) and len(result) == 2:
            code, data = result
            response.json({"code": code, "msg": "success" if code == 200 else "failed", "data": data})
        else:
            response.json({"code": 200, "msg": "success", "data": result})

        return response.build()

    except Exception as e:
        logger.error(f"[Server] Handle request error: {str(e)}", exc_info=True)
        response = Response()
        error_msg = str(e) if DEBUG else "Internal server error"
        response.json({"code": 500, "msg": error_msg}, 500)
        return response.build()

# ===================== 基于HTTPServer的请求处理器（新增核心） =====================
class HTTPServerRequestHandler(BaseHTTPRequestHandler):
    """
    自定义HTTPServer请求处理器
    桥接HTTPServer和原有handle_request逻辑，无侵入式适配
    """
    def do_GET(self):
        """处理GET请求：复用原有handle_request"""
        self._handle_all_methods()

    def do_POST(self):
        """处理POST请求：复用原有handle_request"""
        self._handle_all_methods()

    def do_PUT(self):
        """处理PUT请求：复用原有handle_request"""
        self._handle_all_methods()

    def do_DELETE(self):
        """处理DELETE请求：复用原有handle_request"""
        self._handle_all_methods()

    def do_PATCH(self):
        """处理PATCH请求：复用原有handle_request"""
        self._handle_all_methods()

    def do_OPTIONS(self):
        """处理OPTIONS请求：复用原有handle_request"""
        self._handle_all_methods()

    def _handle_all_methods(self):
        """统一处理所有HTTP方法，桥接原有逻辑"""
        # 1. 构造原始请求数据（模拟原生socket的raw_data格式）
        # 拼接请求行
        request_line = f"{self.command} {self.path} HTTP/1.1\r\n"
        # 拼接请求头
        request_headers = "".join([f"{k}: {v}\r\n" for k, v in self.headers.items()])
        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        request_body = self.rfile.read(content_length) if content_length > 0 else b""
        # 拼接完整raw_data（与原有socket的raw_data格式完全一致）
        raw_data = (request_line + request_headers + "\r\n").encode("utf-8") + request_body

        # 2. 调用原有请求处理逻辑，获取响应
        client_addr = self.client_address  # 客户端地址（ip, port）
        response = handle_request(raw_data, client_addr)

        # 3. 发送响应到客户端（HTTPServer原生方法）
        self.wfile.write(response)

    def log_message(self, format, *args):
        """重写日志方法：禁用HTTPServer默认控制台日志，统一使用项目logger"""
        pass

# ===================== 启动HTTPServer服务（替代原有socket启动） =====================
def run_http_server(host, port):
    """
    启动基于Python原生HTTPServer的HTTP服务
    替代原有原生socket实现，参数/调用方式完全不变
    """
    try:
        # 初始化HTTPServer：绑定地址 + 自定义请求处理器
        server = HTTPServer((host, port), HTTPServerRequestHandler)
        # 输出启动日志
        logger.info(f"[Server] HTTPServer running on http://{host}:{port}")
        logger.info(f"[Server] Debug mode: {DEBUG}, Static dir: {STATIC_DIR}")
        logger.info(f"[Server] Press CTRL+C to stop server")

        # 启动服务（永久运行，直到Ctrl+C终止）
        server.serve_forever()

    except KeyboardInterrupt:
        # 捕获用户中断（Ctrl+C），优雅停止
        logger.info("[Server] Server stopping by user (CTRL+C)")
    except Exception as e:
        # 服务启动异常
        logger.error(f"[Server] Server start error: {str(e)}", exc_info=True)
    finally:
        # 关闭服务，释放端口
        server.server_close()
        logger.info("[Server] HTTPServer stopped successfully")

# 测试：直接运行该文件启动服务
if __name__ == "__main__":
    from config.settings import HOST, PORT
    run_http_server(HOST, PORT)