# =============================================================================
# 根目录入口（Hugging Face Spaces / Render / PythonAnywhere 等 PaaS 用）
#
# 后端代码实际在 backend/ 子目录下，这里做一层薄包装：
# 把 backend/ 塞进 sys.path，然后 import backend/main.py 里的 app。
# 这样任何 PaaS 只要指定"从仓库根目录启动"就能找到 FastAPI app 对象。
# =============================================================================

from __future__ import annotations

import os
import sys

# 把 backend/ 加进搜索路径，backend/main.py 里的 `from geometry import ...` 才能正确解析
_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# noqa: E402 —— import 必须在 sys.path 设置之后
from main import app  # type: ignore

__all__ = ["app"]
