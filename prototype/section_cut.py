"""section_cut.py —— 凸多面体"一刀切"截面计算（行测图推截面演示）

只回答一个问题：**一个平面切进正方体 / 长方体，切口是什么形状？**

公考"一刀切"的规则限制（决定了本模块的输出形态，务必先看）
------------------------------------------------------------
行测图推里的截面题，规则是：**用一个平面**把多面体切开，看切口形状。由此有三条铁律：

1. **截面不能拐弯**。平面与凸多面体的交集是凸集，它的边界必然是一个**凸多边形**：
   不会出现 L 形、T 形、凹多边形这类带凹角（内角 > 180°）的形状。
   这条是解题"秒杀点"——选项里凡是凹进去、缺一个角的，直接排除，不用去想怎么切。
2. **截面不会断开**。切一刀只得到一个连通的闭合多边形，不可能切成两个分散的区域。
3. **顶点一定落在棱上，边一定落在面上**。所以正方体的截面最多 6 边形（6 个面各贡献一条边），
   最少是三角形；切得"太浅"时会退化成一条线段甚至一个点。

正因为"不能拐弯"，输出必须是**绕一圈排好序**的顶点序列。
如果按"棱的遍历顺序"直接把交点连起来，就会连出跨越内部的对角线，看起来像是截面拐了弯——
那是错的。所以求交和排序必须分成两步：先收集所有交点（无序），再统一排序（闭合凸多边形）。

模块流程（对应函数）
--------------------
    get_shape_data()          读取几何体：8 个顶点、12 条棱
    collect_intersections()   求交：遍历 12 条棱，调用 segment_plane_intersect 收集合法交点
    order_polygon()           排序：交点 ≥ 3 时排成闭合多边形（凸多边形的边界顺序）
    cut_shape_by_plane()      串起来：判定状态码（无截面 / 单点 / 线段 / 闭合多边形）+ 提示文字

浮点误差
--------
所有"是否在平面上""交点是否算重复"的判断统一用 1e-6 容差（``EPS``）：
棱长为 1 的几何体上，1e-6 远小于任何真实几何特征（顶点间距是 1），
又足以吸收 double 的运算误差，不会把"本来在平面上的顶点"判成不在。

依赖
----
同目录的 ``vector_utils.py``：本模块直接调用它的 ``segment_plane_intersect``（求交）
和 ``sort_intersection_points``（排序），不在本文件里重复实现向量运算。

快速上手
--------
    from section_cut import cut_shape_by_plane

    result = cut_shape_by_plane("cube", [0.5, 0.5, 0.5], [1, 1, 1])
    print(result["status"])    # "polygon"
    print(result["points"])    # 6 个顶点，已按边界顺序排好

命令行调试（打印每个截面点）：见同目录的 test_section_cut.py。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# 本模块依赖同目录的向量工具：求交与排序都直接复用，避免两处逻辑各写一遍
try:
    from vector_utils import (
        cross,
        distance_point_plane,
        dot,
        normalize,
        point_on_plane,
        segment_plane_intersect,
        sort_intersection_points,
    )
except ImportError as exc:  # pragma: no cover - 只在文件被拆散时触发
    raise ImportError(
        "section_cut.py 需要同目录的 vector_utils.py（把两个文件放在同一个文件夹里）"
    ) from exc

Vec3 = Tuple[float, float, float]

# ---------------------------------------------------------------------------
# 容差：本模块统一用 1e-6（比 vector_utils 默认的 1e-9 宽一档）
# 理由：行测演示里的坐标大多是 0.5、1/3 这类"人为取的中间值"，
# 手算/前端传来的浮点值往往有 1e-7~1e-8 的抖动，用 1e-6 能稳稳吃掉它。
# ---------------------------------------------------------------------------
EPS: float = 1e-6

# 状态码：字符串给人看，数字给程序判断（前端 if 判断更省事）
STATUS_NONE = "none"        # 无截面：平面完全在体外
STATUS_POINT = "point"      # 退化成一个点：平面只擦过顶点
STATUS_SEGMENT = "segment"  # 退化成线段：平面只擦过一条棱
STATUS_POLYGON = "polygon"  # 闭合多边形：正常截面

STATUS_CODES: Dict[str, int] = {
    STATUS_NONE: 0,
    STATUS_POINT: 1,
    STATUS_SEGMENT: 2,
    STATUS_POLYGON: 3,
}

# 公考规则提示：本模块所有"多边形"结论都受这条规则约束
SECTION_RULE_NOTE: str = (
    "公考一刀切规则：一个平面切凸多面体，截面一定是闭合的凸多边形，"
    "不可能拐弯（出现凹角/L 形/T 形），也不会断成两片；"
    "顶点一定落在棱上，正方体截面最多 6 边形。"
)

# 默认尺寸：正方体棱长 1；长方体默认 2 x 1.5 x 1（三个方向长度不同，一眼能看出是长方体）
CUBE_SIDE: float = 1.0
CUBOID_DIMS: Tuple[float, float, float] = (2.0, 1.5, 1.0)

# 顶点命名：底面 A B C D（逆时针），顶面 E F G H，一一对应
VERTEX_LABELS: Tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G", "H")

# 12 条棱：底面 4 条 + 顶面 4 条 + 竖直棱 4 条（下标对应 VERTEX_LABELS）
EDGE_INDICES: Tuple[Tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 0),   # 底面 A-B-C-D-A
    (4, 5), (5, 6), (6, 7), (7, 4),   # 顶面 E-F-G-H-E
    (0, 4), (1, 5), (2, 6), (3, 7),   # 竖棱 A-E B-F C-G D-H
)


# ===========================================================================
# 一、读取几何体：顶点 + 棱
# ===========================================================================
def get_shape_data(shape_name: str, dims: Optional[Sequence[float]] = None) -> Dict[str, object]:
    """读取几何体的顶点、棱列表（只支持正方体 / 长方体）。

    坐标系：右手坐标系，底面固定在 z = 0，整体落在第一卦限。
    顶点编号固定 A~H：

        A(0,0,0)  B(a,0,0)  C(a,b,0)  D(0,b,0)     # 底面
        E(0,0,c)  F(a,0,c)  G(a,b,c)  H(0,b,c)     # 顶面

    参数
    ----
    shape_name : ``"cube"`` / ``"正方体"`` / ``"cuboid"`` / ``"长方体"``
    dims       : 长方体三边 (a, b, c)；正方体只取第一个值（默认 1）

    返回
    ----
    {"name", "dims", "vertices": 8 个点, "labels": 8 个名字, "edges": 12 条棱的下标对}
    """
    key = str(shape_name).strip().lower()

    if key in ("cube", "正方体"):
        side = float(dims[0]) if dims is not None else CUBE_SIDE
        a = b = c = side
        name = "cube"
    elif key in ("cuboid", "长方体", "box"):
        a, b, c = (float(dims[0]), float(dims[1]), float(dims[2])) if dims is not None else CUBOID_DIMS
        name = "cuboid"
    else:
        raise ValueError(f"不支持的几何体: {shape_name}；可用值: cube（正方体）/ cuboid（长方体）")

    if a <= 0 or b <= 0 or c <= 0:
        raise ValueError(f"几何体尺寸必须为正数，收到: {(a, b, c)}")

    # 8 个顶点：先底面 4 个（逆时针），再顶面 4 个（与底面一一对应）
    vertices: List[Vec3] = [
        (0.0, 0.0, 0.0),  # A
        (a, 0.0, 0.0),    # B
        (a, b, 0.0),      # C
        (0.0, b, 0.0),    # D
        (0.0, 0.0, c),    # E
        (a, 0.0, c),      # F
        (a, b, c),        # G
        (0.0, b, c),      # H
    ]

    return {
        "name": name,
        "dims": (a, b, c),
        "vertices": vertices,
        "labels": VERTEX_LABELS,
        # 12 条棱：(起点下标, 终点下标)
        "edges": [tuple(e) for e in EDGE_INDICES],
    }


# ===========================================================================
# 二、求交（第一步）：遍历每条棱，收集所有合法交点
# ===========================================================================
def collect_intersections(
    vertices: Sequence[Sequence[float]],
    edges: Sequence[Sequence[int]],
    plane_origin: Sequence[float],
    plane_normal: Sequence[float],
    eps: float = EPS,
    verbose: bool = False,
) -> Tuple[List[Vec3], List[Dict[str, object]]]:
    """遍历所有棱，调用 ``segment_plane_intersect`` 收集交点（**故意不排序**）。

    为什么这一步只收集、不排序？
    ---------------------------
    棱是按固定顺序遍历的，交点顺序天然是乱的：先算到的可能是多边形对边的两个点。
    排序要基于"平面内的极角"，必须等交点**全部**收齐才能做，
    所以求交与排序拆成两个函数（求交 → 收集，排序 → 下一步）。

    收集时补一条规则
    ----------------
    如果一条棱整条躺在平面上（平面与某个面共面），``segment_plane_intersect`` 会返回 None
    （因为"交点不唯一"）。为了不丢点，这里额外把**落在平面上的顶点**补进集合，
    反正后面会按容差去重，重复顶点不会变成重复多边形顶点。

    返回
    ----
    (points, details)：
        points  —— 已按 1e-6 去重后的交点列表（顺序 = 棱的遍历顺序，尚未排序）
        details —— 每条棱的计算明细，调试时打印用（d1/d2、是否穿过、交点）
    """
    n = normalize(plane_normal, eps)  # 单位法向量：保证 d 是真实距离
    points: List[Vec3] = []
    details: List[Dict[str, object]] = []

    # ---- 主体：逐条棱求交（12 条棱 → 最多 12 个交点，正方体截面最多 6 个顶点）----
    for edge_index, (i, j) in enumerate(edges):
        p0 = tuple(float(v) for v in vertices[i])
        p1 = tuple(float(v) for v in vertices[j])

        # 直接复用 vector_utils 的求交：内部用 t = d0/(d0-d1) 判断是否落在线段区间内
        hit = segment_plane_intersect(p0, p1, plane_origin, n, eps)

        details.append(
            {
                "edge_index": edge_index,
                "edge": f"{VERTEX_LABELS[i]}{VERTEX_LABELS[j]}",
                "p0": p0,
                "p1": p1,
                "hit": hit,
            }
        )

        if hit is not None:
            points.append(hit)
            if verbose:
                print(f"    棱 {VERTEX_LABELS[i]}{VERTEX_LABELS[j]}: 穿过 → 交点 "
                      f"({hit[0]:+.4f}, {hit[1]:+.4f}, {hit[2]:+.4f})")
        elif verbose:
            print(f"    棱 {VERTEX_LABELS[i]}{VERTEX_LABELS[j]}: 未穿过（两端同侧，或整条棱在平面上）")

    # ---- 补充：把落在平面上的顶点也收进来（处理"整条棱/整个面与平面共面"的情形）----
    for v_index, vertex in enumerate(vertices):
        if point_on_plane(vertex, plane_origin, n, eps):
            points.append(tuple(float(x) for x in vertex))
            if verbose:
                print(f"    顶点 {VERTEX_LABELS[v_index]} 恰在平面上 → 计入交点集合")

    # ---- 按容差去重：相邻两条棱可能算出同一个交点（交点在顶点处时尤其常见）----
    unique: List[Vec3] = []
    for p in points:
        if all(_distance(p, q) > eps for q in unique):
            unique.append(p)

    if verbose:
        print(f"  → 收集到 {len(points)} 个原始交点，去重后 {len(unique)} 个（容差 {eps:g}）")

    return unique, details


# ===========================================================================
# 三、排序（第二步）：把散乱交点排成闭合多边形
# ===========================================================================
def order_polygon(
    points: Sequence[Sequence[float]],
    plane_origin: Sequence[float],
    plane_normal: Sequence[float],
    eps: float = EPS,
) -> List[Vec3]:
    """把共面交点排成"绕一圈"的闭合顺序（凸多边形的边界顺序）。

    为什么要按极角排，而不是按棱的顺序连？
    -------------------------------------
    因为公考"一刀切"的截面**不能拐弯**：截面必是凸多边形，顶点沿着边界依次相邻。
    以多边形重心为极点算极角、按极角排序，得到的正是"沿边界走一圈"的顺序；
    如果按棱的遍历顺序连点，就会出现横穿多边形内部的对角线，
    画出来像"拐了一个弯"，与公考规则直接冲突。

    实现上直接调用 ``vector_utils.sort_intersection_points``：
    去重 → 求重心 → 在平面内建正交基 (u, v) → atan2 极角排序 → 校正成相对法向量的逆时针。

    参数
    ----
    points : 求交阶段收集到的交点（无序，可含重复点，内部会再去一次重）

    返回
    ----
    排好序的顶点列表；点数 ≤ 2 时原样返回（构不成多边形）。
    """
    pts = [tuple(float(v) for v in p) for p in points]
    if len(pts) < 3:
        # 少于 3 个点没有"环绕顺序"，直接返回（点 / 线段场景由调用方判定）
        return pts

    # 共面自检：这批点理论上都在平面上，若不在说明上游调用有误，早点暴露
    n = normalize(plane_normal, eps)
    for p in pts:
        if abs(dot(_sub(p, plane_origin), n)) > max(eps, 1e-6):
            raise ValueError(f"交点不在指定平面上，无法排序: {p}")

    return sort_intersection_points(pts, plane_origin, n, eps)


# ===========================================================================
# 四、主函数：一刀切
# ===========================================================================
def cut_shape_by_plane(
    shape_name: str,
    plane_origin: Sequence[float],
    plane_normal: Sequence[float],
    dims: Optional[Sequence[float]] = None,
    eps: float = EPS,
    verbose: bool = False,
) -> Dict[str, object]:
    """用平面切几何体，返回截面结果。

    参数
    ----
    shape_name   : ``"cube"`` / ``"cuboid"``（也接受中文）
    plane_origin : 平面上任意一点 [x, y, z]
    plane_normal : 平面法向量 [nx, ny, nz]（不必归一化，但不能是零向量）
    dims         : 长方体三边；正方体可省略
    eps          : 浮点容差，默认 1e-6
    verbose      : 是否打印逐棱求交过程

    返回
    ----
    {
        "shape": 几何体名,
        "status": "none" / "point" / "segment" / "polygon",   # 状态码（字符串）
        "status_code": 0 / 1 / 2 / 3,                        # 状态码（数字）
        "points": 截面顶点列表（polygon 时已按边界顺序排好；none 时为空）,
        "closed_polygon": 首尾相接的顶点列表（polygon 才有，末点重复首点；否则 None）,
        "message": 中文提示文字,
        "area": 截面面积（polygon 才有，否则 None）,
        "side_count": 多边形边数（polygon 才有，否则 0）,
        "plane": {"origin", "normal"(单位向量)},
        "edges_checked": 参与求交的棱数（固定 12）,
        "edge_details": 逐棱明细（调试用）,
        "rule_note": 公考一刀切规则提示,
    }
    """
    # ---- 0. 参数检查：零法向量无法定义平面 ----
    normal_input = tuple(float(v) for v in plane_normal)
    if _length(normal_input) <= eps:
        raise ValueError("plane_normal 不能是零向量")
    n = normalize(normal_input, eps)   # 内部一律用单位法向量，d 才是真实距离
    origin = tuple(float(v) for v in plane_origin)

    # ---- 1. 读取几何体顶点与棱 ----
    solid = get_shape_data(shape_name, dims)
    vertices: List[Vec3] = solid["vertices"]  # type: ignore[assignment]
    edges: List[Tuple[int, int]] = solid["edges"]  # type: ignore[assignment]

    if verbose:
        print("=" * 66)
        print(f"[一刀切] 几何体 = {solid['name']}, dims = {solid['dims']}, "
              f"顶点 {len(vertices)} 个, 棱 {len(edges)} 条")
        print(f"[一刀切] 平面过点 ({origin[0]:g}, {origin[1]:g}, {origin[2]:g})，"
              f"单位法向量 ({n[0]:.4f}, {n[1]:.4f}, {n[2]:.4f})")

    # ---- 2+3. 求交并收集（不排序）----
    points, details = collect_intersections(vertices, edges, origin, n, eps, verbose)

    # ---- 4. 判定状态：先把退化情形挑出来，剩下的才排序 ----
    count = len(points)

    if count == 0:
        # 平面完全在体外：一个交点都没有
        status = STATUS_NONE
        message = "无截面：平面与几何体没有交点（平面整个在几何体的一侧之外）"
        result_points: List[Vec3] = []

    elif count == 1:
        # 只切到一个顶点：截面退化成一个点
        status = STATUS_POINT
        p = points[0]
        message = f"截面退化成一个点：({p[0]:.3f}, {p[1]:.3f}, {p[2]:.3f})，平面只擦过这个顶点"
        result_points = [points[0]]

    elif count == 2:
        # 只切到一条棱：截面退化成线段
        status = STATUS_SEGMENT
        a, b = points[0], points[1]
        length = _distance(a, b)
        message = (
            f"截面退化成一个线段：({a[0]:.3f}, {a[1]:.3f}, {a[2]:.3f}) → "
            f"({b[0]:.3f}, {b[1]:.3f}, {b[2]:.3f})，长度 {length:.3f}（平面只擦过一条棱）"
        )
        result_points = [a, b]

    else:
        # ---- 4. 交点 ≥ 3：排序成闭合多边形 ----
        ordered = order_polygon(points, origin, n, eps)
        area = _polygon_area(ordered, n)

        if area <= 1e-9:
            # 所有交点共线（例如平面正好切过一条棱的延长线）→ 仍然只能算线段
            status = STATUS_SEGMENT
            a, b = ordered[0], ordered[-1]
            message = (
                f"截面退化成一条线段（{len(ordered)} 个交点共线）："
                f"({a[0]:.3f}, {a[1]:.3f}, {a[2]:.3f}) → ({b[0]:.3f}, {b[1]:.3f}, {b[2]:.3f})"
            )
            result_points = [a, b]
        else:
            # 正常截面：凸多边形（公考一刀切不可能拐弯，所以一定是个凸的闭合图形）
            status = STATUS_POLYGON
            result_points = ordered
            message = (
                f"闭合多边形：{len(ordered)} 边形，面积 {area:.4f}；"
                f"顶点按边界顺序排列（逆时针），相邻两点连边即闭合成形"
            )

    closed: Optional[List[Vec3]] = (
        result_points + [result_points[0]] if status == STATUS_POLYGON and result_points else None
    )

    if verbose:
        print("-" * 66)
        print(f"[结论] status={status}（{STATUS_CODES[status]}）  {message}")
        if status == STATUS_POLYGON:
            for i, p in enumerate(result_points):
                print(f"    顶点[{i}] ({p[0]:+.4f}, {p[1]:+.4f}, {p[2]:+.4f})")
        print("=" * 66)

    return {
        "shape": solid["name"],
        "dims": list(solid["dims"]),  # type: ignore[arg-type]
        "status": status,
        "status_code": STATUS_CODES[status],
        "points": [tuple(round(v, 9) + 0.0 for v in p) for p in result_points],
        "closed_polygon": (
            [tuple(round(v, 9) + 0.0 for v in p) for p in closed] if closed else None
        ),
        "message": message,
        "area": round(_polygon_area(result_points, n), 9) if status == STATUS_POLYGON else None,
        "side_count": len(result_points) if status == STATUS_POLYGON else 0,
        "plane": {"origin": origin, "normal": tuple(round(v, 9) + 0.0 for v in n)},
        "edges_checked": len(edges),
        "edge_details": details,
        # 公考规则提示：截面不可能拐弯，凹凸/缺角的选项直接排除
        "rule_note": SECTION_RULE_NOTE,
    }


# ===========================================================================
# 五、内部小工具
# ===========================================================================
def _sub(a: Sequence[float], b: Sequence[float]) -> Vec3:
    """向量减法 a - b。"""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _length(a: Sequence[float]) -> float:
    """向量模长。"""
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _distance(a: Sequence[float], b: Sequence[float]) -> float:
    """两点距离。"""
    return _length(_sub(a, b))


def _polygon_area(points: Sequence[Sequence[float]], plane_normal: Sequence[float]) -> float:
    """多边形面积：以首点为扇心拆成三角形，累加 (Pi−P0)×(Pi+1−P0) 在法向量上的投影。

    逆时针为正、顺时针为负，最后取绝对值。
    """
    if len(points) < 3:
        return 0.0
    n = normalize(plane_normal)
    total = 0.0
    p0 = points[0]
    for i in range(1, len(points) - 1):
        total += dot(cross(_sub(points[i], p0), _sub(points[i + 1], p0)), n)
    return abs(total) / 2.0


# 便于命令行直接看结果：python section_cut.py
if __name__ == "__main__":
    demo = cut_shape_by_plane("cube", (0.5, 0.5, 0.5), (1.0, 1.0, 1.0), verbose=True)
    print("status =", demo["status"], "| 顶点数 =", len(demo["points"]), "| 面积 =", demo["area"])