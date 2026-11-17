"""手写向量 / 平面工具库（不依赖 numpy，纯 Python + math）。

为什么手写
----------
截面切割的核心只有四件事：点积判正负、叉积求法向、线段与平面求交、点在平面判断。
把它们一行行写清楚，配合 print，才能真正讲明白"一刀切"是怎么算出来的；
用现成数值库反而把推导过程藏起来了。

坐标约定
--------
* 所有点 / 向量都是三元组 ``(x, y, z)``，用 tuple 表示，函数全部是纯函数，不改入参。
* 角度统一用"度"，绕轴旋转遵循右手定则（拇指指向轴的正方向，四指为旋转方向）。

容差说明
--------
浮点计算不可能精确等于 0，所以所有"是否落在平面上"的判断都使用 ``EPS`` 容差。
默认 EPS = 1e-7：棱长为 1 的正方体上，这个量级远小于任何实际几何特征，
又足够吸收 double 的舍入误差。
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple, TypedDict

# 点 / 向量的类型别名，方便阅读函数签名
Vec3 = Tuple[float, float, float]

# 几何判断容差（长度单位）
EPS: float = 1e-7


# ---------------------------------------------------------------------------
# 一、最基础的向量运算
# ---------------------------------------------------------------------------
def to_vec(value: Sequence[float]) -> Vec3:
    """把任意长度 >= 3 的序列转成三元组，顺带做一次类型/长度检查。"""
    if value is None or len(value) != 3:
        raise ValueError(f"需要三维坐标 (x, y, z)，收到: {value!r}")
    return (float(value[0]), float(value[1]), float(value[2]))


def add(a: Vec3, b: Vec3) -> Vec3:
    """向量加法：逐分量相加。"""
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec3, b: Vec3) -> Vec3:
    """向量减法 a - b：得到"从 b 指向 a"的位移向量。"""
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(v: Vec3, k: float) -> Vec3:
    """数乘：把向量拉长 / 缩短 k 倍（k 为负则反向）。"""
    return (v[0] * k, v[1] * k, v[2] * k)


def dot(a: Vec3, b: Vec3) -> float:
    """点积 a·b = |a||b|cosθ，几何上表示 b 在 a 方向上的投影长度乘以 |a|。

    截面切割里最关键的一步就是点积：把点代入平面方程
        f(P) = (P - P0) · n
    f 的符号直接告诉我们这个点在平面的哪一侧。
    """
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec3, b: Vec3) -> Vec3:
    """叉积 a × b：结果向量同时垂直于 a、b，方向服从右手定则。

    公式展开（行列式形式）：
        | i   j   k  |
        | ax  ay  az |
        | bx  by  bz |
      = (ay*bz - az*by,  az*bx - ax*bz,  ax*by - ay*bx)

    用途：由平面内两条不共线向量求平面法向量；由线段方向求旋转轴。
    """
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(v: Vec3) -> float:
    """向量模长 |v| = √(x² + y² + z²)。"""
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def length_sq(v: Vec3) -> float:
    """模长平方，比较距离时避免开方、也避免浮点误差放大。"""
    return v[0] * v[0] + v[1] * v[1] + v[2] * v[2]


def normalize(v: Vec3, eps: float = EPS) -> Vec3:
    """单位化：v / |v|。长度近似 0 的向量没有方向，直接抛错而不是返回 NaN。

    先按最大分量缩放再求模长：像 (1e308, 1e308, 1e308) 这种输入直接算 x²+y²+z²
    会溢出成 inf，除法后得到 (0, 0, 0) 的"伪零向量"；先缩放就能得到正确的方向。
    """
    scale = max(abs(v[0]), abs(v[1]), abs(v[2]))
    if scale < eps:
        raise ValueError(f"零向量无法单位化: {v!r}")
    scaled = (v[0] / scale, v[1] / scale, v[2] / scale)
    n = length(scaled)
    return (scaled[0] / n, scaled[1] / n, scaled[2] / n)


def distance(a: Vec3, b: Vec3) -> float:
    """两点间距离。"""
    return length(sub(a, b))


def distance_sq(a: Vec3, b: Vec3) -> float:
    """两点间距离平方。"""
    return length_sq(sub(a, b))


def nearly_equal(a: Vec3, b: Vec3, eps: float = EPS) -> bool:
    """判断两个点是否在容差内重合（用于交点去重）。"""
    return distance_sq(a, b) <= eps * eps


def lerp(a: Vec3, b: Vec3, t: float) -> Vec3:
    """线性插值：t=0 得 a，t=1 得 b，中间按比例取点。

    线段与平面求交就靠这一步：先求参数 t，再插值出交点坐标。
    """
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def midpoint(a: Vec3, b: Vec3) -> Vec3:
    """线段中点。"""
    return lerp(a, b, 0.5)


# ---------------------------------------------------------------------------
# 二、平面相关工具
# ---------------------------------------------------------------------------
def signed_distance(point: Vec3, plane_origin: Vec3, plane_normal_unit: Vec3) -> float:
    """带符号的点到平面距离。

    推导：平面上的点 P0，法向量 n（单位），平面上任意点都满足 (P - P0)·n = 0。
    把任意点 P 代入得到 f(P) = (P - P0)·n：
        f > 0  点在法向量指向的一侧（"正面"）
        f < 0  点在法向量背离的一侧（"背面"）
        f = 0  点落在平面上
    |f| 就是点到平面的垂直距离（因为 n 是单位向量）。
    """
    return dot(sub(point, plane_origin), plane_normal_unit)


def point_on_plane(point: Vec3, plane_origin: Vec3, plane_normal_unit: Vec3, eps: float = EPS) -> bool:
    """判断点是否落在平面上：带符号距离的绝对值小于容差即认为在平面上。"""
    return abs(signed_distance(point, plane_origin, plane_normal_unit)) <= eps


def classify_point(point: Vec3, plane_origin: Vec3, plane_normal_unit: Vec3, eps: float = EPS) -> int:
    """把点相对平面分成三类，返回 1 / -1 / 0（正面 / 背面 / 平面上）。

    这样后续判断棱"是否穿过平面"时，只需要看两个端点分类的乘积是不是 -1。
    """
    d = signed_distance(point, plane_origin, plane_normal_unit)
    if d > eps:
        return 1
    if d < -eps:
        return -1
    return 0


def plane_basis(normal_unit: Vec3) -> Tuple[Vec3, Vec3]:
    """由平面法向量构造平面内的两个正交单位向量 (u, v)。

    做法：随便找一个和法向量不平行的参考向量（优先 z 轴，若法向量几乎平行 z 轴则用 y 轴），
    先叉乘得到 u，再用 n × u 得到 v，这样 (u, v, n) 构成右手正交基。

    截面多边形排序就建立在这组基上：把三维交点投影成平面内的二维坐标，
    按极角排序就能得到有序的闭合多边形。
    """
    n = normalize(normal_unit)
    # 参考向量不能与 n 平行，否则叉积为 0；用 1e-6 阈值判断"几乎平行"
    if abs(n[2]) < 0.9:
        helper: Vec3 = (0.0, 0.0, 1.0)
    else:
        helper = (0.0, 1.0, 0.0)
    u = normalize(cross(helper, n))
    v = normalize(cross(n, u))
    return u, v


def project_to_plane_2d(point: Vec3, plane_origin: Vec3, normal_unit: Vec3) -> Tuple[float, float]:
    """把平面上的点投影到平面局部二维坐标系，返回 (a, b)。

    用相对坐标 (P - P0) 分别在 u、v 上做点积，就得到平面内的二维坐标。
    """
    u, v = plane_basis(normal_unit)
    rel = sub(point, plane_origin)
    return (dot(rel, u), dot(rel, v))


# ---------------------------------------------------------------------------
# 三、线段与平面求交（截面切割的核心）
# ---------------------------------------------------------------------------
class SegmentIntersection(TypedDict):
    """segment_plane_intersection 的返回结构。"""

    status: str
    point: Optional[Vec3]
    t: Optional[float]
    d1: float
    d2: float


def segment_plane_intersection(
    p1: Vec3,
    p2: Vec3,
    plane_origin: Vec3,
    plane_normal_unit: Vec3,
    eps: float = EPS,
) -> SegmentIntersection:
    """求线段 p1p2 与平面的交点。

    返回字典（字段固定，便于逐条打印调试）：
        {
          "status": "none" | "point" | "segment" | "endpoint",
          "point": 交点坐标 或 None,
          "t": 参数 t 或 None,
          "d1": p1 的带符号距离,
          "d2": p2 的带符号距离
        }

    推导过程（这就是"一刀切"的全部数学）
    ------------------------------------
    线段上的点可以写成参数方程：
        P(t) = p1 + t * (p2 - p1),   t ∈ [0, 1]
    代入平面方程 (P - P0)·n = 0：
        (p1 + t*(p2 - p1) - P0)·n = 0
        (p1 - P0)·n + t * (p2 - p1)·n = 0
    记 d1 = (p1 - P0)·n，d2 = (p2 - P0)·n，则 (p2 - p1)·n = d2 - d1，于是
        d1 + t * (d2 - d1) = 0
        t = d1 / (d1 - d2)
    由于 d1 与 d2 异号时 t 才落在 (0, 1) 内，所以"棱被切到"的判据就是 d1*d2 < 0。

    四种情形
    --------
    1. d1、d2 同号（都不为 0）        → 整条棱在平面同一侧，无交点
    2. 一端恰好落在平面上（|d| <= eps）→ 交点就是那个端点（status = "endpoint"）
    3. 两端都落在平面上               → 整条棱躺在平面里（status = "segment"）
    4. d1、d2 异号                    → 正常穿越，算出 t 再插值（status = "point"）
    """
    # 第一步：分别算出两个端点带到平面方程里的值（也就是带符号距离）
    d1 = signed_distance(p1, plane_origin, plane_normal_unit)
    d2 = signed_distance(p2, plane_origin, plane_normal_unit)

    # 第二步：处理"两端都在平面上"——整条棱与平面重合
    if abs(d1) <= eps and abs(d2) <= eps:
        return {"status": "segment", "point": p1, "t": 0.0, "d1": d1, "d2": d2}

    # 第三步：处理"一端在平面上"——交点锁定在这个端点上
    if abs(d1) <= eps:
        return {"status": "endpoint", "point": p1, "t": 0.0, "d1": d1, "d2": d2}
    if abs(d2) <= eps:
        return {"status": "endpoint", "point": p2, "t": 1.0, "d1": d1, "d2": d2}

    # 第四步：两端同号（同侧）——棱没有穿过平面
    if (d1 > 0 and d2 > 0) or (d1 < 0 and d2 < 0):
        return {"status": "none", "point": None, "t": None, "d1": d1, "d2": d2}

    # 第五步：异号，正常的"一刀切"。用 t = d1 / (d1 - d2) 定位切割位置
    t = d1 / (d1 - d2)
    hit = lerp(p1, p2, t)
    return {"status": "point", "point": hit, "t": t, "d1": d1, "d2": d2}


# ---------------------------------------------------------------------------
# 四、绕轴旋转（展开图折叠动画的数学基础）
# ---------------------------------------------------------------------------
def rotate_point_about_axis(
    point: Vec3,
    axis_point: Vec3,
    axis_dir_unit: Vec3,
    angle_deg: float,
) -> Vec3:
    """把点绕"过 axis_point、方向为 axis_dir_unit 的直线"旋转 angle_deg 度。

    使用罗德里格斯（Rodrigues）旋转公式：
        v' = v·cosθ + (k × v)·sinθ + k·(k·v)·(1 - cosθ)
    其中 v 是"点相对轴上一点"的位移向量，k 是单位旋转轴。

    三个分量分别的含义：
        v·cosθ            —— 平行于旋转平面内的原有分量按余弦缩放
        (k × v)·sinθ       —— 垂直方向的分量，负责"转过去"
        k·(k·v)·(1-cosθ)   —— 沿轴方向的分量不参与旋转，这里做修正保证轴向不变
    """
    k = normalize(axis_dir_unit)
    theta = math.radians(angle_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    # 把点平移到以 axis_point 为原点的局部坐标
    v = sub(point, axis_point)
    # 拆解：轴向分量 + 旋转平面内分量
    kv = dot(k, v)
    # 罗德里格斯公式本体
    rotated = add(
        add(scale(v, cos_t), scale(cross(k, v), sin_t)),
        scale(k, kv * (1.0 - cos_t)),
    )
    # 平移回世界坐标
    return add(rotated, axis_point)


def rotate_vector_about_axis(v: Vec3, axis_dir_unit: Vec3, angle_deg: float) -> Vec3:
    """只旋转方向向量（不涉及位置），用于验证法向量 / 轴方向的变换。"""
    return rotate_point_about_axis(v, (0.0, 0.0, 0.0), axis_dir_unit, angle_deg)


def axis_from_direction_and_up(direction: Vec3, up: Vec3 = (0.0, 0.0, 1.0)) -> Vec3:
    """由"面片伸展方向"和"上方向"求折叠旋转轴。

    折叠的物理含义：面片绕公共棱转 90°，让原本躺在桌面上的面片"立起来"，
    也就是让伸展方向 direction 转到 up 方向 (0,0,1)。
    能完成这个转换的旋转轴就是 direction × up（右手定则：绕该轴正向旋转
    会把 direction 转向 up）。
    """
    axis = cross(normalize(direction), normalize(up))
    if length(axis) < EPS:
        raise ValueError("伸展方向与上方向平行，无法确定折叠轴")
    return normalize(axis)


# ---------------------------------------------------------------------------
# 五、多边形工具（交点去重、排序、面积、凸性检查）
# ---------------------------------------------------------------------------
def dedupe_points(points: Sequence[Vec3], eps: float = 1e-6) -> List[Vec3]:
    """按容差去重，保留首次出现的点，保持输入顺序。

    一条棱恰好穿过某个顶点时，相邻两条棱会算出同一个交点；
    平面掠过某个顶点时也会有重复交点，必须去重，否则多边形顶点数会虚高。
    """
    result: List[Vec3] = []
    for p in points:
        if all(not nearly_equal(p, q, eps) for q in result):
            result.append(p)
    return result


def sort_points_on_plane(
    points: Sequence[Vec3],
    plane_origin: Vec3,
    plane_normal_unit: Vec3,
    eps: float = 1e-6,
) -> List[Vec3]:
    """把平面上的散乱交点按"绕平面中心一圈"的顺序排好，得到闭合多边形顶点序列。

    做法（凸多边形一定成立，正方体 / 长方体的截面必然是凸多边形）：
    1. 求所有点的重心 C（重心一定在多边形内部）；
    2. 在平面内建立正交基 (u, v)，把每个点变成二维坐标 (a, b)；
    3. 以重心为极点计算极角 atan2(b - bc, a - ac)；
    4. 按极角从 -π 到 π 排序，得到的顺序就是沿着多边形边界走一圈的顺序；
    5. 最后检查有向面积，若为负（顺时针）则整体反转，统一输出逆时针
       （相对平面法向量方向），前端拿到的顶点顺序可以直接做面片三角化。
    """
    pts = dedupe_points(points, eps)
    if len(pts) <= 2:
        return pts

    n = normalize(plane_normal_unit)
    u, v = plane_basis(n)

    # 步骤 1：重心（把点投影到平面局部坐标后再算，减少大坐标带来的误差）
    # 平面基只建一次，逐点投影直接做点积；不要再调 project_to_plane_2d，
    # 否则每个点都会重建一次 (u, v)。
    coords: List[Tuple[float, float]] = []
    for p in pts:
        rel = sub(p, plane_origin)
        coords.append((dot(rel, u), dot(rel, v)))
    cx = sum(c[0] for c in coords) / len(coords)
    cy = sum(c[1] for c in coords) / len(coords)

    # 步骤 2：计算每个点相对重心的极角
    with_angle = []
    for p, (a, b) in zip(pts, coords):
        ang = math.atan2(b - cy, a - cx)
        with_angle.append((ang, p))

    # 步骤 3：按极角排序
    with_angle.sort(key=lambda item: item[0])
    ordered = [p for _, p in with_angle]

    # 步骤 4：统一成逆时针（相对法向量 n）
    if signed_area_3d(ordered, n) < 0:
        ordered.reverse()
    return ordered


def signed_area_3d(points: Sequence[Vec3], plane_normal_unit: Vec3) -> float:
    """用叉积法算多边形在平面法向下的有向面积。

    把多边形拆成以 p0 为顶点的若干三角形，累加 (pi - p0) × (pi+1 - p0) 的模长
    与法向量的点积（符号即方向）。
    """
    if len(points) < 3:
        return 0.0
    n = normalize(plane_normal_unit)
    total = 0.0
    p0 = points[0]
    for i in range(1, len(points) - 1):
        a = sub(points[i], p0)
        b = sub(points[i + 1], p0)
        total += dot(cross(a, b), n)
    return total / 2.0


def polygon_area(points: Sequence[Vec3], plane_normal_unit: Vec3) -> float:
    """多边形面积（取有向面积的绝对值）。"""
    return abs(signed_area_3d(points, plane_normal_unit))


def _vertex_average(points: Sequence[Vec3]) -> Vec3:
    """顶点算术平均（只作为退化情形的兜底，不代表面积重心）。"""
    if not points:
        raise ValueError("空点集没有重心")
    sx = sum(p[0] for p in points) / len(points)
    sy = sum(p[1] for p in points) / len(points)
    sz = sum(p[2] for p in points) / len(points)
    return (sx, sy, sz)


def polygon_centroid(
    points: Sequence[Vec3],
    plane_origin: Vec3,
    plane_normal_unit: Vec3,
) -> Vec3:
    """多边形面积重心（按面积加权），返回三维坐标。

    输入要求顶点按边界顺序排好（sort_points_on_plane 的输出）。
    做法：把顶点投影到平面局部二维坐标系，用鞋带公式的加权形式
        C = Σ((Pi + Pi+1) × 有向叉积) / (3 · Σ有向叉积)
    再沿 (u, v) 基映射回三维。顶点数 < 3 或退化到面积为 0 时，
    退回顶点算术平均，保证不出现除零和 NaN。
    """
    pts = list(points)
    if len(pts) < 3:
        return _vertex_average(pts)

    n = normalize(plane_normal_unit)
    u, v = plane_basis(n)
    coords: List[Tuple[float, float]] = []
    for p in pts:
        rel = sub(p, plane_origin)
        coords.append((dot(rel, u), dot(rel, v)))

    area2 = 0.0
    cx = 0.0
    cy = 0.0
    for i, (x0, y0) in enumerate(coords):
        x1, y1 = coords[(i + 1) % len(coords)]
        cross_i = x0 * y1 - x1 * y0
        area2 += cross_i
        cx += (x0 + x1) * cross_i
        cy += (y0 + y1) * cross_i

    # 退化判断按二维坐标量级缩放，避免"面积恰好为 0"之外还有近零的数值噪声
    scale_ref = max(max(abs(x), abs(y)) for x, y in coords)
    if abs(area2) <= 1e-12 * max(scale_ref * scale_ref, 1e-12):
        return _vertex_average(pts)

    cx /= 3.0 * area2
    cy /= 3.0 * area2
    return add(plane_origin, add(scale(u, cx), scale(v, cy)))


def is_convex_polygon(points: Sequence[Vec3], plane_normal_unit: Vec3, eps: float = 1e-6) -> bool:
    """检查排序后的多边形是否为凸多边形（截面模块自测用）。

    做法：沿边界依次取三条连续边，检查相邻边的叉积方向是否一致；
    只要出现转向翻转，就不是凸多边形。
    """
    pts = list(points)
    n = len(pts)
    if n < 3:
        return False
    sign = 0
    for i in range(n):
        a = pts[i]
        b = pts[(i + 1) % n]
        c = pts[(i + 2) % n]
        turn = dot(cross(sub(b, a), sub(c, b)), plane_normal_unit)
        if abs(turn) <= eps:
            continue  # 共线点，不影响凸性
        s = 1 if turn > 0 else -1
        if sign == 0:
            sign = s
        elif s != sign:
            return False
    return True


def round_point(p: Vec3, ndigits: int = 9) -> Vec3:
    """统一保留小数位，消除 -0.0 与 0.0000000001 这类难看输出。"""
    return (round(p[0], ndigits) + 0.0, round(p[1], ndigits) + 0.0, round(p[2], ndigits) + 0.0)


def round_points(points: Sequence[Vec3], ndigits: int = 9) -> List[Vec3]:
    """批量保留小数位。"""
    return [round_point(p, ndigits) for p in points]


def format_point(p: Optional[Vec3], ndigits: int = 4) -> str:
    """把点格式化成便于阅读的字符串，用于调试打印。"""
    if p is None:
        return "None"
    return "(" + ", ".join(f"{c:.{ndigits}f}" for c in p) + ")"