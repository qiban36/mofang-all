"""基础几何体数据（顶点 / 棱 / 面）。

这个模块只做一件事：把"正方体"和"长方体"用最朴素的方式写死成
顶点坐标 + 棱索引 + 面索引三张表，供其它模块（截面切割、展开图折叠）使用。

坐标约定
--------
* 右手坐标系：x 向右、y 向后（深度）、z 向上。
* 正方体 / 长方体的底面放在 z = 0 平面，整体位于第一卦限，
  边长由 dims = (a, b, c) 决定，其中 a 沿 x 轴，b 沿 y 轴，c 沿 z 轴。
* 顶点编号固定为 A~H：
      A(0,0,0)  B(a,0,0)  C(a,b,0)  D(0,b,0)    # 底面 z = 0
      E(0,0,c)  F(a,0,c)  G(a,b,c)  H(0,b,c)    # 顶面 z = c
  这样编号可以让"棱"和"面"都写成好读的索引对，方便调试时对照。

为什么底面放在 z = 0？
-----------------------
公考里的立方体展开图是"把盒子摊平在桌面上"，摊平的平面自然就是 z = 0，
所以让正方体的底面和 z = 0 重合，展开图就能直接落在 z = 0 上，
折叠动画也就变成"从桌面立起来"的直观过程。
"""

from __future__ import annotations

from typing import List, Sequence, Tuple, TypedDict


class FaceDef(TypedDict):
    """一个面的定义：顶点下标 + 单位外法向量。"""

    name: str
    label: str
    vertex_indices: Tuple[int, ...]
    normal: Tuple[float, ...]


class ShapeData(TypedDict):
    """build_box 的返回值，也是截面模块消费的几何体结构。"""

    name: str
    dims: Tuple[float, float, float]
    vertices: List[Tuple[float, float, float]]
    vertex_labels: Tuple[str, ...]
    edges: List[Tuple[int, int]]
    faces: List[FaceDef]


class ShapeCatalogEntry(TypedDict):
    """/api/shape/list 里的一条几何体说明。"""

    name: str
    label: str
    dims: List[float]
    vertex_count: int
    edge_count: int
    face_count: int
    has_unfold: bool
    description: str


# 顶点名，与 vertices 列表下标一一对应
VERTEX_LABELS: Tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G", "H")

# 棱：12 条。前 4 条是底面、接着 4 条是顶面、最后 4 条是竖棱（侧棱）
EDGE_LABELS: Tuple[Tuple[int, int], ...] = (
    (0, 1),  # A-B  底面
    (1, 2),  # B-C  底面
    (2, 3),  # C-D  底面
    (3, 0),  # D-A  底面
    (4, 5),  # E-F  顶面
    (5, 6),  # F-G  顶面
    (6, 7),  # G-H  顶面
    (7, 4),  # H-E  顶面
    (0, 4),  # A-E  竖棱
    (1, 5),  # B-F  竖棱
    (2, 6),  # C-G  竖棱
    (3, 7),  # D-H  竖棱
)

# 面：6 个。每个面给出顶点下标（按逆时针/顺时针都能用，截面模块只关心顶点集合）
# 和该面的单位外法向量（用于调试打印与"平面与某个面共面"的判断）
FACE_DEFS: Tuple[FaceDef, ...] = (
    {"name": "bottom", "label": "底面", "vertex_indices": (0, 1, 2, 3), "normal": (0.0, 0.0, -1.0)},
    {"name": "top", "label": "顶面", "vertex_indices": (4, 5, 6, 7), "normal": (0.0, 0.0, 1.0)},
    {"name": "front", "label": "前面", "vertex_indices": (0, 1, 5, 4), "normal": (0.0, -1.0, 0.0)},
    {"name": "back", "label": "后面", "vertex_indices": (3, 2, 6, 7), "normal": (0.0, 1.0, 0.0)},
    {"name": "left", "label": "左面", "vertex_indices": (0, 3, 7, 4), "normal": (-1.0, 0.0, 0.0)},
    {"name": "right", "label": "右面", "vertex_indices": (1, 2, 6, 5), "normal": (1.0, 0.0, 0.0)},
)

# 默认尺寸：正方体边长 1，长方体取 2 x 1.5 x 1 便于肉眼区分三个方向
DEFAULT_CUBE_DIMS: Tuple[float, float, float] = (1.0, 1.0, 1.0)
DEFAULT_CUBOID_DIMS: Tuple[float, float, float] = (2.0, 1.5, 1.0)


def build_box(dims: Sequence[float] = DEFAULT_CUBE_DIMS) -> ShapeData:
    """按给定尺寸生成一个长方体的完整数据（正方体是它的特例）。

    参数
    ----
    dims: (a, b, c) —— 沿 x / y / z 三个方向的长度。

    返回
    ----
    {
        "name": "cube" / "cuboid",
        "dims": (a, b, c),
        "vertices": [(x, y, z), ...] 8 个,
        "vertex_labels": ("A", ..., "H"),
        "edges": [(i, j), ...] 12 条,
        "faces": [{"name", "label", "vertex_indices", "normal"}, ...] 6 个
    }
    """
    a, b, c = (float(dims[0]), float(dims[1]), float(dims[2]))
    if a <= 0 or b <= 0 or c <= 0:
        raise ValueError("几何体尺寸必须为正数")

    # 8 个顶点：底面 4 个 + 顶面 4 个（顺序与 VERTEX_LABELS 一致）
    vertices: List[Tuple[float, float, float]] = [
        (0.0, 0.0, 0.0),  # A
        (a, 0.0, 0.0),    # B
        (a, b, 0.0),      # C
        (0.0, b, 0.0),    # D
        (0.0, 0.0, c),    # E
        (a, 0.0, c),      # F
        (a, b, c),        # G
        (0.0, b, c),      # H
    ]

    # 面数据复制一份字典，避免调用方改动全局常量；
    # 字典里的值是元组（不可变），所以不必做 tuple() 转换或深拷贝
    faces: List[FaceDef] = [
        {
            "name": f["name"],
            "label": f["label"],
            "vertex_indices": f["vertex_indices"],
            "normal": f["normal"],
        }
        for f in FACE_DEFS
    ]

    is_cube = abs(a - b) < 1e-9 and abs(b - c) < 1e-9
    return {
        "name": "cube" if is_cube else "cuboid",
        "dims": (a, b, c),
        "vertices": vertices,
        "vertex_labels": VERTEX_LABELS,
        "edges": list(EDGE_LABELS),
        "faces": faces,
    }


def build_cube(size: float = 1.0) -> ShapeData:
    """生成棱长为 size 的正方体。"""
    return build_box((size, size, size))


def build_cuboid(dims: Sequence[float] = DEFAULT_CUBOID_DIMS) -> ShapeData:
    """生成长方体。"""
    return build_box(dims)


def get_shape(shape: str, dims: Sequence[float] | None = None) -> ShapeData:
    """按名字取几何体。

    shape 支持 "cube"（正方体）与 "cuboid"（长方体）；
    dims 为空时使用各自默认尺寸。传了 dims 的长方体不会被强制成正方体。
    """
    key = (shape or "").strip().lower()
    if key in ("cube", "正方体"):
        if dims is None:
            return build_cube(DEFAULT_CUBE_DIMS[0])
        return build_box((float(dims[0]), float(dims[0]), float(dims[0])))
    if key in ("cuboid", "cuboid_box", "长方体"):
        return build_cuboid(DEFAULT_CUBOID_DIMS if dims is None else dims)
    raise ValueError(f"不支持的几何体: {shape}，可选值: cube / cuboid")


# 供 /api/shape/list 使用的几何体清单
SHAPE_CATALOG: Tuple[ShapeCatalogEntry, ...] = (
    {
        "name": "cube",
        "label": "正方体",
        "dims": list(DEFAULT_CUBE_DIMS),
        "vertex_count": 8,
        "edge_count": 12,
        "face_count": 6,
        "has_unfold": True,
        "description": "棱长 1 的正方体，底面位于 z=0 平面，支持 11 种展开图",
    },
    {
        "name": "cuboid",
        "label": "长方体",
        "dims": list(DEFAULT_CUBOID_DIMS),
        "vertex_count": 8,
        "edge_count": 12,
        "face_count": 6,
        "has_unfold": False,
        "description": "默认 2 x 1.5 x 1 的长方体，可通过 dims 自定义三边长度，支持任意平面截面",
    },
)


def edge_endpoints(shape_data: ShapeData, edge_index: int) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
    """取第 edge_index 条棱的两个端点坐标（调试打印用）。"""
    i, j = shape_data["edges"][edge_index]
    verts = shape_data["vertices"]
    return verts[i], verts[j]