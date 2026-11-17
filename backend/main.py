"""空间几何 · 几何计算后端（FastAPI 入口）

职责边界
--------
本服务只做几何计算：给出展开图数据、给出平面截面多边形。
**不含任何前端渲染逻辑**，返回的都是纯数据（坐标、旋转轴、角度、颜色编号），
前端（如 http://localhost:5173 的 Vite + Three.js 工程）拿到数据自己画。

接口
----
POST /api/hexahedron/get_data  正方体展开图：6 个面片的展开坐标 / 折叠目标 / 铰链 / 旋转轴 / 角度
POST /api/section/cut          平面切几何体：返回排好序的闭合截面多边形
GET  /api/shape/list           支持的几何体清单 + 支持的 11 种展开图类型

响应约定
--------
成功：HTTP 200 + {"code": 0, "message": "ok", "data": {...}}
失败：HTTP 4xx/5xx + {"code": <状态码>, "message": "<中文原因>", "data": null, "request_id": "..."}
      400 几何 / 参数逻辑错误、422 入参结构错误、500 未预期异常，三种错误共用同一个信封。

启动
----
    python -m pip install -r requirements.txt
    uvicorn main:app --reload --port 8000
    # 或者
    python main.py

调试
----
section/cut 请求里带 "debug": true，服务端会打印逐棱求交的中间过程，
响应里也会带上 edge_intersections 明细。
"""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, Generic, List, Literal, Optional, TypeVar
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from geometry import hexahedron, section_cut, shape_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("mofang.geometry")

# ---------------------------------------------------------------------------
# 入参边界：几何计算是纯浮点运算，坐标 / 尺寸过大时会溢出成 inf，最终无法序列化成 JSON
# ---------------------------------------------------------------------------
MAX_ABS_COORD: float = 1e6   # 平面原点 / 法向量的分量绝对值上限
MIN_DIM: float = 1e-6        # 几何体边长下限（再小就接近 double 精度极限）
MAX_DIM: float = 1e6         # 几何体边长上限
MIN_NORMAL_LENGTH: float = 1e-6  # 法向量模长下限（与 vector_utils 的零向量容差保持安全距离）

# ---------------------------------------------------------------------------
# 应用与 CORS
# ---------------------------------------------------------------------------
app = FastAPI(
    title="空间几何 · 几何计算服务",
    version="1.0.0",
    description=(
        "公考立体几何模拟器的后端计算服务：正方体 11 种展开图的折叠参数、"
        "任意平面与正方体/长方体的截面多边形。只输出数据，不做渲染。"
    ),
)

# 前端 Vite 开发服务器 + 生产部署域名：CORS 白名单可以通过 CORS_ORIGINS 环境变量覆盖，
# 多个域名用英文逗号分隔（示例："https://mofang.vercel.app,https://xxx.up.railway.app"）。
# 开发环境不设变量时默认放行 localhost 的两种写法。
_DEFAULT_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_ENV_ORIGINS = os.environ.get("CORS_ORIGINS", "").strip()
ALLOWED_ORIGINS: List[str] = [
    origin.strip() for origin in _ENV_ORIGINS.split(",") if origin.strip()
] or _DEFAULT_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# request-id：每个请求一个短 id，写进响应头和错误响应体，方便对照日志排查
# ---------------------------------------------------------------------------
@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


# ---------------------------------------------------------------------------
# 入参模型（pydantic v2 校验）
# ---------------------------------------------------------------------------
class HexahedronRequest(BaseModel):
    """正方体展开图请求。"""

    unfold_type: str = Field(
        default="141",
        description="展开图类型：141 / 231 / 222 / 33；也可写成 141-3 直接指定第几种",
        examples=["141", "231-2", "33"],
    )
    variant: Optional[int] = Field(
        default=None,
        description="同一分型的第几种（1 起）。不传则取 1；unfold_type 写成 141-3 时以字段为准",
        examples=[1, 3],
    )

    debug: bool = Field(
        default=False,
        description="是否在服务端打印折叠中间几何量（折叠树、铰链、旋转轴、角度、折后角点）",
    )

    @field_validator("unfold_type")
    @classmethod
    def _check_unfold_type(cls, value: str) -> str:
        text = (value or "").strip()
        if not text:
            raise ValueError("unfold_type 不能为空，可选值：141 / 231 / 222 / 33")
        return text

    @field_validator("variant")
    @classmethod
    def _check_variant(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and value < 1:
            raise ValueError("variant 从 1 开始计数")
        return value


class SectionRequest(BaseModel):
    """平面切割请求。"""

    shape: Literal["cube", "cuboid"] = Field(
        default="cube",
        description="几何体类型：cube（正方体）/ cuboid（长方体）",
        examples=["cube"],
    )
    plane_origin: List[float] = Field(
        ...,
        min_length=3,
        max_length=3,
        description=f"平面上的一个点 [x, y, z]，每个分量绝对值 ≤ {MAX_ABS_COORD:g}",
        examples=[[0.5, 0.0, 0.5]],
    )
    plane_normal: List[float] = Field(
        ...,
        min_length=3,
        max_length=3,
        description=(
            f"平面法向量 [nx, ny, nz]，不必是单位向量，但模长需 ≥ {MIN_NORMAL_LENGTH:g}、"
            f"分量绝对值 ≤ {MAX_ABS_COORD:g}"
        ),
        examples=[[1.0, 0.0, 0.0]],
    )
    dims: Optional[List[float]] = Field(
        default=None,
        min_length=3,
        max_length=3,
        description=(
            f"长方体三边长度 [a, b, c]，每个分量在 [{MIN_DIM:g}, {MAX_DIM:g}] 内；"
            "长方体默认 [2, 1.5, 1]，正方体只取第一个值（默认 1）"
        ),
        examples=[[2.0, 1.5, 1.0]],
    )
    debug: bool = Field(
        default=False,
        description="是否打印逐棱求交的中间过程，并在响应里附带 edge_intersections 明细",
    )

    @field_validator("plane_origin", "plane_normal")
    @classmethod
    def _check_coord_range(cls, value: List[float]) -> List[float]:
        for component in value:
            number = float(component)
            if not math.isfinite(number):
                raise ValueError("坐标分量必须是有限实数（不能是 NaN / Infinity）")
            if abs(number) > MAX_ABS_COORD:
                raise ValueError(f"坐标分量绝对值不能超过 {MAX_ABS_COORD:g}，否则会数值溢出")
        return [float(component) for component in value]

    @field_validator("plane_normal")
    @classmethod
    def _check_normal(cls, value: List[float]) -> List[float]:
        # 分量已限制在 1e6 以内，平方和不会溢出，可以直接算模长
        magnitude = math.sqrt(sum(component * component for component in value))
        if magnitude < MIN_NORMAL_LENGTH:
            raise ValueError(
                f"plane_normal 模长过小（当前 {magnitude:.3g}，至少 {MIN_NORMAL_LENGTH:g}），无法确定平面方向"
            )
        return value

    @field_validator("dims")
    @classmethod
    def _check_dims(cls, value: Optional[List[float]]) -> Optional[List[float]]:
        if value is None:
            return None
        for component in value:
            number = float(component)
            if not math.isfinite(number):
                raise ValueError("dims 的三个分量必须是有限实数")
            if not (MIN_DIM <= number <= MAX_DIM):
                raise ValueError(f"dims 的每个分量必须在 [{MIN_DIM:g}, {MAX_DIM:g}] 内")
        return [float(component) for component in value]

    @model_validator(mode="after")
    def _check_shape_dims(self) -> "SectionRequest":
        # 正方体只允许传 3 个相等的长度，避免"叫正方体却给了长方体尺寸"的歧义
        if self.shape == "cube" and self.dims is not None:
            if len(set(round(v, 12) for v in self.dims)) != 1:
                raise ValueError("shape=cube 时 dims 的三个分量必须相等；要切长方体请用 shape=cuboid")
        return self


# ---------------------------------------------------------------------------
# 出参模型（pydantic v2）：既是 OpenAPI 文档，也是序列化前的最后一道校验
# ---------------------------------------------------------------------------
Vector3 = List[float]
T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """成功响应信封：{ code, message, data }。"""

    code: int = 0
    message: str = "ok"
    data: T


class ApiError(BaseModel):
    """错误响应信封：400 / 422 / 500 共用。"""

    code: int
    message: str
    data: Any = None
    request_id: Optional[str] = None


class FaceData(BaseModel):
    face_index: int
    cell: List[int]
    color_index: int
    color: str
    target_face: str
    target_face_label: str
    start_pos: List[Vector3]
    target_pos: List[Vector3]
    hinge_edge: Optional[List[Vector3]]
    hinge_edge_folded: Optional[List[Vector3]]
    rotate_axis: Optional[Vector3]
    rotate_angle: float
    target_normal: Vector3
    parent_id: Optional[int]
    depth: int
    fold_order: int
    is_base: bool


class AnimationStep(BaseModel):
    face_index: int
    fold_order: int
    start_time: float
    duration: float
    rotate_axis: Optional[Vector3]
    rotate_angle: float
    pivot: Optional[Vector3]
    parent_id: Optional[int]


class FoldAnimation(BaseModel):
    easing: str
    step_duration: float
    overlap: float
    total_duration: float
    fps: int
    play_order: List[int]
    steps: List[AnimationStep]
    note: str


class NetBounds(BaseModel):
    min: Vector3
    max: Vector3
    width: float
    height: float


class HexahedronData(BaseModel):
    unfold_type: str
    variant: int
    net_id: str
    label: str
    note: str
    edge_length: float
    face_count: int
    cells: List[List[int]]
    base_face_index: int
    faces: List[FaceData]
    net_bounds: NetBounds
    fold_sequence: List[int]
    animation: FoldAnimation


class SectionPlane(BaseModel):
    origin: Vector3
    normal: Vector3


class VertexOnPlane(BaseModel):
    index: int
    label: str
    point: Vector3


class EdgeIntersection(BaseModel):
    edge_index: int
    edge: List[str]
    p1: Vector3
    p2: Vector3
    d1: float
    d2: float
    status: str
    t: Optional[float]
    point: Optional[Vector3]


class SectionData(BaseModel):
    # allow_inf_nan=False：任何 inf / NaN 都会在响应校验阶段被拦下，
    # 不会交给 JSON 序列化器（Starlette 的 JSONResponse 也不接受 NaN / Infinity）
    model_config = ConfigDict(allow_inf_nan=False)

    shape: str
    dims: Vector3
    plane: SectionPlane
    status: str
    message: str
    point_count: int
    points: List[Vector3]
    closed_polygon: Optional[List[Vector3]]
    area: Optional[float]
    centroid: Optional[Vector3]
    vertices_on_plane: List[VertexOnPlane]
    edges_total: int
    edges_crossed: int
    coplanar_edges: List[EdgeIntersection]
    edge_intersections: Optional[List[EdgeIntersection]] = None
    warnings: List[str]


class ShapeInfo(BaseModel):
    name: str
    label: str
    dims: Vector3
    vertex_count: int
    edge_count: int
    face_count: int
    has_unfold: bool
    description: str


class UnfoldVariant(BaseModel):
    variant: int
    net_id: str
    label: str
    note: str
    cells: List[List[int]]


class UnfoldGroup(BaseModel):
    code: str
    label: str
    count: int
    variants: List[UnfoldVariant]


class UnfoldTypes(BaseModel):
    total_unfold_types: int
    groups: List[UnfoldGroup]
    codes: List[str]


class SectionStatusInfo(BaseModel):
    status: str
    label: str
    description: str


class ShapeListData(BaseModel):
    shapes: List[ShapeInfo]
    unfold_types: UnfoldTypes
    section_status: List[SectionStatusInfo]


# ---------------------------------------------------------------------------
# 统一错误处理：所有失败都返回同一个信封 { code, message, data, request_id }
# ---------------------------------------------------------------------------
def _request_id(request: Request) -> str:
    """取中间件写入的 request id；拿不到时用 "-" 占位。"""
    return getattr(request.state, "request_id", "-")


def _error_response(
    status_code: int, message: str, request: Request
) -> JSONResponse:
    """构造统一错误响应。code 与 HTTP 状态码保持一致，方便前端分支处理。"""
    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "message": message,
            "data": None,
            "request_id": _request_id(request),
        },
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """pydantic 入参校验失败：把 422 的数组详情压成一句中文，仍然走统一信封。"""
    parts: List[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", ()) if item != "body")
        detail = error.get("msg", "参数不合法")
        parts.append(f"{location}: {detail}" if location else detail)
    message = "；".join(parts) or "请求参数不合法"
    logger.warning("参数校验失败 request_id=%s %s: %s", _request_id(request), request.url.path, message)
    return _error_response(422, message, request)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """几何模块抛出的 ValueError 全部转成 400，前端能直接看到中文原因。"""
    logger.warning("参数或几何计算错误 request_id=%s %s: %s", _request_id(request), request.url.path, exc)
    return _error_response(400, str(exc), request)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """404 等 HTTPException 也统一成同一个信封，避免出现 {"detail": ...}。"""
    return _error_response(exc.status_code, str(exc.detail), request)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """兜底：未预期异常不把堆栈暴露给前端，只写日志并返回带 request_id 的 500。"""
    logger.exception("未处理异常 request_id=%s %s", _request_id(request), request.url.path)
    return _error_response(500, "服务端内部错误，请查看后端日志并按 request_id 排查", request)


# ---------------------------------------------------------------------------
# 接口 1：正方体展开图数据
# ---------------------------------------------------------------------------
@app.post(
    "/api/hexahedron/get_data",
    summary="获取正方体展开图的折叠数据",
    response_model=ApiResponse[HexahedronData],
    responses={400: {"model": ApiError}, 422: {"model": ApiError}, 500: {"model": ApiError}},
)
def hexahedron_get_data(payload: HexahedronRequest) -> dict:
    """返回 6 个面片的展开坐标、折叠目标、铰链公共边、旋转轴、旋转角度、颜色编号。

    * start_pos        展开状态下 4 个角点（z = 0 平面）
    * target_pos       折叠到位后 4 个角点（单位正方体 [0,1]³ 上）
    * hinge_edge       与父面片的公共棱（折痕），摊平状态
    * hinge_edge_folded 折完后这条公共棱的位置
    * rotate_axis      折叠旋转轴（单位向量），rotate_angle 为绕轴旋转角度（90°）
    * parent_id        父面片序号；子面片必须在父面片折完之后再折
    * color_index      颜色编号 1~6，按"折完是哪一面"固定分配

    另外附带 fold_sequence（折叠顺序）与 animation（逐步骤动画时间轴）。
    """
    # debug=True 时后端会打印折叠树、每片的铰链 / 旋转轴 / 角度 / 折后角点
    data = hexahedron.get_unfold_data(payload.unfold_type, payload.variant, debug=payload.debug)
    logger.info(
        "hexahedron/get_data unfold_type=%s variant=%s → %s",
        payload.unfold_type,
        payload.variant,
        data["net_id"],
    )
    return {"code": 0, "message": "ok", "data": data}


# ---------------------------------------------------------------------------
# 接口 2：平面切割求截面
# ---------------------------------------------------------------------------
@app.post(
    "/api/section/cut",
    summary="求平面与几何体的截面多边形",
    response_model=ApiResponse[SectionData],
    responses={400: {"model": ApiError}, 422: {"model": ApiError}, 500: {"model": ApiError}},
)
def section_cut_endpoint(payload: SectionRequest) -> dict:
    """一刀切下去，返回截面。

    status 四种取值：
        none     平面与几何体没有交点
        point    只擦到一个顶点，截面退化成一个点
        segment  只擦过一条棱（或交点共线），截面退化成线段
        polygon  正常截面，points 已按边界顺序排好，closed_polygon 首尾相连
    """
    result: Dict[str, Any] = dict(
        section_cut.cut(
            shape=payload.shape,
            plane_origin=payload.plane_origin,
            plane_normal=payload.plane_normal,
            dims=payload.dims,
            verbose=payload.debug,
        )
    )

    # 非 debug 模式下不返回 12 条棱的逐条明细，减小响应体积
    if not payload.debug:
        result.pop("edge_intersections", None)

    logger.info(
        "section/cut shape=%s status=%s points=%d",
        payload.shape,
        result["status"],
        result["point_count"],
    )
    return {"code": 0, "message": result["message"], "data": result}


# ---------------------------------------------------------------------------
# 接口 3：支持的几何体与展开图清单
# ---------------------------------------------------------------------------
@app.get(
    "/api/shape/list",
    summary="列出支持的几何体与展开图类型",
    response_model=ApiResponse[ShapeListData],
)
def shape_list() -> dict:
    """返回几何体清单（含顶点/棱/面数量）与 11 种展开图的分类与变体。"""
    unfold = hexahedron.list_unfold_types()
    return {
        "code": 0,
        "message": "ok",
        "data": {
            "shapes": list(shape_data.SHAPE_CATALOG),
            "unfold_types": unfold,
            "section_status": [
                {"status": "none", "label": "无截面", "description": "平面完全在几何体外侧"},
                {"status": "point", "label": "单点", "description": "平面只擦过一个顶点"},
                {"status": "segment", "label": "线段", "description": "平面只擦过一条棱，或交点共线"},
                {"status": "polygon", "label": "闭合多边形", "description": "正常截面，顶点已按边界顺序排序"},
            ],
        },
    }


@app.get("/", summary="服务自检")
def index() -> dict:
    """根路径：确认服务活着，并给出接口清单。"""
    return {
        "service": "空间几何 · 几何计算服务",
        "version": app.version,
        "docs": "/docs",
        "endpoints": [
            "POST /api/hexahedron/get_data",
            "POST /api/section/cut",
            "GET  /api/shape/list",
        ],
    }


if __name__ == "__main__":
    # 直接 python main.py 也能跑起来，方便不熟悉 uvicorn 命令的使用者。
    # Railway / Render / Fly.io 等平台会注入 PORT 环境变量，读它；否则默认 8000。
    # host 0.0.0.0：容器内必须监听所有网卡，不能只绑 127.0.0.1，否则外部访问不到。
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=False)
