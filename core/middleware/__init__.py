# 中间件模块初始化
from core.middleware.csrf import csrf_middleware
from core.middleware.rate_limit import rate_limit_middleware
from core.middleware.throttle_debounce import throttle_middleware, debounce_middleware
from core.middleware.auth import auth_middleware
from core.middleware.desensitize import desensitize_middleware