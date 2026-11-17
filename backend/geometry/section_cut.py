"""平面切割模块：一刀切下去，正方体 / 长方体的截面到底是什么形状？

完整流程（也是公考立体截面题的标准解法）
---------------------------------------
1. 拿到几何体的 8 个顶点、12 条棱；
2. 把每个顶点代进平面方程 (P - P0)·n，得到带符号距离 → 顶点被分成"正侧 / 负侧 / 平面上"三类；
3. 逐条棱判断是否被平面"穿过"：两端异号才算穿过，算出参数 t 再插值出交点；
4. 把所有交点收集起来（端点恰好在平面上的情况单独处理），按容差去重；
5. 用平面局部坐标系 + 极角排序，把散乱交点排成绕一圈的顺序 → 闭合截面多边形；
6. 按交点数区分四种场景：无交点 / 单点（擦过顶点）/ 线段（擦过一条棱或切到边界）/ 闭合多边形。

为什么要"排序"？
----------------
12 条棱是按下标顺序遍历的，交点天然是乱序的（比如先算到的可能是多边形对边的点）。
前端要连成闭合图形，拿到的点必须沿着多边形边界顺序排列，
所以要用"重心 + 极角排序"把点理顺；正方体、长方体的截面一定是凸多边形，
以重心为极点按极角排序必然得到正确的边界顺序。

调试输出
--------
函数默认 verbose=True，会把每一条棱的计算过程写进日志（带符号距离、t、交点），
然后在末尾输出原始交点顺序与排序后的顺序，一眼就能看出"一刀切"是怎么来的。
自测脚本 / 命令行入口会把 root logger 配成 INFO，所以默认就能在终端看到；
接口层（main.py）也有统一的日志格式，debug=true 时输出和请求日志落在同一处。
"""

from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Sequence, Tuple, TypedDict, cast

from . import shape_data
from . import vector_utils as vu

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 容差：一律按"几何体体对角线"相对缩放
# ---------------------------------------------------------------------------
# 之前用固定的绝对容差（1e-7 / 1e-6 / 1e-9），尺寸稍小的几何体就会出问题：
# 边长 1e-5 的正方体，过体心的正六边形面积约 1.3e-10，会被 "面积 <= 1e-9"
# 误判成线段；边长 1e-9 时所有顶点距离都小于去重容差，被合并成一个点。
# 因此这里改成"相对系数 × 体对角线"，大尺寸、小尺寸都保持同一套判定。
REL_PLANE_EPS: float = 1e-9   # 点到平面的距离 / 端点是否在平面上
REL_DEDUPE_EPS: float = 1e-8  # 交点去重
REL_AREA_EPS: float = 1e-12   # 判定"交点共线"的最小面积（相对体对角线平方）
MIN_EPS: float = 1e-15        # 数值下限，避免尺寸极小时容差退化成 0


def _diagonal(dims: Sequence[float]) -> float:
    """几何体体对角线长度 √(a²+b²+c²)，作为"尺寸量级"的自然代表。"""
    return math.sqrt(sum(float(d) * float(d) for d in dims))


def _tolerances(
    diagonal: float, eps: Optional[float] = None
) -> Tuple[float, float, float]:
    """按体对角线算出一组容差 (plane_eps, dedupe_eps, area_eps)。

    eps 显式传入时覆盖 plane_eps（保留给自测/调试脚本），其余两项仍按尺寸缩放。
    """
    plane_eps = float(eps) if eps is not None else max(diagonal * REL_PLANE_EPS, MIN_EPS)
    dedupe_eps = max(diagonal * REL_DEDUPE_EPS, MIN_EPS)
    area_eps = max(diagonal * diagonal * REL_AREA_EPS, MIN_EPS * MIN_EPS)
    return plane_eps, dedupe_eps, area_eps


def _output_digits(diagonal: float) -> int:
    """输出坐标保留的小数位：至少 9 位；几何体越小保留越多，避免坐标被量化成 0。"""
    if diagonal <= 0 or not math.isfinite(diagonal):
        return 9
    return max(9, -int(math.floor(math.log10(diagonal))) + 9)


def _round_significant(value: float, digits: int = 9) -> float:
    """按有效数字四舍五入：小尺寸几何体的面积不会被 round(x, 9) 抹成 0。"""
    if value == 0.0 or not math.isfinite(value):
        return value
    return float(f"{value:.{digits}g}")


# ---------------------------------------------------------------------------
# 出参结构（TypedDict）：与 main.py 的 SectionData 保持同一形状
# ---------------------------------------------------------------------------
class VertexOnPlane(TypedDict):
    index: int
    label: str
    point: vu.Vec3


class EdgeIntersectionRecord(TypedDict):
    edge_index: int
    edge: List[str]
    p1: vu.Vec3
    p2: vu.Vec3
    d1: float
    d2: float
    status: str
    t: Optional[float]
    point: Optional[vu.Vec3]


class SectionPlane(TypedDict):
    origin: vu.Vec3
    normal: vu.Vec3


class SectionResult(TypedDict):
    shape: str
    dims: List[float]
    plane: SectionPlane
    status: str
    message: str
    point_count: int
    points: List[vu.Vec3]
    closed_polygon: Optional[List[vu.Vec3]]
    area: Optional[float]
    centroid: Optional[vu.Vec3]
    vertices_on_plane: List[VertexOnPlane]
    edges_total: int
    edges_crossed: int
    coplanar_edges: List[EdgeIntersectionRecord]
    edge_intersections: List[EdgeIntersectionRecord]
    warnings: List[str]


def _log(verbose: bool, message: str) -> None:
    """统一的调试日志入口：verbose=False 时完全静默。"""
    if verbose:
        _LOGGER.info(message)


def cut(
    shape: str,
    plane_origin: Sequence[float],
    plane_normal: Sequence[float],
    dims: Optional[Sequence[float]] = None,
    verbose: bool = True,
    eps: Optional[float] = None,
) -> SectionResult:
    """求平面与几何体的截面。

    参数
    ----
    shape        : "cube"（正方体）或 "cuboid"（长方体）
    plane_origin : 平面上的一点 (x, y, z)
    plane_normal : 平面法向量 (nx, ny, nz)，内部会单位化，不需要自己归一
    dims         : 长方体的三边 (a, b, c)，正方体可省略
    verbose      : 是否打印中间计算过程
    eps          : 覆盖"点到平面"的绝对容差；不传则按体对角线自动缩放（推荐）

    返回
    ----
    {
        "shape", "dims", "plane",
        "status": "none" | "point" | "segment" | "polygon",
        "message": 中文提示,
        "points": 排好序的顶点列表（多边形时为边界顺序）,
        "closed_polygon": 首尾相连的多边形（多边形场景才有）,
        "point_count", "area", "centroid",
        "vertices_on_plane": 恰好落在平面上的原始顶点,
        "edge_intersections": 逐棱调试信息,
        "warnings": 退化情况的提醒
    }
    """
    # ---------- 第 0 步：准备几何体与平面 ----------
    solid = shape_data.get_shape(shape, dims)
    shape_name = str(solid["name"])
    vertices: List[vu.Vec3] = [vu.to_vec(v) for v in solid["vertices"]]
    edges: List[Tuple[int, int]] = list(solid["edges"])
    labels: Tuple[str, ...] = solid["vertex_labels"]

    origin = vu.to_vec(plane_origin)
    normal_length_before = vu.length(vu.to_vec(plane_normal))
    normal = vu.normalize(vu.to_vec(plane_normal))  # 法向量单位化：后面算的才是"距离"

    # 容差与输出精度都随几何体尺寸缩放，尺寸再小也不会被误判或量化成 0
    diagonal = _diagonal(solid["dims"])
    plane_eps, dedupe_eps, area_eps = _tolerances(diagonal, eps)
    output_digits = _output_digits(diagonal)

    _log(verbose, "=" * 72)
    _log(verbose, f"[截面切割] 几何体 = {shape_name}, dims = {solid['dims']}, 顶点 {len(vertices)} 个, 棱 {len(edges)} 条")
    _log(verbose, f"[截面切割] 平面原点 = {vu.format_point(origin)}, 输入法向量 = {vu.format_point(vu.to_vec(plane_normal))} (模长 {normal_length_before:.4f})")
    _log(verbose, f"[截面切割] 单位法向量 n = {vu.format_point(normal)}")
    _log(
        verbose,
        f"[截面切割] 容差 = 平面 {plane_eps:.3e} / 去重 {dedupe_eps:.3e} / 面积 {area_eps:.3e}（按体对角线缩放）",
    )
    _log(verbose, "平面方程：(P - P0)·n = 0")

    # ---------- 第 1 步：给 8 个顶点分类（正侧 / 负侧 / 平面上）----------
    _log(verbose, "-" * 72)
    _log(verbose, "[第 1 步] 计算每个顶点到平面的带符号距离 d = (V - P0)·n")
    distances: List[float] = []
    signs: List[int] = []
    vertices_on_plane: List[VertexOnPlane] = []
    for i, vertex in enumerate(vertices):
        d = vu.signed_distance(vertex, origin, normal)
        sign = vu.classify_point(vertex, origin, normal, plane_eps)
        distances.append(d)
        signs.append(sign)
        side = "平面上" if sign == 0 else ("正侧" if sign > 0 else "负侧")
        _log(verbose, f"    顶点 {labels[i]} = {vu.format_point(vertex)}  d = {d:+.6f}  → {side}")
        if sign == 0:
            vertices_on_plane.append({"index": i, "label": labels[i], "point": vu.round_point(vertex, output_digits)})

    # ---------- 第 2 步：逐条棱做"线段与平面求交"（这就是一刀切）----------
    _log(verbose, "-" * 72)
    _log(verbose, "[第 2 步] 遍历 12 条棱，判断每条棱是否被平面穿过（两端异号才穿过）")

    collected: List[vu.Vec3] = [vu.to_vec(v["point"]) for v in vertices_on_plane]  # 先放入平面上的顶点
    edge_intersections: List[EdgeIntersectionRecord] = []
    crossing_count = 0
    coplanar_edges: List[EdgeIntersectionRecord] = []

    for edge_index, (i, j) in enumerate(edges):
        p1, p2 = vertices[i], vertices[j]
        result = vu.segment_plane_intersection(p1, p2, origin, normal, plane_eps)
        status = result["status"]
        t_value = result["t"]
        point = result["point"]

        record: EdgeIntersectionRecord = {
            "edge_index": edge_index,
            "edge": [labels[i], labels[j]],
            "p1": vu.round_point(p1, output_digits),
            "p2": vu.round_point(p2, output_digits),
            "d1": round(result["d1"], output_digits),
            "d2": round(result["d2"], output_digits),
            "status": status,
            "t": None if t_value is None else round(float(t_value), output_digits),
            "point": None if point is None else vu.round_point(point, output_digits),
        }
        edge_intersections.append(record)

        if status == "none":
            _log(verbose, f"    棱{edge_index + 1:>2} {labels[i]}{labels[j]}: d1={record['d1']:+.6f}, d2={record['d2']:+.6f} → 两端同侧，跳过")
            continue

        if status == "segment":
            # 整条棱躺在平面里（平面与某个面共面时会出现）
            coplanar_edges.append(record)
            collected.append(p1)
            collected.append(p2)
            _log(verbose, f"    棱{edge_index + 1:>2} {labels[i]}{labels[j]}: 两端都在平面上 → 整条棱与平面重合")
            continue

        if status == "endpoint":
            # 端点恰好落在平面上：交点就是这个端点，不重复收集也没关系（后面会去重）
            if point is None:  # 理论上不会发生：endpoint 状态一定有交点
                continue
            crossing_count += 1
            collected.append(point)
            _log(verbose, f"    棱{edge_index + 1:>2} {labels[i]}{labels[j]}: 端点恰在平面上 → 交点 = {vu.format_point(point)}")
            continue

        # status == "point"：正常穿越
        if point is None:  # 理论上不会发生：point 状态一定有交点
            continue
        crossing_count += 1
        collected.append(point)
        _log(
            verbose,
            f"    棱{edge_index + 1:>2} {labels[i]}{labels[j]}: d1={record['d1']:+.6f}, d2={record['d2']:+.6f} "
            f"→ 异号，穿过！t = {t_value if t_value is not None else 0.0:.6f} → 交点 {vu.format_point(point)}",
        )

    _log(verbose, "-" * 72)
    _log(verbose, f"[第 3 步] 原始交点（含平面上顶点）共 {len(collected)} 个，去重中……")

    # ---------- 第 3 步：去重 ----------
    # 注意：这里保持全精度，排序与面积都在原始坐标上算；坐标四舍五入只放在最后输出，
    # 否则小尺寸几何体（如边长 1e-9）会在排序前就被量化成一堆重复点。
    points = vu.dedupe_points(collected, dedupe_eps)
    _log(verbose, f"    去重后剩 {len(points)} 个点")
    for idx, p in enumerate(points):
        _log(verbose, f"    原始顺序 [{idx}] {vu.format_point(p)}")

    # ---------- 第 4 步：场景判定 ----------
    warnings: List[str] = []
    if coplanar_edges:
        warnings.append(f"有 {len(coplanar_edges)} 条棱完全落在平面上，说明平面与几何体的某个面共面，返回值直接取该面的四边形")

    status = "none"
    message = ""
    closed_polygon: Optional[List[vu.Vec3]] = None
    area: Optional[float] = None
    centroid: Optional[vu.Vec3] = None

    if len(points) == 0:
        status = "none"
        message = "该平面与几何体没有交点：平面完全在几何体外侧（或刚好错过所有顶点与棱）"
        _log(verbose, f"[结论] {message}")
    elif len(points) == 1:
        status = "point"
        message = f"该平面只与几何体相切于一个顶点 {vu.format_point(points[0])}，截面退化成一个点"
        _log(verbose, f"[结论] {message}")
    elif len(points) == 2:
        status = "segment"
        message = (
            f"该平面只擦过几何体的一条棱/边界，截面退化成线段："
            f"{vu.format_point(points[0])} → {vu.format_point(points[1])}"
        )
        _log(verbose, f"[结论] {message}")
    else:
        # ---------- 第 5 步：排序成闭合多边形 ----------
        _log(verbose, "-" * 72)
        _log(verbose, "[第 4 步] 交点数量 ≥ 3，按平面极角排序，生成闭合多边形")
        ordered = vu.sort_points_on_plane(points, origin, normal, dedupe_eps)
        area_value = vu.polygon_area(ordered, normal)
        centroid_value = vu.polygon_centroid(ordered, origin, normal)

        if area_value <= area_eps:
            # 所有交点共线：退化成线段（例如平面正好切过一条棱的两个端点及其延长线）
            endpoints = [ordered[0], ordered[-1]]
            status = "segment"
            message = "交点全部共线，退化为线段：" + " → ".join(vu.format_point(p) for p in endpoints)
            points = endpoints
            _log(verbose, f"[结论] {message}")
        else:
            status = "polygon"
            # ---- 排序前后对照：让"乱序交点"变成"一圈闭合多边形"的过程看得见 ----
            # 注意：必须在 points = ordered 之前打印，否则"排序前"打出来的其实是排好序的点
            _log(verbose, "    排序前（棱的遍历顺序，是乱的）：")
            for idx, p in enumerate(points):
                _log(verbose, f"      原始[{idx}] {vu.format_point(p)}")
            points = ordered
            closed_polygon = ordered + [ordered[0]]  # 首尾相连，前端可直接画闭合折线
            area = _round_significant(area_value)
            centroid = vu.round_point(centroid_value, output_digits)
            convex = vu.is_convex_polygon(ordered, normal)
            message = f"截面是 {len(ordered)} 边形（{'凸' if convex else '非凸'}多边形，面积 {area:.6g}）"
            _log(verbose, "    排序后（绕重心极角排序，可直接连成闭合多边形）：")
            for idx, p in enumerate(ordered):
                _log(verbose, f"      顶点[{idx}] {vu.format_point(p)}")

            # ---- 闭合校验：逐边长度 + 首尾闭合距离 + 周长 ----
            edge_lengths = [
                vu.distance(ordered[i], ordered[(i + 1) % len(ordered)]) for i in range(len(ordered))
            ]
            closing_gap = vu.distance(ordered[-1], ordered[0])
            perimeter = sum(edge_lengths)
            _log(verbose, "    闭合校验：")
            _log(verbose, "      边 0-1 … n-1-0 的长度 = " + ", ".join(f"{d:.6f}" for d in edge_lengths))
            _log(verbose, f"      首尾闭合距离（末点→首点，应等于最后一条边长） = {closing_gap:.6f}")
            _log(verbose, f"      周长 = {perimeter:.6f}")
            _log(verbose, f"    多边形顶点数 = {len(ordered)}，面积 = {area:.6f}，重心 = {vu.format_point(centroid)}")
            _log(verbose, f"    凸性检查 = {convex}（公考一刀切的截面一定凸，拐弯的选项可排除）")
            _log(verbose, f"[结论] {message}")

    _log(verbose, "=" * 72)

    section_result: SectionResult = {
        "shape": shape_name,
        "dims": list(solid["dims"]),
        "plane": {
            "origin": vu.round_point(origin, output_digits),
            "normal": vu.round_point(normal, output_digits),
        },
        "status": status,
        "message": message,
        "point_count": len(points),
        "points": [vu.round_point(p, output_digits) for p in points],
        "closed_polygon": [vu.round_point(p, output_digits) for p in closed_polygon] if closed_polygon else None,
        "area": area,
        "centroid": centroid,
        "vertices_on_plane": vertices_on_plane,
        "edges_total": len(edges),
        "edges_crossed": crossing_count,
        "coplanar_edges": coplanar_edges,
        "edge_intersections": edge_intersections,
        "warnings": warnings,
    }
    return section_result


def cut_with_dict(payload: Dict[str, object], verbose: bool = True) -> SectionResult:
    """给自测脚本用的小包装：直接吃一个字典参数。"""
    return cut(
        shape=str(payload.get("shape", "cube")),
        plane_origin=cast(Sequence[float], payload["plane_origin"]),
        plane_normal=cast(Sequence[float], payload["plane_normal"]),
        dims=cast(Optional[Sequence[float]], payload.get("dims")),
        verbose=verbose,
    )


# 常用内部自测：直接 python -m geometry.section_cut 就能看到结果
if __name__ == "__main__":
    # 命令行入口自己配置日志，保证 verbose=True 的输出能直接看到
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    demos = [
        ("cube", [0.5, 0.0, 0.5], [1.0, 0.0, 0.0], "竖直切一刀 → 正方形"),
        ("cube", [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], "过(0,0,0)顶点 → 单点"),
        ("cube", [0.0, 0.0, 0.0], [1.0, 1.0, 0.0], "沿一条棱擦过 → 线段"),
        ("cube", [0.0, 0.0, 5.0], [0.0, 0.0, 1.0], "平面在体外 → 无交点"),
        ("cube", [0.0, 0.0, 0.5], [1.0, 0.0, 0.0], "过中心竖直 → 正方形"),
        ("cuboid", [0.0, 0.0, 0.0], [1.0, 1.0, 1.0], "长方体过顶点 → 单点"),
    ]
    for shape_name, origin, normal, desc in demos:
        print(f"\n>>> 用例：{desc}")
        result = cut(shape_name, origin, normal, verbose=True)
        print(f">>> status = {result['status']}，points = {result['points']}")