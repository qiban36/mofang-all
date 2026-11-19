# =============================================================================
# Vercel Python Serverless 入口（catch-all：/api/* 全部进这里）
#
# 为什么文件名是 [...path].py：Vercel 的函数路由按文件名匹配 URL，
# 只有 catch-all 语法才能让 /api/shape/list、/api/hexahedron/get_data、
# /api/section/cut 这类多级路径都落到同一个函数上。
#
# 这个文件只做三件事：
#   1. 把仓库根目录和 backend/ 加进 sys.path，让 backend/main.py 里的
#      `from geometry import ...` 能正常解析；
#   2. 复用 backend/main.py 里现成的 FastAPI app（不复制任何业务代码）；
#   3. 兜底把被剥掉 /api 前缀的请求路径补回来（不同 Vercel 版本行为略有差异）。
# =============================================================================

from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND = os.path.join(_ROOT, "backend")
for _entry in (_ROOT, _BACKEND):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from main import app as _fastapi_app  # noqa: E402  # 必须在 sys.path 设置之后导入


class _NormalizeApiPrefix:
    """保证 FastAPI 收到的一定是 /api/... 开头的路径。

    Vercel 的 catch-all 函数有可能把 /api/ 前缀吃掉（scope.path 变成 /hexahedron/get_data），
    而 backend/main.py 里所有路由都带 /api 前缀。这里统一补回来，
    两种行为下都能命中路由，避免线上出现 404。
    """

    def __init__(self, inner) -> None:
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path") or "/"
            if not path.startswith("/api"):
                scope = dict(scope)
                scope["path"] = "/api" + path
                scope["raw_path"] = scope["path"].encode("utf-8")
        await self.inner(scope, receive, send)


# Vercel Functions 的 ASGI 入口名必须是 app
app = _NormalizeApiPrefix(_fastapi_app)

__all__ = ["app"]
