# =============================================================================
# Vercel Python Serverless 入口
#
# 把根目录 backend/main.py 里的 FastAPI app 挂到 Vercel Functions 上。
# Vercel 收到 /api/* 请求 → 进入本文件 → 转给 FastAPI app → 返回 JSON。
# 这样前后端在同一个 Vercel 项目里、同一个域名下、同源零 CORS。
# =============================================================================

from __future__ import annotations

import os
import sys

# 把 backend/ 塞进搜索路径，让 backend/main.py 里的 `from geometry import ...` 正确解析
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_ROOT, "backend")
for entry in (_ROOT, _BACKEND):
    if entry not in sys.path:
        sys.path.insert(0, entry)

# noqa: E402 —— import 必须在 sys.path 设置之后
from main import app  # type: ignore  # backend/main.py 里的 FastAPI 实例

# Vercel Functions 需要的 ASGI 入口名：app
# （FastAPI app 本身就是 ASGI 可调用对象，直接导出即可）
__all__ = ["app"]
